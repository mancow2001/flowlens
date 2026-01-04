"""Resolution worker that processes flow aggregates.

Builds dependency graph from aggregated flows.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import ResolutionSettings, get_settings
from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.common.metrics import RESOLUTION_ERRORS, RESOLUTION_PROCESSED
from flowlens.enrichment.resolvers.geoip import GeoIPResolver
from flowlens.enrichment.resolvers.protocol import ProtocolResolver
from flowlens.models.flow import FlowAggregate
from flowlens.resolution.aggregator import FlowAggregator
from flowlens.resolution.asset_mapper import AssetMapper
from flowlens.resolution.change_detector import ChangeDetector
from flowlens.resolution.dependency_builder import DependencyBuilder
from flowlens.resolution.gateway_inference import GatewayInferenceService

logger = get_logger(__name__)


class ResolutionWorker:
    """Worker that resolves dependencies from flow aggregates.

    Processes aggregated flows to:
    - Create/update assets
    - Build dependency edges
    - Detect changes
    """

    def __init__(self, settings: ResolutionSettings | None = None) -> None:
        """Initialize resolution worker.

        Args:
            settings: Resolution settings.
        """
        if settings is None:
            settings = get_settings().resolution

        self._settings = settings
        self._batch_size = settings.batch_size
        self._poll_interval = settings.poll_interval_ms / 1000
        self._detection_interval = settings.detection_interval_minutes * 60

        # Initialize components
        geoip_resolver = GeoIPResolver(get_settings().enrichment)
        protocol_resolver = ProtocolResolver()
        asset_mapper = AssetMapper(geoip_resolver)

        self._aggregator = FlowAggregator(settings)
        self._dependency_builder = DependencyBuilder(asset_mapper, protocol_resolver, settings)
        self._change_detector = ChangeDetector(settings)
        self._gateway_inference = GatewayInferenceService()

        # State
        self._running = False
        self._processed_count = 0
        self._gateways_processed = 0
        self._last_detection_run = datetime.min
        self._last_gateway_run = datetime.min

    async def start(self) -> None:
        """Start the resolution worker."""
        self._running = True
        logger.info("Resolution worker started")

        while self._running:
            try:
                # Process pending aggregation windows
                processed = await self._process_aggregation()

                if processed > 0:
                    # Process new aggregates into dependencies
                    deps_processed = await self._process_dependencies()
                    self._processed_count += deps_processed
                    RESOLUTION_PROCESSED.inc(deps_processed)

                # Process gateway observations
                await self._maybe_process_gateways()

                # Run change detection periodically
                await self._maybe_run_detection()

                if processed == 0:
                    # No work, wait before polling again
                    await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Resolution batch failed", error=str(e))
                RESOLUTION_ERRORS.labels(error_type="batch_processing").inc()
                await asyncio.sleep(1)  # Back off on error

        logger.info(
            "Resolution worker stopped",
            total_processed=self._processed_count,
        )

    async def stop(self) -> None:
        """Stop the resolution worker."""
        self._running = False

    async def _process_aggregation(self) -> int:
        """Process pending aggregation windows.

        Returns:
            Number of aggregates created.
        """
        total_aggregates = 0

        async with get_session() as db:
            # Get pending windows
            windows = await self._aggregator.get_pending_windows(db)

            if not windows:
                return 0

            logger.debug("Processing aggregation windows", count=len(windows))

            for window_start, window_end in windows:
                aggregates = await self._aggregator.aggregate_window(
                    db, window_start, window_end
                )
                total_aggregates += aggregates

            await db.commit()

        return total_aggregates

    async def _process_dependencies(self) -> int:
        """Process aggregates into dependencies.

        Returns:
            Number of dependencies processed.
        """
        async with get_session() as db:
            # Fetch unprocessed aggregates
            result = await db.execute(
                select(FlowAggregate)
                .where(FlowAggregate.is_processed == False)
                .order_by(FlowAggregate.window_start)
                .limit(self._batch_size)
            )
            aggregates = result.scalars().all()

            if not aggregates:
                return 0

            logger.debug("Processing aggregates", count=len(aggregates))

            # Build dependencies
            count = await self._dependency_builder.build_batch(db, aggregates)

            # Mark aggregates as processed
            aggregate_ids = [a.id for a in aggregates]
            await db.execute(
                update(FlowAggregate)
                .where(FlowAggregate.id.in_(aggregate_ids))
                .values(is_processed=True)
            )

            await db.commit()
            return count

    async def _maybe_process_gateways(self) -> None:
        """Process gateway observations periodically.

        Runs every 30 seconds to process accumulated gateway observations.
        """
        now = datetime.utcnow()

        # Run every 30 seconds
        if (now - self._last_gateway_run).total_seconds() < 30:
            return

        self._last_gateway_run = now

        try:
            async with get_session() as db:
                # Process observations into gateway relationships
                processed = await self._gateway_inference.process_observations(db)
                self._gateways_processed += processed

                # Update traffic shares
                if processed > 0:
                    await self._gateway_inference.calculate_traffic_shares(db)

                await db.commit()
        except Exception as e:
            logger.error("Gateway inference failed", error=str(e))
            RESOLUTION_ERRORS.labels(error_type="gateway_inference").inc()

    async def _maybe_run_detection(self) -> None:
        """Run change detection if interval has passed."""
        now = datetime.utcnow()

        if (now - self._last_detection_run).total_seconds() < self._detection_interval:
            return

        self._last_detection_run = now

        try:
            async with get_session() as db:
                results = await self._change_detector.run_detection_cycle(db)
                await db.commit()

                if results["events_created"] > 0:
                    logger.info(
                        "Change detection complete",
                        **results,
                    )
        except Exception as e:
            logger.error("Change detection failed", error=str(e))
            RESOLUTION_ERRORS.labels(error_type="change_detection").inc()

    @property
    def stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        return {
            "running": self._running,
            "processed_count": self._processed_count,
            "gateways_processed": self._gateways_processed,
            "asset_cache_size": self._dependency_builder.asset_mapper.cache_size,
            "last_detection_run": self._last_detection_run.isoformat(),
            "last_gateway_run": self._last_gateway_run.isoformat(),
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self._dependency_builder.asset_mapper.clear_cache()
        self._gateway_inference.clear_cache()
