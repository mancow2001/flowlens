"""Classification worker that processes assets for auto-classification.

Runs as a background service to classify assets based on behavioral features.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import FeatureExtractor
from flowlens.classification.ml.hybrid_engine import HybridClassificationEngine, HybridClassificationResult
from flowlens.classification.scoring_engine import ClassificationResult
from flowlens.common.config import ClassificationSettings, get_settings
from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.common.metrics import (
    CLASSIFICATION_PROCESSED,
    CLASSIFICATION_ERRORS,
    CLASSIFICATION_UPDATES,
    CLASSIFICATION_CONFIDENCE,
)
from flowlens.models.asset import Asset, AssetType
from flowlens.models.classification import AssetFeatures, ClassificationHistory

logger = get_logger(__name__)


class ClassificationWorker:
    """Worker that classifies assets based on behavioral features.

    Polls for assets needing classification and runs the classification
    pipeline:
    1. Extract behavioral features from flow data
    2. Compute scores for each asset type
    3. Update asset if confidence exceeds threshold
    """

    def __init__(self, settings: ClassificationSettings | None = None) -> None:
        """Initialize classification worker.

        Args:
            settings: Classification settings.
        """
        if settings is None:
            settings = get_settings().classification

        self._settings = settings
        self._batch_size = settings.batch_size
        self._poll_interval = settings.poll_interval_ms / 1000
        self._reclassify_interval = timedelta(hours=settings.reclassify_interval_hours)
        self._min_observation_hours = settings.min_observation_hours
        self._auto_threshold = settings.auto_update_confidence_threshold

        # State
        self._running = False
        self._processed_count = 0
        self._update_count = 0

    async def start(self) -> None:
        """Start the classification worker."""
        self._running = True
        logger.info(
            "Classification worker started",
            batch_size=self._batch_size,
            poll_interval=self._poll_interval,
        )

        while self._running:
            try:
                processed = await self._process_batch()

                if processed > 0:
                    self._processed_count += processed
                    CLASSIFICATION_PROCESSED.inc(processed)
                else:
                    # No work, wait before polling again
                    await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Classification batch failed", error=str(e))
                CLASSIFICATION_ERRORS.labels(error_type="batch_processing").inc()
                await asyncio.sleep(1)  # Back off on error

        logger.info(
            "Classification worker stopped",
            total_processed=self._processed_count,
            total_updates=self._update_count,
        )

    async def stop(self) -> None:
        """Stop the classification worker."""
        self._running = False

    async def _process_batch(self) -> int:
        """Process a batch of assets needing classification.

        Returns:
            Number of assets processed.
        """
        async with get_session() as db:
            # Get assets needing classification
            assets = await self._get_assets_to_classify(db)

            if not assets:
                logger.debug(
                    "No assets to classify",
                    min_observation_hours=self._min_observation_hours,
                    reclassify_interval_hours=self._settings.reclassify_interval_hours,
                )
                return 0

            logger.info("Processing classification batch", count=len(assets))

            # Initialize hybrid classification engine for this batch
            engine = HybridClassificationEngine(db=db)
            await engine.initialize()

            for asset in assets:
                try:
                    await self._classify_asset(db, asset, engine)
                except Exception as e:
                    logger.error(
                        "Failed to classify asset",
                        asset_id=str(asset.id),
                        ip=asset.ip_address,
                        error=str(e),
                    )
                    CLASSIFICATION_ERRORS.labels(error_type="asset_classification").inc()

            await db.commit()
            return len(assets)

    async def _get_assets_to_classify(self, db: AsyncSession) -> list[Asset]:
        """Get assets that need classification.

        Criteria:
        - Not locked
        - Not deleted
        - Never classified OR classification is stale
        - Has been observed long enough
        """
        now = datetime.now(timezone.utc)
        stale_cutoff = now - self._reclassify_interval
        observation_cutoff = now - timedelta(hours=self._min_observation_hours)

        logger.debug(
            "Querying assets for classification",
            now=now.isoformat(),
            observation_cutoff=observation_cutoff.isoformat(),
            stale_cutoff=stale_cutoff.isoformat(),
            min_observation_hours=self._min_observation_hours,
        )

        query = (
            select(Asset)
            .where(
                Asset.classification_locked == False,  # noqa: E712
                Asset.deleted_at.is_(None),
                Asset.first_seen <= observation_cutoff,  # Has enough observation time
            )
            .where(
                # Never classified OR classification is stale
                (Asset.last_classified_at.is_(None))
                | (Asset.last_classified_at < stale_cutoff)
            )
            .order_by(
                Asset.last_classified_at.nulls_first(),
                Asset.last_seen.desc(),
            )
            .limit(self._batch_size)
        )

        result = await db.execute(query)
        assets = list(result.scalars().all())
        logger.info(
            "Asset query completed",
            assets_found=len(assets),
            min_observation_hours=self._min_observation_hours,
        )
        return assets

    async def _classify_asset(
        self, db: AsyncSession, asset: Asset, engine: HybridClassificationEngine
    ) -> None:
        """Classify a single asset.

        Args:
            db: Database session.
            asset: Asset to classify.
            engine: Hybrid classification engine to use.
        """
        # Extract behavioral features
        extractor = FeatureExtractor(db)
        features = await extractor.extract_features(
            ip_address=asset.ip_address,
            window_size="5min",
            lookback_hours=self._min_observation_hours,
        )

        # Check minimum flow requirement (use lower threshold if ML is available)
        ml_settings = get_settings().ml_classification
        min_flows = ml_settings.ml_min_flows if engine.ml_enabled else self._settings.min_flows_required

        if features.total_flows < min_flows:
            logger.debug(
                "Insufficient flows for classification",
                asset_id=str(asset.id),
                ip=asset.ip_address,
                flows=features.total_flows,
                required=min_flows,
                ml_enabled=engine.ml_enabled,
            )
            # Update last_classified_at to avoid re-processing too soon
            asset.last_classified_at = datetime.now(timezone.utc)
            return

        # Compute classification using hybrid engine
        # Handle both enum and string types for asset_type
        current_type = None
        if asset.asset_type:
            current_type = asset.asset_type.value if hasattr(asset.asset_type, 'value') else str(asset.asset_type)

        result = await engine.classify(
            features=features,
            current_type=current_type,
        )

        # Record confidence metric
        CLASSIFICATION_CONFIDENCE.observe(result.confidence)

        # Store classification data
        await self._store_classification(db, asset, result, features)

        # Update asset if auto-update threshold met
        if result.should_auto_update:
            await self._update_asset_type(db, asset, result)

        # Log classification method used
        if isinstance(result, HybridClassificationResult):
            logger.info(
                "Asset classified",
                asset_id=str(asset.id),
                ip=asset.ip_address,
                method=result.classification_method,
                recommended_type=result.recommended_type.value,
                confidence=result.confidence,
                ml_confidence=result.ml_confidence,
            )

    async def _store_classification(
        self,
        db: AsyncSession,
        asset: Asset,
        result: ClassificationResult,
        features: Any,
    ) -> None:
        """Store classification results on the asset.

        Args:
            db: Database session.
            asset: Asset being classified.
            result: Classification result.
            features: Extracted features.
        """
        now = datetime.now(timezone.utc)

        # Update asset classification fields
        asset.classification_confidence = result.confidence
        asset.classification_scores = {
            k.value: v.to_dict()
            for k, v in result.scores.items()
        }
        asset.last_classified_at = now

        # Store the classification method used
        if isinstance(result, HybridClassificationResult):
            asset.classification_method = result.classification_method

        # Store feature snapshot
        feature_record = AssetFeatures(
            id=uuid.uuid4(),
            asset_id=asset.id,
            ip_address=asset.ip_address,
            window_size=features.window_size,
            computed_at=features.computed_at,
            inbound_flows=features.inbound_flows,
            outbound_flows=features.outbound_flows,
            inbound_bytes=features.inbound_bytes,
            outbound_bytes=features.outbound_bytes,
            fan_in_count=features.fan_in_count,
            fan_out_count=features.fan_out_count,
            fan_in_ratio=features.fan_in_ratio,
            unique_dst_ports=features.unique_dst_ports,
            unique_src_ports=features.unique_src_ports,
            well_known_port_ratio=features.well_known_port_ratio,
            ephemeral_port_ratio=features.ephemeral_port_ratio,
            persistent_listener_ports=features.persistent_listener_ports,
            protocol_distribution=features.protocol_distribution,
            avg_flow_duration_ms=features.avg_flow_duration_ms,
            avg_packets_per_flow=features.avg_packets_per_flow,
            avg_bytes_per_packet=features.avg_bytes_per_packet,
            connection_churn_rate=features.connection_churn_rate,
            active_hours_count=features.active_hours_count,
            business_hours_ratio=features.business_hours_ratio,
            traffic_variance=features.traffic_variance,
            has_db_ports=features.has_db_ports,
            has_storage_ports=features.has_storage_ports,
            has_web_ports=features.has_web_ports,
            has_ssh_ports=features.has_ssh_ports,
        )
        db.add(feature_record)

    async def _update_asset_type(
        self,
        db: AsyncSession,
        asset: Asset,
        result: ClassificationResult,
    ) -> None:
        """Update asset type based on classification.

        Args:
            db: Database session.
            asset: Asset to update.
            result: Classification result.
        """
        now = datetime.now(timezone.utc)
        previous_type = None
        if asset.asset_type:
            previous_type = asset.asset_type.value if hasattr(asset.asset_type, 'value') else str(asset.asset_type)
        new_type = result.recommended_type.value if hasattr(result.recommended_type, 'value') else str(result.recommended_type)

        # Map ClassifiableAssetType to AssetType
        asset_type_mapping = {
            # Compute
            "server": AssetType.SERVER,
            "workstation": AssetType.WORKSTATION,
            "virtual_machine": AssetType.VIRTUAL_MACHINE,
            "container": AssetType.CONTAINER,
            "cloud_service": AssetType.CLOUD_SERVICE,
            # Data
            "database": AssetType.DATABASE,
            "storage": AssetType.STORAGE,
            # Network
            "load_balancer": AssetType.LOAD_BALANCER,
            "network_device": AssetType.ROUTER,  # Map to router as closest match
            # Network Services (new)
            "dns_server": AssetType.DNS_SERVER,
            "dhcp_server": AssetType.DHCP_SERVER,
            "ntp_server": AssetType.NTP_SERVER,
            "directory_service": AssetType.DIRECTORY_SERVICE,
            # Communication (new)
            "mail_server": AssetType.MAIL_SERVER,
            "voip_server": AssetType.VOIP_SERVER,
            # Security & Access (new)
            "vpn_gateway": AssetType.VPN_GATEWAY,
            "proxy_server": AssetType.PROXY_SERVER,
            "log_collector": AssetType.LOG_COLLECTOR,
            "remote_access": AssetType.REMOTE_ACCESS,
            # Endpoints (new)
            "printer": AssetType.PRINTER,
            "iot_device": AssetType.IOT_DEVICE,
            "ip_camera": AssetType.IP_CAMERA,
            # Application Infrastructure (new)
            "message_queue": AssetType.MESSAGE_QUEUE,
            "monitoring_server": AssetType.MONITORING_SERVER,
            # Default
            "unknown": AssetType.UNKNOWN,
        }

        new_asset_type = asset_type_mapping.get(new_type, AssetType.UNKNOWN)

        # Skip if no change
        if asset.asset_type == new_asset_type:
            return

        # Update asset
        asset.asset_type = new_asset_type
        # Set classification method based on hybrid result
        if isinstance(result, HybridClassificationResult):
            asset.classification_method = result.classification_method
        else:
            asset.classification_method = "auto"

        # Record in history
        history = ClassificationHistory(
            id=uuid.uuid4(),
            asset_id=asset.id,
            classified_at=now,
            previous_type=previous_type,
            new_type=new_type,
            confidence=result.confidence,
            scores={k.value: v.to_dict() for k, v in result.scores.items()},
            features_snapshot=result.features_summary,
            triggered_by="auto",
        )
        db.add(history)

        self._update_count += 1
        CLASSIFICATION_UPDATES.labels(
            from_type=previous_type or "none",
            to_type=new_type,
        ).inc()

        logger.info(
            "Asset type updated",
            asset_id=str(asset.id),
            ip=asset.ip_address,
            previous=previous_type,
            new=new_type,
            confidence=result.confidence,
        )

    async def classify_single(self, asset_id: uuid.UUID) -> ClassificationResult | None:
        """Classify a single asset on-demand.

        Args:
            asset_id: Asset ID to classify.

        Returns:
            Classification result or None if asset not found.
        """
        async with get_session() as db:
            result = await db.execute(
                select(Asset).where(Asset.id == asset_id)
            )
            asset = result.scalar_one_or_none()

            if not asset:
                return None

            # Extract features
            extractor = FeatureExtractor(db)
            features = await extractor.extract_features(
                ip_address=asset.ip_address,
                window_size="5min",
            )

            # Compute scores
            classification = self._scoring_engine.compute_scores(
                features=features,
                current_type=asset.asset_type.value if asset.asset_type else None,
            )

            return classification

    @property
    def stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        return {
            "running": self._running,
            "processed_count": self._processed_count,
            "update_count": self._update_count,
        }
