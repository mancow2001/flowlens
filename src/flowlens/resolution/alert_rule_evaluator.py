"""Alert rule evaluation service.

Evaluates change events against configured alert rules to determine
which alerts should be created and how they should be configured.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.models.alert_rule import AlertRule
from flowlens.models.asset import Asset
from flowlens.models.change import AlertSeverity, ChangeEvent
from flowlens.models.maintenance_window import MaintenanceWindow

logger = get_logger(__name__)


@dataclass
class RuleEvaluationResult:
    """Result of evaluating alert rules for a change event."""

    should_create_alert: bool
    matching_rule: AlertRule | None = None
    rendered_title: str | None = None
    rendered_description: str | None = None
    severity: AlertSeverity | None = None
    notify_channels: list[str] | None = None
    suppression_reason: str | None = None


@dataclass
class AlertContext:
    """Context data for alert template rendering."""

    change_type: str
    summary: str
    description: str | None
    asset_name: str | None
    asset_ip: str | None
    asset_type: str | None
    environment: str | None
    datacenter: str | None
    impact_score: int
    affected_assets_count: int

    def to_dict(self) -> dict:
        """Convert to dictionary for template rendering."""
        return {
            "change_type": self.change_type.replace("_", " ").title(),
            "summary": self.summary,
            "description": self.description or "",
            "asset_name": self.asset_name or "Unknown",
            "asset_ip": self.asset_ip or "Unknown",
            "asset_type": self.asset_type or "Unknown",
            "environment": self.environment or "Unknown",
            "datacenter": self.datacenter or "Unknown",
            "impact_score": self.impact_score,
            "affected_assets_count": self.affected_assets_count,
        }


class AlertRuleEvaluator:
    """Evaluates change events against alert rules.

    Handles:
    - Matching change events to active alert rules
    - Checking maintenance window suppression
    - Applying cooldown periods
    - Rendering alert templates
    """

    async def evaluate(
        self,
        db: AsyncSession,
        event: ChangeEvent,
        asset: Asset | None = None,
    ) -> RuleEvaluationResult:
        """Evaluate a change event against all active alert rules.

        Args:
            db: Database session.
            event: The change event to evaluate.
            asset: Optional pre-loaded asset for the event.

        Returns:
            RuleEvaluationResult with matching rule info and rendered content.
        """
        # Get the asset if not provided
        if asset is None and event.asset_id:
            result = await db.execute(
                select(Asset).where(Asset.id == event.asset_id)
            )
            asset = result.scalar_one_or_none()

        # Check if asset is in maintenance
        suppression = await self._check_maintenance_suppression(
            db, event, asset
        )
        if suppression:
            logger.debug(
                "Alert suppressed by maintenance window",
                event_id=str(event.id),
                reason=suppression,
            )
            return RuleEvaluationResult(
                should_create_alert=False,
                suppression_reason=suppression,
            )

        # Get active alert rules ordered by priority
        change_type_str = (
            event.change_type.value
            if hasattr(event.change_type, "value")
            else str(event.change_type)
        )

        result = await db.execute(
            select(AlertRule)
            .where(
                AlertRule.is_active == True,
                AlertRule.change_types.any(change_type_str),
            )
            .order_by(AlertRule.priority.asc())
        )
        rules = result.scalars().all()

        if not rules:
            # No matching rules - use default behavior
            logger.debug(
                "No alert rules match change type",
                change_type=change_type_str,
            )
            return RuleEvaluationResult(
                should_create_alert=True,
                matching_rule=None,
            )

        # Build asset data for filter matching
        asset_data = self._build_asset_data(asset) if asset else {}

        # Find first matching rule (by priority)
        for rule in rules:
            # Check asset filter
            if not rule.matches_asset_filter(asset_data):
                logger.debug(
                    "Rule asset filter did not match",
                    rule=rule.name,
                    asset_id=str(asset.id) if asset else None,
                )
                continue

            # Check schedule (if configured)
            if not self._is_rule_scheduled(rule):
                logger.debug(
                    "Rule not active per schedule",
                    rule=rule.name,
                )
                continue

            # Check cooldown
            if rule.is_on_cooldown():
                logger.debug(
                    "Rule is on cooldown",
                    rule=rule.name,
                    cooldown_minutes=rule.cooldown_minutes,
                    last_triggered=rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                )
                continue

            # Rule matches! Build context and render templates
            context = self._build_context(event, asset)
            context_dict = context.to_dict()

            rendered_title = rule.render_title(context_dict)
            rendered_description = rule.render_description(context_dict)

            # Mark rule as triggered
            rule.trigger()
            await db.flush()

            logger.info(
                "Alert rule matched",
                rule=rule.name,
                change_type=change_type_str,
                severity=rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity),
            )

            return RuleEvaluationResult(
                should_create_alert=True,
                matching_rule=rule,
                rendered_title=rendered_title,
                rendered_description=rendered_description,
                severity=rule.severity,
                notify_channels=rule.notify_channels,
            )

        # All matching rules are on cooldown or filtered out
        logger.debug(
            "All matching rules filtered out (cooldown/filter/schedule)",
            change_type=change_type_str,
            rules_checked=len(rules),
        )
        return RuleEvaluationResult(
            should_create_alert=True,
            matching_rule=None,
        )

    async def _check_maintenance_suppression(
        self,
        db: AsyncSession,
        event: ChangeEvent,
        asset: Asset | None,
    ) -> str | None:
        """Check if the event should be suppressed due to maintenance.

        Args:
            db: Database session.
            event: The change event.
            asset: The related asset.

        Returns:
            Suppression reason if suppressed, None otherwise.
        """
        now = datetime.now(timezone.utc)

        # Query active maintenance windows
        result = await db.execute(
            select(MaintenanceWindow)
            .where(
                MaintenanceWindow.is_active == True,
                MaintenanceWindow.suppress_alerts == True,
                MaintenanceWindow.start_time <= now,
                MaintenanceWindow.end_time >= now,
            )
        )
        active_windows = result.scalars().all()

        if not active_windows:
            return None

        # Check if any window affects this asset
        asset_id = event.asset_id or (asset.id if asset else None)

        for window in active_windows:
            # Check if window has no scope (global) or matches asset
            if not window.asset_ids and not window.environments and not window.datacenters:
                window.increment_suppressed()
                return f"Global maintenance window: {window.name}"

            if asset:
                if window.affects_asset(
                    asset_id=asset.id,
                    environment=asset.environment,
                    datacenter=asset.datacenter,
                ):
                    window.increment_suppressed()
                    return f"Maintenance window: {window.name}"
            elif asset_id and window.asset_ids and asset_id in window.asset_ids:
                window.increment_suppressed()
                return f"Maintenance window: {window.name}"

        return None

    def _build_asset_data(self, asset: Asset) -> dict:
        """Build asset data dictionary for filter matching.

        Args:
            asset: The asset to extract data from.

        Returns:
            Dictionary of asset properties.
        """
        return {
            "environment": asset.environment,
            "datacenter": asset.datacenter,
            "is_critical": asset.is_critical,
            "is_internal": asset.is_internal,
            "asset_type": (
                asset.asset_type.value
                if hasattr(asset.asset_type, "value")
                else str(asset.asset_type)
            ),
            "owner": asset.owner,
            "team": asset.team,
        }

    def _build_context(
        self,
        event: ChangeEvent,
        asset: Asset | None,
    ) -> AlertContext:
        """Build context for template rendering.

        Args:
            event: The change event.
            asset: The related asset.

        Returns:
            AlertContext with template variables.
        """
        change_type_str = (
            event.change_type.value
            if hasattr(event.change_type, "value")
            else str(event.change_type)
        )

        return AlertContext(
            change_type=change_type_str,
            summary=event.summary,
            description=event.description,
            asset_name=asset.name if asset else None,
            asset_ip=str(asset.ip_address) if asset else None,
            asset_type=(
                asset.asset_type.value
                if asset and hasattr(asset.asset_type, "value")
                else str(asset.asset_type) if asset else None
            ),
            environment=asset.environment if asset else None,
            datacenter=asset.datacenter if asset else None,
            impact_score=event.impact_score,
            affected_assets_count=event.affected_assets_count,
        )

    def _is_rule_scheduled(self, rule: AlertRule) -> bool:
        """Check if a rule is active per its schedule.

        Args:
            rule: The alert rule to check.

        Returns:
            True if the rule should be active now.
        """
        if not rule.schedule:
            return True

        now = datetime.now(timezone.utc)

        # Check days
        if "days" in rule.schedule:
            day_map = {
                0: "mon", 1: "tue", 2: "wed",
                3: "thu", 4: "fri", 5: "sat", 6: "sun"
            }
            current_day = day_map.get(now.weekday())
            if current_day not in rule.schedule["days"]:
                return False

        # Check hours
        if "hours" in rule.schedule:
            hours = rule.schedule["hours"]
            start_hour = hours.get("start", 0)
            end_hour = hours.get("end", 24)
            if not (start_hour <= now.hour < end_hour):
                return False

        return True
