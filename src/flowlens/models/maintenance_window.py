"""Maintenance window model for alert suppression during planned maintenance.

Allows users to define scheduled maintenance periods during which alerts
are suppressed for specific assets, environments, or datacenters.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base, TimestampMixin, UUIDMixin


class MaintenanceWindow(Base, UUIDMixin, TimestampMixin):
    """Scheduled maintenance window for alert suppression.

    Maintenance windows allow users to:
    - Define time periods when alerts should be suppressed
    - Scope suppression to specific assets, environments, or datacenters
    - Optionally set up recurring maintenance schedules
    """

    __tablename__ = "maintenance_windows"

    # Window identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Scope - which assets/environments are affected
    # If all are null, applies to all assets
    asset_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )

    environments: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    datacenters: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
    )

    # Schedule
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Recurrence (optional)
    is_recurring: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # iCal RRULE format for recurrence
    # Example: "FREQ=WEEKLY;BYDAY=SU;BYHOUR=2;BYMINUTE=0"
    recurrence_rule: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Settings
    suppress_alerts: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    suppress_notifications: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    # Tracking
    created_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Status tracking
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )

    # Count of alerts suppressed during this window
    suppressed_alerts_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Tags for organization
    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    __table_args__ = (
        Index("ix_maintenance_windows_active_time", "is_active", "start_time", "end_time"),
        CheckConstraint("end_time > start_time", name="ck_maintenance_windows_valid_time_range"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceWindow '{self.name}' {self.start_time} - {self.end_time}>"

    def is_currently_active(self) -> bool:
        """Check if this maintenance window is currently in effect.

        Returns:
            True if current time is within the window's time range and window is active.
        """
        if not self.is_active:
            return False

        now = datetime.utcnow()
        return self.start_time <= now <= self.end_time

    def affects_asset(self, asset_id: uuid.UUID, environment: str | None = None, datacenter: str | None = None) -> bool:
        """Check if this maintenance window affects a specific asset.

        Args:
            asset_id: The asset ID to check.
            environment: The asset's environment (optional).
            datacenter: The asset's datacenter (optional).

        Returns:
            True if the asset is within the scope of this maintenance window.
        """
        # If no scope is defined, affects all assets
        if not self.asset_ids and not self.environments and not self.datacenters:
            return True

        # Check asset ID
        if self.asset_ids and asset_id in self.asset_ids:
            return True

        # Check environment
        if self.environments and environment and environment in self.environments:
            return True

        # Check datacenter
        if self.datacenters and datacenter and datacenter in self.datacenters:
            return True

        return False

    def increment_suppressed(self) -> None:
        """Increment the count of suppressed alerts."""
        self.suppressed_alerts_count += 1
