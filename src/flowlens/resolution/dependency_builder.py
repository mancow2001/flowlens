"""Dependency builder for resolution service.

Creates and updates dependency edges from flow aggregates.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import ResolutionSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import DEPENDENCIES_CREATED, DEPENDENCIES_UPDATED
from flowlens.enrichment.resolvers.geoip import PrivateIPClassifier
from flowlens.enrichment.resolvers.protocol import ProtocolResolver
from flowlens.models.dependency import Dependency, DependencyHistory
from flowlens.models.flow import FlowAggregate
from flowlens.resolution.asset_mapper import AssetMapper

logger = get_logger(__name__)


class DependencyBuilder:
    """Builds dependency graph from flow aggregates.

    Creates new dependencies for previously unseen connections
    and updates existing ones with new metrics.
    """

    def __init__(
        self,
        asset_mapper: AssetMapper | None = None,
        protocol_resolver: ProtocolResolver | None = None,
        settings: ResolutionSettings | None = None,
    ) -> None:
        """Initialize dependency builder.

        Args:
            asset_mapper: Asset mapper instance.
            protocol_resolver: Protocol resolver for service classification.
            settings: Resolution settings for filtering configuration.
        """
        self._asset_mapper = asset_mapper or AssetMapper()
        self._protocol_resolver = protocol_resolver or ProtocolResolver()
        self._settings = settings or get_settings().resolution
        self._ip_classifier = PrivateIPClassifier()

    def _should_exclude_external(
        self,
        src_ip: str,
        dst_ip: str,
    ) -> bool:
        """Check if this flow should be excluded based on external IP settings.

        Args:
            src_ip: Source IP address.
            dst_ip: Destination IP address.

        Returns:
            True if the flow should be excluded.
        """
        # If no exclusion settings are enabled, allow all
        if not (
            self._settings.exclude_external_ips
            or self._settings.exclude_external_sources
            or self._settings.exclude_external_targets
        ):
            return False

        src_is_external = not self._ip_classifier.is_private(src_ip)
        dst_is_external = not self._ip_classifier.is_private(dst_ip)

        # Exclude if either end is external and exclude_external_ips is set
        if self._settings.exclude_external_ips and (src_is_external or dst_is_external):
            return True

        # Exclude if source is external and exclude_external_sources is set
        if self._settings.exclude_external_sources and src_is_external:
            return True

        # Exclude if target is external and exclude_external_targets is set
        if self._settings.exclude_external_targets and dst_is_external:
            return True

        return False

    async def build_from_aggregate(
        self,
        db: AsyncSession,
        aggregate: FlowAggregate,
    ) -> UUID | None:
        """Build or update dependency from a flow aggregate.

        Args:
            db: Database session.
            aggregate: Flow aggregate to process.

        Returns:
            Dependency ID, or None if excluded.
        """
        src_ip = str(aggregate.src_ip)
        dst_ip = str(aggregate.dst_ip)

        # Check external IP exclusion settings
        if self._should_exclude_external(src_ip, dst_ip):
            logger.debug(
                "Skipping external IP dependency",
                src_ip=src_ip,
                dst_ip=dst_ip,
            )
            return None

        # Map to assets
        src_asset_id, dst_asset_id = await self._asset_mapper.map_aggregate_to_assets(
            db, aggregate
        )

        # Skip self-loops
        if src_asset_id == dst_asset_id:
            logger.debug(
                "Skipping self-loop",
                src_ip=src_ip,
                dst_ip=dst_ip,
            )
            return None

        # Get or create dependency
        dep_id = await self._upsert_dependency(
            db,
            source_asset_id=src_asset_id,
            target_asset_id=dst_asset_id,
            target_port=aggregate.dst_port,
            protocol=aggregate.protocol,
            bytes_count=aggregate.bytes_total,
            packets_count=aggregate.packets_total,
            flows_count=aggregate.flows_count,
            window_start=aggregate.window_start,
            window_end=aggregate.window_end,
        )

        return dep_id

    async def _upsert_dependency(
        self,
        db: AsyncSession,
        source_asset_id: UUID,
        target_asset_id: UUID,
        target_port: int,
        protocol: int,
        bytes_count: int,
        packets_count: int,
        flows_count: int,
        window_start: datetime,
        window_end: datetime,
    ) -> UUID:
        """Upsert a dependency edge.

        Args:
            db: Database session.
            source_asset_id: Source asset ID.
            target_asset_id: Target asset ID.
            target_port: Destination port.
            protocol: IP protocol number.
            bytes_count: Bytes in this window.
            packets_count: Packets in this window.
            flows_count: Flow count in this window.
            window_start: Aggregation window start.
            window_end: Aggregation window end.

        Returns:
            Dependency ID.
        """
        # Infer dependency type from protocol/port
        service_info = self._protocol_resolver.resolve(target_port, protocol)
        dependency_type = service_info.category if service_info else None

        # Check if dependency exists
        result = await db.execute(
            select(Dependency.id, Dependency.bytes_total, Dependency.first_seen)
            .where(
                Dependency.source_asset_id == source_asset_id,
                Dependency.target_asset_id == target_asset_id,
                Dependency.target_port == target_port,
                Dependency.protocol == protocol,
                Dependency.valid_to.is_(None),
            )
        )
        existing = result.first()

        if existing:
            # Update existing dependency
            dep_id, _, _ = existing
            await self._update_dependency(
                db,
                dep_id=dep_id,
                bytes_count=bytes_count,
                packets_count=packets_count,
                flows_count=flows_count,
                last_seen=window_end,
                source_asset_id=source_asset_id,
                target_asset_id=target_asset_id,
                target_port=target_port,
                protocol=protocol,
            )
            return dep_id

        # Create new dependency - set rolling window bytes to initial value
        new_dep = Dependency(
            id=uuid4(),
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            target_port=target_port,
            protocol=protocol,
            bytes_total=bytes_count,
            packets_total=packets_count,
            flows_total=flows_count,
            bytes_last_24h=bytes_count,  # Initial value is current bytes
            bytes_last_7d=bytes_count,   # Initial value is current bytes
            first_seen=window_start,
            last_seen=window_end,
            dependency_type=dependency_type,
            valid_from=window_start,
        )

        db.add(new_dep)
        await db.flush()

        # Record history
        await self._record_history(
            db,
            dependency_id=new_dep.id,
            change_type="created",
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            target_port=target_port,
            protocol=protocol,
            bytes_total=bytes_count,
            flows_total=flows_count,
            reason="New dependency discovered",
        )

        logger.info(
            "Created new dependency",
            dep_id=str(new_dep.id),
            source=str(source_asset_id),
            target=str(target_asset_id),
            port=target_port,
            protocol=protocol,
        )

        DEPENDENCIES_CREATED.inc()

        return new_dep.id

    async def _calculate_rolling_bytes(
        self,
        db: AsyncSession,
        source_asset_id: UUID,
        target_asset_id: UUID,
        target_port: int,
        protocol: int,
    ) -> tuple[int, int]:
        """Calculate bytes for rolling time windows from flow aggregates.

        Args:
            db: Database session.
            source_asset_id: Source asset ID.
            target_asset_id: Target asset ID.
            target_port: Target port.
            protocol: Protocol number.

        Returns:
            Tuple of (bytes_last_24h, bytes_last_7d).
        """
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)

        # Get source and target asset IPs for aggregate lookup
        from flowlens.models.asset import Asset

        result = await db.execute(
            select(Asset.ip_address).where(Asset.id == source_asset_id)
        )
        src_row = result.first()
        src_ip = str(src_row[0]) if src_row else None

        result = await db.execute(
            select(Asset.ip_address).where(Asset.id == target_asset_id)
        )
        dst_row = result.first()
        dst_ip = str(dst_row[0]) if dst_row else None

        if not src_ip or not dst_ip:
            return 0, 0

        # Query flow aggregates for rolling windows
        # 24h window
        result_24h = await db.execute(
            select(func.coalesce(func.sum(FlowAggregate.bytes_total), 0))
            .where(
                FlowAggregate.src_ip == src_ip,
                FlowAggregate.dst_ip == dst_ip,
                FlowAggregate.dst_port == target_port,
                FlowAggregate.protocol == protocol,
                FlowAggregate.window_start >= cutoff_24h,
            )
        )
        bytes_24h = result_24h.scalar() or 0

        # 7d window
        result_7d = await db.execute(
            select(func.coalesce(func.sum(FlowAggregate.bytes_total), 0))
            .where(
                FlowAggregate.src_ip == src_ip,
                FlowAggregate.dst_ip == dst_ip,
                FlowAggregate.dst_port == target_port,
                FlowAggregate.protocol == protocol,
                FlowAggregate.window_start >= cutoff_7d,
            )
        )
        bytes_7d = result_7d.scalar() or 0

        return int(bytes_24h), int(bytes_7d)

    async def _update_dependency(
        self,
        db: AsyncSession,
        dep_id: UUID,
        bytes_count: int,
        packets_count: int,
        flows_count: int,
        last_seen: datetime,
        source_asset_id: UUID | None = None,
        target_asset_id: UUID | None = None,
        target_port: int | None = None,
        protocol: int | None = None,
    ) -> None:
        """Update dependency metrics.

        Args:
            db: Database session.
            dep_id: Dependency ID.
            bytes_count: Bytes to add.
            packets_count: Packets to add.
            flows_count: Flows to add.
            last_seen: New last_seen timestamp.
            source_asset_id: Source asset ID (for rolling window calculation).
            target_asset_id: Target asset ID (for rolling window calculation).
            target_port: Target port (for rolling window calculation).
            protocol: Protocol (for rolling window calculation).
        """
        update_values = {
            "bytes_total": Dependency.bytes_total + bytes_count,
            "packets_total": Dependency.packets_total + packets_count,
            "flows_total": Dependency.flows_total + flows_count,
            "last_seen": func.greatest(Dependency.last_seen, last_seen),
        }

        # Calculate rolling window bytes if we have the required info
        if source_asset_id and target_asset_id and target_port is not None and protocol is not None:
            bytes_24h, bytes_7d = await self._calculate_rolling_bytes(
                db, source_asset_id, target_asset_id, target_port, protocol
            )
            # Add current bytes_count since aggregate may not include it yet
            update_values["bytes_last_24h"] = bytes_24h + bytes_count
            update_values["bytes_last_7d"] = bytes_7d + bytes_count

        await db.execute(
            update(Dependency)
            .where(Dependency.id == dep_id)
            .values(**update_values)
        )

        DEPENDENCIES_UPDATED.inc()

    async def _record_history(
        self,
        db: AsyncSession,
        dependency_id: UUID,
        change_type: str,
        source_asset_id: UUID,
        target_asset_id: UUID,
        target_port: int,
        protocol: int,
        bytes_total: int,
        flows_total: int,
        reason: str | None = None,
        triggered_by: str = "system",
        previous_state: dict | None = None,
        new_state: dict | None = None,
    ) -> None:
        """Record dependency change in history.

        Args:
            db: Database session.
            dependency_id: Dependency ID.
            change_type: Type of change.
            source_asset_id: Source asset.
            target_asset_id: Target asset.
            target_port: Port number.
            protocol: Protocol number.
            bytes_total: Total bytes.
            flows_total: Total flows.
            reason: Reason for change.
            triggered_by: Who/what triggered change.
            previous_state: State before change.
            new_state: State after change.
        """
        history = DependencyHistory(
            dependency_id=dependency_id,
            change_type=change_type,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            target_port=target_port,
            protocol=protocol,
            bytes_total=bytes_total,
            flows_total=flows_total,
            reason=reason,
            triggered_by=triggered_by,
            previous_state=previous_state,
            new_state=new_state,
        )

        db.add(history)

    async def build_batch(
        self,
        db: AsyncSession,
        aggregates: list[FlowAggregate],
    ) -> int:
        """Build dependencies from multiple aggregates.

        Args:
            db: Database session.
            aggregates: List of flow aggregates.

        Returns:
            Number of dependencies processed.
        """
        count = 0
        for aggregate in aggregates:
            try:
                await self.build_from_aggregate(db, aggregate)
                count += 1
            except Exception as e:
                logger.warning(
                    "Failed to build dependency from aggregate",
                    error=str(e),
                    src_ip=str(aggregate.src_ip),
                    dst_ip=str(aggregate.dst_ip),
                )

        return count

    async def close_stale_dependency(
        self,
        db: AsyncSession,
        dep_id: UUID,
        reason: str = "No traffic observed",
    ) -> None:
        """Mark a dependency as stale/closed.

        Sets valid_to to close the temporal validity window.

        Args:
            db: Database session.
            dep_id: Dependency to close.
            reason: Reason for closing.
        """
        now = datetime.utcnow()

        # Get current state for history
        result = await db.execute(
            select(Dependency).where(Dependency.id == dep_id)
        )
        dep = result.scalar_one_or_none()

        if not dep or dep.valid_to:
            return

        # Close the dependency
        await db.execute(
            update(Dependency)
            .where(Dependency.id == dep_id)
            .values(valid_to=now)
        )

        # Record history
        await self._record_history(
            db,
            dependency_id=dep_id,
            change_type="stale",
            source_asset_id=dep.source_asset_id,
            target_asset_id=dep.target_asset_id,
            target_port=dep.target_port,
            protocol=dep.protocol,
            bytes_total=dep.bytes_total,
            flows_total=dep.flows_total,
            reason=reason,
            triggered_by="system",
        )

        logger.info(
            "Closed stale dependency",
            dep_id=str(dep_id),
            reason=reason,
        )

    async def refresh_rolling_bytes(
        self,
        db: AsyncSession,
        batch_size: int = 100,
    ) -> int:
        """Refresh bytes_last_24h and bytes_last_7d for all active dependencies.

        This is useful for backfilling existing dependencies that don't have
        rolling window metrics populated.

        Args:
            db: Database session.
            batch_size: Number of dependencies to process per batch.

        Returns:
            Number of dependencies updated.
        """
        from flowlens.models.asset import Asset

        # Get all active dependencies
        result = await db.execute(
            select(
                Dependency.id,
                Dependency.source_asset_id,
                Dependency.target_asset_id,
                Dependency.target_port,
                Dependency.protocol,
            )
            .where(Dependency.valid_to.is_(None))
        )
        dependencies = result.fetchall()

        updated = 0
        for dep_id, source_id, target_id, port, proto in dependencies:
            bytes_24h, bytes_7d = await self._calculate_rolling_bytes(
                db, source_id, target_id, port, proto
            )

            await db.execute(
                update(Dependency)
                .where(Dependency.id == dep_id)
                .values(
                    bytes_last_24h=bytes_24h,
                    bytes_last_7d=bytes_7d,
                )
            )
            updated += 1

            if updated % batch_size == 0:
                await db.flush()
                logger.debug(f"Refreshed rolling bytes for {updated} dependencies")

        await db.flush()
        logger.info(f"Refreshed rolling bytes for {updated} total dependencies")

        return updated

    @property
    def asset_mapper(self) -> AssetMapper:
        """Get asset mapper instance."""
        return self._asset_mapper
