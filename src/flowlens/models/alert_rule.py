"""Alert rules model for configurable alert generation.

Allows users to define custom rules for when alerts should be generated
based on change events, with configurable severity and notification settings.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base, TimestampMixin, UUIDMixin
from flowlens.models.change import AlertSeverity


class AlertRule(Base, UUIDMixin, TimestampMixin):
    """Configurable rule for generating alerts from change events.

    Alert rules allow users to customize:
    - Which change types trigger alerts
    - What severity the alert should have
    - Which assets the rule applies to (via filters)
    - Which notification channels to use
    - Cooldown periods to prevent alert fatigue
    """

    __tablename__ = "alert_rules"

    # Rule identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Rule status
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )

    # Trigger conditions
    # Which ChangeTypes trigger this rule (e.g., ["dependency_created", "asset_discovered"])
    change_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
    )

    # Optional filter to match specific assets
    # Example: {"environment": "production", "is_critical": true}
    asset_filter: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Alert configuration
    severity: Mapped[AlertSeverity] = mapped_column(
        String(20),
        nullable=False,
        default=AlertSeverity.WARNING,
    )

    # Template for alert title (supports placeholders like {change_type}, {asset_name})
    title_template: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="{change_type} detected",
    )

    # Template for alert description
    description_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{summary}",
    )

    # Notification settings
    # Which channels to notify (e.g., ["email", "webhook", "slack"])
    notify_channels: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    # Cooldown in minutes - don't re-alert for same condition within this period
    cooldown_minutes: Mapped[int] = mapped_column(
        default=60,
        nullable=False,
    )

    # Priority for rule matching (lower = higher priority)
    priority: Mapped[int] = mapped_column(
        default=100,
        nullable=False,
    )

    # Track last trigger time for cooldown
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Statistics
    trigger_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Optional schedule - only active during certain times
    # Example: {"days": ["mon", "tue", "wed", "thu", "fri"], "hours": {"start": 9, "end": 17}}
    schedule: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Tags for organization
    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    __table_args__ = (
        Index("ix_alert_rules_active_priority", "is_active", "priority"),
        CheckConstraint("cooldown_minutes >= 0", name="ck_alert_rules_cooldown_positive"),
        CheckConstraint("priority >= 0", name="ck_alert_rules_priority_positive"),
    )

    def __repr__(self) -> str:
        return f"<AlertRule '{self.name}' [{self.severity.value}] active={self.is_active}>"

    def matches_change_type(self, change_type: str) -> bool:
        """Check if this rule matches a given change type.

        Args:
            change_type: The change type to check.

        Returns:
            True if this rule should trigger for the given change type.
        """
        return change_type in self.change_types

    def matches_asset_filter(self, asset_data: dict) -> bool:
        """Check if an asset matches this rule's filter.

        Args:
            asset_data: Dictionary of asset properties to match against.

        Returns:
            True if the asset matches the filter (or no filter is set).
        """
        if not self.asset_filter:
            return True

        for key, expected_value in self.asset_filter.items():
            actual_value = asset_data.get(key)
            if actual_value != expected_value:
                return False

        return True

    def is_on_cooldown(self) -> bool:
        """Check if this rule is currently on cooldown.

        Returns:
            True if the cooldown period hasn't elapsed since last trigger.
        """
        if not self.last_triggered_at or self.cooldown_minutes <= 0:
            return False

        now = datetime.now(timezone.utc)
        # Make last_triggered_at timezone-aware if needed
        last_triggered = self.last_triggered_at
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)

        elapsed = now - last_triggered
        return elapsed.total_seconds() < (self.cooldown_minutes * 60)

    def trigger(self) -> None:
        """Mark this rule as triggered.

        Updates last_triggered_at and increments trigger_count.
        """
        self.last_triggered_at = datetime.now(timezone.utc)
        self.trigger_count += 1

    def render_title(self, context: dict) -> str:
        """Render the alert title template with context values.

        Args:
            context: Dictionary of values to substitute in the template.

        Returns:
            Rendered title string.
        """
        try:
            return self.title_template.format(**context)
        except KeyError:
            return self.title_template

    def render_description(self, context: dict) -> str:
        """Render the alert description template with context values.

        Args:
            context: Dictionary of values to substitute in the template.

        Returns:
            Rendered description string.
        """
        try:
            return self.description_template.format(**context)
        except KeyError:
            return self.description_template
