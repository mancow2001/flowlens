"""Enrichment worker that processes flow records.

Polls for unenriched flows, applies enrichments (DNS, GeoIP, protocol),
and marks them as enriched.
"""

import asyncio
import random
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import EnrichmentSettings, get_settings
from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.common.metrics import ENRICHMENT_ERRORS, ENRICHMENT_PROCESSED
from flowlens.enrichment.correlator import AssetCorrelator
from flowlens.enrichment.resolvers.dns import DNSResolver
from flowlens.enrichment.resolvers.geoip import GeoIPResolver
from flowlens.enrichment.resolvers.protocol import ProtocolResolver
from flowlens.models.flow import FlowRecord

logger = get_logger(__name__)

# Maximum retries for deadlock errors
MAX_DEADLOCK_RETRIES = 3


class EnrichmentWorker:
    """Worker that enriches flow records.

    Processes flows in batches, performing:
    - DNS reverse lookup for hostnames
    - GeoIP lookup for location info
    - Protocol/service type inference
    - Asset correlation
    """

    def __init__(self, settings: EnrichmentSettings | None = None) -> None:
        """Initialize enrichment worker.

        Args:
            settings: Enrichment settings.
        """
        if settings is None:
            settings = get_settings().enrichment

        self._settings = settings
        self._batch_size = settings.batch_size
        self._poll_interval = settings.poll_interval_ms / 1000

        # Initialize resolvers
        self._dns_resolver = DNSResolver(settings)
        self._geoip_resolver = GeoIPResolver(settings)
        self._protocol_resolver = ProtocolResolver()
        self._correlator = AssetCorrelator(self._geoip_resolver)

        # State
        self._running = False
        self._processed_count = 0

    async def start(self) -> None:
        """Start the enrichment worker."""
        self._running = True
        logger.info("Enrichment worker started")

        while self._running:
            try:
                processed = await self._process_batch()

                if processed == 0:
                    # No work, wait before polling again
                    await asyncio.sleep(self._poll_interval)
                else:
                    self._processed_count += processed
                    ENRICHMENT_PROCESSED.inc(processed)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Enrichment batch failed", error=str(e))
                ENRICHMENT_ERRORS.labels(error_type="batch_processing").inc()
                await asyncio.sleep(1)  # Back off on error

        logger.info(
            "Enrichment worker stopped",
            total_processed=self._processed_count,
        )

    async def stop(self) -> None:
        """Stop the enrichment worker."""
        self._running = False

    async def _process_batch(self) -> int:
        """Process a batch of unenriched flows.

        Uses FOR UPDATE SKIP LOCKED to prevent multiple workers from
        grabbing the same rows, avoiding deadlocks.

        Returns:
            Number of flows processed.
        """
        for attempt in range(MAX_DEADLOCK_RETRIES):
            try:
                return await self._process_batch_internal()
            except Exception as e:
                error_str = str(e).lower()
                if "deadlock" in error_str:
                    if attempt < MAX_DEADLOCK_RETRIES - 1:
                        # Exponential backoff with jitter
                        delay = (0.1 * (2 ** attempt)) + random.uniform(0, 0.1)
                        logger.warning(
                            "Deadlock detected, retrying",
                            attempt=attempt + 1,
                            max_retries=MAX_DEADLOCK_RETRIES,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "Deadlock persisted after retries",
                            attempts=MAX_DEADLOCK_RETRIES,
                        )
                        ENRICHMENT_ERRORS.labels(error_type="deadlock").inc()
                raise
        return 0

    async def _process_batch_internal(self) -> int:
        """Internal batch processing with row locking.

        Returns:
            Number of flows processed.
        """
        async with get_session() as db:
            # Fetch unenriched flows with FOR UPDATE SKIP LOCKED
            # This prevents multiple workers from grabbing the same rows
            result = await db.execute(
                select(FlowRecord)
                .where(FlowRecord.is_enriched == False)  # noqa: E712
                .order_by(FlowRecord.timestamp)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            flows = result.scalars().all()

            if not flows:
                return 0

            logger.debug("Processing enrichment batch", count=len(flows))

            # Collect unique IPs for batch lookup
            unique_ips = set()
            for flow in flows:
                unique_ips.add(str(flow.src_ip))
                unique_ips.add(str(flow.dst_ip))

            # Batch DNS lookups
            hostnames = await self._dns_resolver.resolve_batch(list(unique_ips))

            # Process each flow
            for flow in flows:
                await self._enrich_flow(db, flow, hostnames)

            await db.commit()
            return len(flows)

    async def _enrich_flow(
        self,
        db: AsyncSession,
        flow: FlowRecord,
        hostnames: dict[str, str | None],
    ) -> bool:
        """Enrich a single flow record.

        Uses a savepoint so individual flow failures don't abort the batch.

        Args:
            db: Database session.
            flow: Flow record to enrich.
            hostnames: Pre-resolved hostnames.

        Returns:
            True if enrichment succeeded, False otherwise.
        """
        try:
            # Use savepoint to isolate this flow's operations
            async with db.begin_nested():
                src_ip = str(flow.src_ip)
                dst_ip = str(flow.dst_ip)

                # Get hostnames from batch results
                src_hostname = hostnames.get(src_ip)
                dst_hostname = hostnames.get(dst_ip)

                # Correlate to assets
                src_asset_id = await self._correlator.correlate(db, src_ip, src_hostname)
                dst_asset_id = await self._correlator.correlate(db, dst_ip, dst_hostname)

                # Get service info
                service_info = self._protocol_resolver.resolve(flow.dst_port, flow.protocol)

                # Build extended fields with enrichment data
                extended = flow.extended_fields or {}
                extended["enrichment"] = {
                    "src_hostname": src_hostname,
                    "dst_hostname": dst_hostname,
                    "src_asset_id": str(src_asset_id),
                    "dst_asset_id": str(dst_asset_id),
                    "service_name": service_info.name if service_info else None,
                    "service_category": service_info.category if service_info else None,
                    "is_encrypted": service_info.encrypted if service_info else None,
                    "enriched_at": datetime.utcnow().isoformat(),
                }

                # Update flow record
                await db.execute(
                    update(FlowRecord)
                    .where(
                        FlowRecord.id == flow.id,
                        FlowRecord.timestamp == flow.timestamp,
                    )
                    .values(
                        is_enriched=True,
                        extended_fields=extended,
                    )
                )
                return True

        except Exception as e:
            logger.warning(
                "Failed to enrich flow",
                flow_id=str(flow.id),
                error=str(e),
            )
            ENRICHMENT_ERRORS.labels(error_type="flow_enrichment").inc()
            return False

    @property
    def stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        return {
            "running": self._running,
            "processed_count": self._processed_count,
            "dns_cache": self._dns_resolver.cache_stats,
            "geoip_enabled": self._geoip_resolver.is_enabled,
            "correlator_cache_size": self._correlator.cache_size,
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self._dns_resolver.cleanup()
        self._geoip_resolver.close()
        self._correlator.clear_cache()
