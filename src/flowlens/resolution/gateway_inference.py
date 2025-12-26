"""Gateway inference service.

Processes gateway observations and maintains asset gateway relationships.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset, AssetType
from flowlens.models.gateway import AssetGateway, GatewayObservation, GatewayRole, InferenceMethod

logger = get_logger(__name__)


@dataclass
class GatewayCandidate:
    """Candidate gateway for an asset."""

    source_ip: str
    gateway_ip: str
    bytes_total: int
    flows_total: int
    first_seen: datetime
    last_seen: datetime
    observation_count: int


class GatewayInferenceService:
    """Infers gateway relationships from observations.

    Processes gateway observations created during flow aggregation
    and builds asset-level gateway relationships with confidence scoring.
    """

    # Confidence thresholds
    MIN_FLOWS_FOR_CONFIDENCE = 10
    MIN_OBSERVATIONS_FOR_CONFIDENCE = 3
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    AUTO_CREATE_THRESHOLD = 0.6

    def __init__(self) -> None:
        """Initialize the inference service."""
        self._asset_cache: dict[str, UUID] = {}  # IP -> Asset ID cache

    async def process_observations(
        self,
        db: AsyncSession,
        batch_size: int = 1000,
    ) -> int:
        """Process pending gateway observations.

        Groups observations by source/gateway IP and creates or updates
        gateway relationships based on confidence scoring.

        Args:
            db: Database session.
            batch_size: Maximum observations to process.

        Returns:
            Number of gateway relationships created/updated.
        """
        # Aggregate unprocessed observations by source/gateway
        result = await db.execute(
            select(
                GatewayObservation.source_ip,
                GatewayObservation.gateway_ip,
                func.sum(GatewayObservation.bytes_total).label("bytes_total"),
                func.sum(GatewayObservation.flows_count).label("flows_total"),
                func.min(GatewayObservation.window_start).label("first_seen"),
                func.max(GatewayObservation.window_end).label("last_seen"),
                func.count().label("observation_count"),
            )
            .where(GatewayObservation.is_processed == False)
            .group_by(
                GatewayObservation.source_ip,
                GatewayObservation.gateway_ip,
            )
            .limit(batch_size)
        )

        grouped = result.fetchall()

        if not grouped:
            return 0

        processed = 0

        for row in grouped:
            candidate = GatewayCandidate(
                source_ip=str(row.source_ip),
                gateway_ip=str(row.gateway_ip),
                bytes_total=row.bytes_total or 0,
                flows_total=row.flows_total or 0,
                first_seen=row.first_seen,
                last_seen=row.last_seen,
                observation_count=row.observation_count or 0,
            )

            gateway_id = await self._process_gateway_candidate(db, candidate)
            if gateway_id:
                processed += 1

        # Mark observations as processed
        source_gateway_pairs = [(str(r.source_ip), str(r.gateway_ip)) for r in grouped]
        for src_ip, gw_ip in source_gateway_pairs:
            await db.execute(
                update(GatewayObservation)
                .where(
                    GatewayObservation.source_ip == src_ip,
                    GatewayObservation.gateway_ip == gw_ip,
                    GatewayObservation.is_processed == False,
                )
                .values(is_processed=True)
            )

        if processed > 0:
            logger.info(
                "Processed gateway observations",
                candidates=len(grouped),
                relationships_created=processed,
            )

        return processed

    async def _process_gateway_candidate(
        self,
        db: AsyncSession,
        candidate: GatewayCandidate,
    ) -> UUID | None:
        """Process a single gateway candidate.

        Args:
            db: Database session.
            candidate: Gateway candidate data.

        Returns:
            Gateway relationship ID if created/updated, None otherwise.
        """
        # Skip if source and gateway are the same
        if candidate.source_ip == candidate.gateway_ip:
            return None

        # Calculate confidence
        confidence, scores = self._calculate_confidence(candidate)

        # Skip low-confidence candidates
        if confidence < self.AUTO_CREATE_THRESHOLD:
            logger.debug(
                "Skipping low-confidence gateway",
                source=candidate.source_ip,
                gateway=candidate.gateway_ip,
                confidence=round(confidence, 2),
            )
            return None

        # Get or create source asset
        source_asset_id = await self._get_or_create_asset(db, candidate.source_ip)

        # Get or create gateway asset (as ROUTER type)
        gateway_asset_id = await self._get_or_create_asset(
            db,
            candidate.gateway_ip,
            asset_type=AssetType.ROUTER,
        )

        # Upsert gateway relationship
        return await self._upsert_gateway(
            db,
            source_asset_id=source_asset_id,
            gateway_asset_id=gateway_asset_id,
            candidate=candidate,
            confidence=confidence,
            scores=scores,
        )

    def _calculate_confidence(
        self,
        candidate: GatewayCandidate,
    ) -> tuple[float, dict]:
        """Calculate confidence score for gateway candidate.

        Uses multiple factors:
        - Flow count: More flows = higher confidence
        - Observation count: More observations = higher confidence
        - Time consistency: Longer observation period = higher confidence
        - Bytes volume: More traffic = higher confidence

        Args:
            candidate: Gateway candidate data.

        Returns:
            Tuple of (confidence, breakdown dict).
        """
        scores = {}

        # Flow count factor (0-0.30)
        flow_score = min(candidate.flows_total / 100, 1.0) * 0.30
        scores["flow_count"] = round(flow_score, 3)

        # Observation count factor (0-0.30)
        obs_score = min(candidate.observation_count / 10, 1.0) * 0.30
        scores["observation_count"] = round(obs_score, 3)

        # Time consistency factor (0-0.20) - based on observation spread
        time_span = (candidate.last_seen - candidate.first_seen).total_seconds()
        consistency_score = min(time_span / 86400, 1.0) * 0.20  # 24h = full score
        scores["time_consistency"] = round(consistency_score, 3)

        # Bytes volume factor (0-0.20)
        bytes_score = min(candidate.bytes_total / 1_000_000, 1.0) * 0.20  # 1MB = full score
        scores["bytes_volume"] = round(bytes_score, 3)

        total = sum(scores.values())

        return round(total, 3), scores

    async def _get_or_create_asset(
        self,
        db: AsyncSession,
        ip: str,
        asset_type: AssetType = AssetType.UNKNOWN,
    ) -> UUID:
        """Get existing asset or create new one.

        Args:
            db: Database session.
            ip: IP address.
            asset_type: Type for new assets (default: UNKNOWN).

        Returns:
            Asset ID.
        """
        # Check cache
        if ip in self._asset_cache:
            return self._asset_cache[ip]

        # Check database
        result = await db.execute(
            select(Asset.id)
            .where(Asset.ip_address == ip, Asset.deleted_at.is_(None))
        )
        existing = result.scalar_one_or_none()

        if existing:
            self._asset_cache[ip] = existing
            return existing

        # Create new asset
        asset = Asset(
            id=uuid4(),
            name=ip.replace(".", "-"),
            ip_address=ip,
            asset_type=asset_type,
            is_internal=True,  # Gateways are typically internal
        )
        db.add(asset)
        await db.flush()

        self._asset_cache[ip] = asset.id

        logger.info(
            "Created gateway asset",
            ip=ip,
            asset_type=asset_type.value,
            asset_id=str(asset.id),
        )

        return asset.id

    async def _upsert_gateway(
        self,
        db: AsyncSession,
        source_asset_id: UUID,
        gateway_asset_id: UUID,
        candidate: GatewayCandidate,
        confidence: float,
        scores: dict,
    ) -> UUID:
        """Upsert gateway relationship.

        Args:
            db: Database session.
            source_asset_id: Source asset ID.
            gateway_asset_id: Gateway asset ID.
            candidate: Candidate data.
            confidence: Confidence score.
            scores: Confidence breakdown.

        Returns:
            Gateway relationship ID.
        """
        now = datetime.now(timezone.utc)

        # Check for existing relationship
        result = await db.execute(
            select(AssetGateway)
            .where(
                AssetGateway.source_asset_id == source_asset_id,
                AssetGateway.gateway_asset_id == gateway_asset_id,
                AssetGateway.destination_network.is_(None),
                AssetGateway.valid_to.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing relationship
            existing.bytes_total += candidate.bytes_total
            existing.flows_total += candidate.flows_total
            existing.last_seen = candidate.last_seen
            existing.confidence = confidence
            existing.confidence_scores = scores
            existing.last_inferred_at = now
            existing.updated_at = now

            logger.debug(
                "Updated gateway relationship",
                source=candidate.source_ip,
                gateway=candidate.gateway_ip,
                confidence=confidence,
            )

            return existing.id

        # Create new relationship
        gateway = AssetGateway(
            id=uuid4(),
            source_asset_id=source_asset_id,
            gateway_asset_id=gateway_asset_id,
            destination_network=None,  # Default gateway
            gateway_role=GatewayRole.PRIMARY.value,
            is_default_gateway=True,
            bytes_total=candidate.bytes_total,
            flows_total=candidate.flows_total,
            first_seen=candidate.first_seen,
            last_seen=candidate.last_seen,
            confidence=confidence,
            confidence_scores=scores,
            inference_method=InferenceMethod.NEXT_HOP.value,
            last_inferred_at=now,
            valid_from=now,
        )

        db.add(gateway)
        await db.flush()

        logger.info(
            "Created gateway relationship",
            source=candidate.source_ip,
            gateway=candidate.gateway_ip,
            confidence=confidence,
            gateway_id=str(gateway.id),
        )

        return gateway.id

    async def calculate_traffic_shares(
        self,
        db: AsyncSession,
    ) -> int:
        """Calculate traffic share percentages for each asset's gateways.

        For assets with multiple gateways, calculates what percentage
        of traffic goes through each gateway.

        Args:
            db: Database session.

        Returns:
            Number of gateways updated.
        """
        # Get all current gateways grouped by source
        result = await db.execute(
            select(
                AssetGateway.source_asset_id,
                func.sum(AssetGateway.bytes_total).label("total_bytes"),
            )
            .where(AssetGateway.valid_to.is_(None))
            .group_by(AssetGateway.source_asset_id)
        )

        totals = {row.source_asset_id: row.total_bytes for row in result.fetchall()}

        # Update traffic shares
        updated = 0
        for source_id, total_bytes in totals.items():
            if total_bytes == 0:
                continue

            gateways_result = await db.execute(
                select(AssetGateway)
                .where(
                    AssetGateway.source_asset_id == source_id,
                    AssetGateway.valid_to.is_(None),
                )
            )
            gateways = gateways_result.scalars().all()

            for gw in gateways:
                share = gw.bytes_total / total_bytes
                gw.traffic_share = round(share, 4)
                updated += 1

        return updated

    def clear_cache(self) -> None:
        """Clear the asset ID cache."""
        self._asset_cache.clear()
