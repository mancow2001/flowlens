"""Change detection for dependency resolution.

Detects new, stale, and changed dependencies and assets,
generating change events and alerts.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import ResolutionSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import CHANGES_DETECTED
from flowlens.models.asset import Asset
from flowlens.models.change import Alert, AlertSeverity, ChangeEvent, ChangeType
from flowlens.models.dependency import Dependency

logger = get_logger(__name__)


class ChangeDetector:
    """Detects changes in the dependency graph.

    Monitors for:
    - New dependencies (first-time connections)
    - Stale dependencies (no traffic for threshold period)
    - Asset state changes (online/offline)
    - Traffic anomalies (spikes/drops)
    """

    def __init__(self, settings: ResolutionSettings | None = None) -> None:
        """Initialize change detector.

        Args:
            settings: Resolution settings.
        """
        if settings is None:
            settings = get_settings().resolution

        self._stale_threshold_hours = settings.stale_threshold_hours
        self._traffic_spike_threshold = 2.0  # 2x baseline
        self._traffic_drop_threshold = 0.5  # 50% of baseline

    async def detect_stale_dependencies(
        self,
        db: AsyncSession,
        threshold_hours: int | None = None,
    ) -> list[UUID]:
        """Detect dependencies with no recent traffic.

        Args:
            db: Database session.
            threshold_hours: Hours since last activity to consider stale.

        Returns:
            List of stale dependency IDs.
        """
        if threshold_hours is None:
            threshold_hours = self._stale_threshold_hours

        cutoff = datetime.utcnow() - timedelta(hours=threshold_hours)

        result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.last_seen < cutoff,
                Dependency.valid_to.is_(None),
                Dependency.is_ignored == False,
            )
            .limit(1000)
        )

        stale_ids = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected stale dependencies",
            count=len(stale_ids),
            threshold_hours=threshold_hours,
        )

        return stale_ids

    async def detect_offline_assets(
        self,
        db: AsyncSession,
        threshold_hours: int = 24,
    ) -> list[UUID]:
        """Detect assets with no recent activity.

        Args:
            db: Database session.
            threshold_hours: Hours since last activity.

        Returns:
            List of offline asset IDs.
        """
        cutoff = datetime.utcnow() - timedelta(hours=threshold_hours)

        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.last_seen < cutoff,
                Asset.deleted_at.is_(None),
            )
            .limit(1000)
        )

        offline_ids = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected offline assets",
            count=len(offline_ids),
            threshold_hours=threshold_hours,
        )

        return offline_ids

    async def create_change_event(
        self,
        db: AsyncSession,
        change_type: ChangeType,
        summary: str,
        description: str | None = None,
        asset_id: UUID | None = None,
        dependency_id: UUID | None = None,
        source_asset_id: UUID | None = None,
        target_asset_id: UUID | None = None,
        previous_state: dict | None = None,
        new_state: dict | None = None,
        impact_score: int = 0,
        affected_assets_count: int = 0,
        occurred_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> ChangeEvent:
        """Create a change event record.

        Args:
            db: Database session.
            change_type: Type of change.
            summary: Brief summary of the change.
            description: Detailed description.
            asset_id: Related asset ID.
            dependency_id: Related dependency ID.
            source_asset_id: Source asset for dependency changes.
            target_asset_id: Target asset for dependency changes.
            previous_state: State before change.
            new_state: State after change.
            impact_score: Impact severity (0-100).
            affected_assets_count: Number of affected assets.
            occurred_at: When the change occurred.
            metadata: Additional metadata.

        Returns:
            Created change event.
        """
        event = ChangeEvent(
            change_type=change_type,
            summary=summary,
            description=description,
            asset_id=asset_id,
            dependency_id=dependency_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            previous_state=previous_state,
            new_state=new_state,
            impact_score=impact_score,
            affected_assets_count=affected_assets_count,
            occurred_at=occurred_at,
            metadata=metadata or {},
        )

        db.add(event)
        await db.flush()

        CHANGES_DETECTED.labels(change_type=change_type.value).inc()

        logger.info(
            "Created change event",
            event_id=str(event.id),
            change_type=change_type.value,
            summary=summary,
        )

        return event

    async def create_alert_from_event(
        self,
        db: AsyncSession,
        event: ChangeEvent,
        severity: AlertSeverity | None = None,
        title: str | None = None,
        message: str | None = None,
    ) -> Alert:
        """Create an alert from a change event.

        Args:
            db: Database session.
            event: Source change event.
            severity: Alert severity (auto-determined if not provided).
            title: Alert title (derived from event if not provided).
            message: Alert message (derived from event if not provided).

        Returns:
            Created alert.
        """
        # Auto-determine severity based on change type and impact
        if severity is None:
            severity = self._determine_severity(event)

        # Generate title if not provided
        if title is None:
            title = self._generate_alert_title(event)

        # Generate message if not provided
        if message is None:
            message = self._generate_alert_message(event)

        alert = Alert(
            change_event_id=event.id,
            severity=severity,
            title=title,
            message=message,
            asset_id=event.asset_id,
            dependency_id=event.dependency_id,
        )

        db.add(alert)
        await db.flush()

        logger.info(
            "Created alert",
            alert_id=str(alert.id),
            severity=severity.value,
            title=title,
        )

        return alert

    def _determine_severity(self, event: ChangeEvent) -> AlertSeverity:
        """Determine alert severity from change event.

        Args:
            event: Change event.

        Returns:
            Appropriate severity level.
        """
        # Critical events
        if event.change_type in (
            ChangeType.CRITICAL_PATH_CHANGE,
            ChangeType.ASSET_OFFLINE,
        ):
            return AlertSeverity.CRITICAL

        # Error-level events
        if event.change_type in (
            ChangeType.DEPENDENCY_REMOVED,
            ChangeType.ASSET_REMOVED,
            ChangeType.DEPENDENCY_TRAFFIC_DROP,
        ):
            return AlertSeverity.ERROR

        # Warning-level events
        if event.change_type in (
            ChangeType.DEPENDENCY_STALE,
            ChangeType.DEPENDENCY_TRAFFIC_SPIKE,
            ChangeType.NEW_EXTERNAL_CONNECTION,
        ):
            return AlertSeverity.WARNING

        # Info-level for new discoveries
        if event.change_type in (
            ChangeType.DEPENDENCY_CREATED,
            ChangeType.ASSET_DISCOVERED,
            ChangeType.SERVICE_DISCOVERED,
            ChangeType.ASSET_ONLINE,
        ):
            return AlertSeverity.INFO

        # Default based on impact score
        if event.impact_score >= 70:
            return AlertSeverity.CRITICAL
        elif event.impact_score >= 50:
            return AlertSeverity.ERROR
        elif event.impact_score >= 30:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    def _generate_alert_title(self, event: ChangeEvent) -> str:
        """Generate alert title from change event.

        Args:
            event: Change event.

        Returns:
            Alert title.
        """
        type_titles = {
            ChangeType.DEPENDENCY_CREATED: "New Dependency Discovered",
            ChangeType.DEPENDENCY_REMOVED: "Dependency Removed",
            ChangeType.DEPENDENCY_STALE: "Stale Dependency Detected",
            ChangeType.DEPENDENCY_TRAFFIC_SPIKE: "Traffic Spike Detected",
            ChangeType.DEPENDENCY_TRAFFIC_DROP: "Traffic Drop Detected",
            ChangeType.ASSET_DISCOVERED: "New Asset Discovered",
            ChangeType.ASSET_REMOVED: "Asset Removed",
            ChangeType.ASSET_OFFLINE: "Asset Offline",
            ChangeType.ASSET_ONLINE: "Asset Back Online",
            ChangeType.SERVICE_DISCOVERED: "New Service Discovered",
            ChangeType.SERVICE_REMOVED: "Service Removed",
            ChangeType.NEW_EXTERNAL_CONNECTION: "New External Connection",
            ChangeType.CRITICAL_PATH_CHANGE: "Critical Path Changed",
        }

        return type_titles.get(event.change_type, "Topology Change Detected")

    def _generate_alert_message(self, event: ChangeEvent) -> str:
        """Generate alert message from change event.

        Args:
            event: Change event.

        Returns:
            Alert message.
        """
        message = event.summary

        if event.description:
            message += f"\n\n{event.description}"

        if event.affected_assets_count > 0:
            message += f"\n\nAffected assets: {event.affected_assets_count}"

        if event.previous_state or event.new_state:
            message += "\n\nChange details:"
            if event.previous_state:
                message += f"\n- Previous: {event.previous_state}"
            if event.new_state:
                message += f"\n- New: {event.new_state}"

        return message

    async def process_stale_dependencies(
        self,
        db: AsyncSession,
        stale_dep_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process stale dependencies - create events and optionally alerts.

        Args:
            db: Database session.
            stale_dep_ids: List of stale dependency IDs.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for dep_id in stale_dep_ids:
            # Get dependency details
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()

            if not dep:
                continue

            # Create change event
            event = await self.create_change_event(
                db,
                change_type=ChangeType.DEPENDENCY_STALE,
                summary=f"No traffic on dependency for {self._stale_threshold_hours}+ hours",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                previous_state={
                    "last_seen": dep.last_seen.isoformat(),
                    "bytes_total": dep.bytes_total,
                    "flows_total": dep.flows_total,
                },
                metadata={
                    "port": dep.target_port,
                    "protocol": dep.protocol,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)

            count += 1

        return count

    async def check_new_external_connections(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> list[UUID]:
        """Check for new connections to external assets.

        Args:
            db: Database session.
            since: Check for connections created after this time.

        Returns:
            List of dependency IDs for new external connections.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        # Find new dependencies where target is external
        result = await db.execute(
            select(Dependency.id)
            .join(Asset, Dependency.target_asset_id == Asset.id)
            .where(
                Dependency.first_seen >= since,
                Dependency.valid_to.is_(None),
                Asset.is_internal == False,
            )
        )

        new_external = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected new external connections",
            count=len(new_external),
            since=since.isoformat(),
        )

        return new_external

    async def run_detection_cycle(
        self,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Run a full detection cycle.

        Checks for:
        - Stale dependencies
        - Offline assets
        - New external connections

        Args:
            db: Database session.

        Returns:
            Summary of detected changes.
        """
        results = {
            "stale_dependencies": 0,
            "offline_assets": 0,
            "new_external_connections": 0,
            "events_created": 0,
            "alerts_created": 0,
        }

        # Detect stale dependencies
        stale_deps = await self.detect_stale_dependencies(db)
        results["stale_dependencies"] = len(stale_deps)

        if stale_deps:
            events_created = await self.process_stale_dependencies(
                db, stale_deps[:100]  # Limit batch size
            )
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect offline assets
        offline_assets = await self.detect_offline_assets(db)
        results["offline_assets"] = len(offline_assets)

        # Detect new external connections
        new_external = await self.check_new_external_connections(db)
        results["new_external_connections"] = len(new_external)

        logger.info(
            "Detection cycle complete",
            **results,
        )

        return results
