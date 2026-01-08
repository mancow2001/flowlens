"""Baseline monitoring service for detecting deviations.

Compares active baselines against current state and generates
change events for alerting.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, EntryPoint
from flowlens.models.baseline import ApplicationBaseline
from flowlens.models.change import ChangeEvent, ChangeType
from flowlens.models.dependency import Dependency

logger = get_logger(__name__)


class BaselineMonitorService:
    """Service for monitoring baseline deviations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_all_baselines(self) -> list[ChangeEvent]:
        """Check all active baselines for deviations.

        Returns:
            List of generated change events
        """
        # Get all active baselines
        result = await self.db.execute(
            select(ApplicationBaseline)
            .where(ApplicationBaseline.is_active == True)
            .options(selectinload(ApplicationBaseline.application))
        )
        baselines = result.scalars().all()

        all_events = []
        for baseline in baselines:
            try:
                events = await self.check_baseline(baseline)
                all_events.extend(events)
            except Exception as e:
                logger.error(
                    "Failed to check baseline",
                    baseline_id=str(baseline.id),
                    error=str(e),
                )

        return all_events

    async def check_baseline(
        self,
        baseline: ApplicationBaseline,
        create_events: bool = True,
    ) -> list[ChangeEvent]:
        """Check a single baseline for deviations.

        Args:
            baseline: The baseline to check
            create_events: Whether to create change events (default True)

        Returns:
            List of generated change events
        """
        events = []
        now = datetime.now(timezone.utc)

        # Get current state
        current_snapshot = await self._capture_current_state(baseline.application_id)

        # Compare dependencies
        baseline_deps = {d["id"]: d for d in baseline.snapshot.get("dependencies", [])}
        current_deps = {d["id"]: d for d in current_snapshot["dependencies"]}

        # Dependencies added
        for dep_id, dep in current_deps.items():
            if dep_id not in baseline_deps:
                event = self._create_change_event(
                    change_type=ChangeType.BASELINE_DEPENDENCY_ADDED,
                    application_id=baseline.application_id,
                    baseline_id=baseline.id,
                    dependency_id=uuid.UUID(dep_id),
                    source_asset_id=uuid.UUID(dep["source_asset_id"]),
                    target_asset_id=uuid.UUID(dep["target_asset_id"]),
                    summary=f"New dependency detected vs baseline '{baseline.name}'",
                    description=f"Port {dep['target_port']}/{dep['protocol']}",
                    new_state=dep,
                    detected_at=now,
                )
                events.append(event)

        # Dependencies removed
        for dep_id, dep in baseline_deps.items():
            if dep_id not in current_deps:
                event = self._create_change_event(
                    change_type=ChangeType.BASELINE_DEPENDENCY_REMOVED,
                    application_id=baseline.application_id,
                    baseline_id=baseline.id,
                    dependency_id=uuid.UUID(dep_id),
                    source_asset_id=uuid.UUID(dep["source_asset_id"]),
                    target_asset_id=uuid.UUID(dep["target_asset_id"]),
                    summary=f"Dependency removed vs baseline '{baseline.name}'",
                    description=f"Port {dep['target_port']}/{dep['protocol']}",
                    previous_state=dep,
                    detected_at=now,
                )
                events.append(event)

        # Compare entry points
        baseline_eps = {
            f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
            for ep in baseline.snapshot.get("entry_points", [])
        }
        current_eps = {
            f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
            for ep in current_snapshot["entry_points"]
        }

        # Entry points added
        for ep_key, ep in current_eps.items():
            if ep_key not in baseline_eps:
                event = self._create_change_event(
                    change_type=ChangeType.BASELINE_ENTRY_POINT_ADDED,
                    application_id=baseline.application_id,
                    baseline_id=baseline.id,
                    asset_id=uuid.UUID(ep["asset_id"]),
                    summary=f"New entry point vs baseline '{baseline.name}'",
                    description=f"Port {ep['port']}/{ep['protocol']}",
                    new_state=ep,
                    detected_at=now,
                )
                events.append(event)

        # Entry points removed
        for ep_key, ep in baseline_eps.items():
            if ep_key not in current_eps:
                event = self._create_change_event(
                    change_type=ChangeType.BASELINE_ENTRY_POINT_REMOVED,
                    application_id=baseline.application_id,
                    baseline_id=baseline.id,
                    asset_id=uuid.UUID(ep["asset_id"]),
                    summary=f"Entry point removed vs baseline '{baseline.name}'",
                    description=f"Port {ep['port']}/{ep['protocol']}",
                    previous_state=ep,
                    detected_at=now,
                )
                events.append(event)

        # Compare members
        baseline_members = set(baseline.snapshot.get("member_asset_ids", []))
        current_members = set(current_snapshot["member_asset_ids"])

        # Members added
        for member_id in current_members - baseline_members:
            event = self._create_change_event(
                change_type=ChangeType.BASELINE_MEMBER_ADDED,
                application_id=baseline.application_id,
                baseline_id=baseline.id,
                asset_id=uuid.UUID(member_id),
                summary=f"New member added vs baseline '{baseline.name}'",
                detected_at=now,
            )
            events.append(event)

        # Members removed
        for member_id in baseline_members - current_members:
            event = self._create_change_event(
                change_type=ChangeType.BASELINE_MEMBER_REMOVED,
                application_id=baseline.application_id,
                baseline_id=baseline.id,
                asset_id=uuid.UUID(member_id),
                summary=f"Member removed vs baseline '{baseline.name}'",
                detected_at=now,
            )
            events.append(event)

        # Create events in database if requested
        if create_events and events:
            for event in events:
                self.db.add(event)
            await self.db.flush()
            logger.info(
                "Created baseline deviation events",
                baseline_id=str(baseline.id),
                event_count=len(events),
            )

        return events

    async def _capture_current_state(self, application_id: uuid.UUID) -> dict[str, Any]:
        """Capture current state of an application."""
        # Get application members
        members_result = await self.db.execute(
            select(ApplicationMember)
            .where(ApplicationMember.application_id == application_id)
            .options(selectinload(ApplicationMember.asset))
            .options(selectinload(ApplicationMember.entry_points))
        )
        members = members_result.scalars().all()
        member_asset_ids = [str(m.asset_id) for m in members]

        # Get dependencies
        if member_asset_ids:
            deps_result = await self.db.execute(
                select(Dependency)
                .where(
                    (Dependency.source_asset_id.in_([m.asset_id for m in members]))
                    | (Dependency.target_asset_id.in_([m.asset_id for m in members]))
                )
            )
            dependencies = deps_result.scalars().all()
        else:
            dependencies = []

        # Get entry points
        entry_points = []
        for member in members:
            for ep in member.entry_points:
                entry_points.append({
                    "id": str(ep.id),
                    "member_id": str(member.id),
                    "asset_id": str(member.asset_id),
                    "port": ep.port,
                    "protocol": ep.protocol,
                    "label": ep.label,
                })

        # Build dependencies snapshot
        deps_snapshot = []
        for dep in dependencies:
            deps_snapshot.append({
                "id": str(dep.id),
                "source_asset_id": str(dep.source_asset_id),
                "target_asset_id": str(dep.target_asset_id),
                "target_port": dep.target_port,
                "protocol": dep.protocol,
            })

        return {
            "dependencies": deps_snapshot,
            "entry_points": entry_points,
            "member_asset_ids": member_asset_ids,
        }

    def _create_change_event(
        self,
        change_type: ChangeType,
        application_id: uuid.UUID,
        baseline_id: uuid.UUID,
        summary: str,
        detected_at: datetime,
        dependency_id: uuid.UUID | None = None,
        asset_id: uuid.UUID | None = None,
        source_asset_id: uuid.UUID | None = None,
        target_asset_id: uuid.UUID | None = None,
        description: str | None = None,
        previous_state: dict | None = None,
        new_state: dict | None = None,
    ) -> ChangeEvent:
        """Create a change event for a baseline deviation."""
        return ChangeEvent(
            change_type=change_type,
            detected_at=detected_at,
            application_id=application_id,
            baseline_id=baseline_id,
            dependency_id=dependency_id,
            asset_id=asset_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            summary=summary,
            description=description,
            previous_state=previous_state,
            new_state=new_state,
            impact_score=self._calculate_impact_score(change_type),
        )

    def _calculate_impact_score(self, change_type: ChangeType) -> int:
        """Calculate impact score based on change type."""
        scores = {
            ChangeType.BASELINE_DEPENDENCY_ADDED: 30,
            ChangeType.BASELINE_DEPENDENCY_REMOVED: 50,
            ChangeType.BASELINE_TRAFFIC_DEVIATION: 20,
            ChangeType.BASELINE_ENTRY_POINT_ADDED: 40,
            ChangeType.BASELINE_ENTRY_POINT_REMOVED: 60,
            ChangeType.BASELINE_MEMBER_ADDED: 25,
            ChangeType.BASELINE_MEMBER_REMOVED: 45,
        }
        return scores.get(change_type, 10)


async def check_baseline_deviations(db: AsyncSession) -> list[ChangeEvent]:
    """Utility function to check all baseline deviations.

    Can be called from a scheduled task or manually.
    """
    service = BaselineMonitorService(db)
    return await service.check_all_baselines()
