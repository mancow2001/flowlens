"""Change detection and alerting models.

Tracks changes in the dependency graph and generates alerts.
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TimestampMixin, UUIDMixin


class ChangeType(str, Enum):
    """Types of changes detected in the dependency graph."""

    # Dependency changes
    DEPENDENCY_CREATED = "dependency_created"
    DEPENDENCY_REMOVED = "dependency_removed"
    DEPENDENCY_STALE = "dependency_stale"
    DEPENDENCY_TRAFFIC_SPIKE = "dependency_traffic_spike"
    DEPENDENCY_TRAFFIC_DROP = "dependency_traffic_drop"

    # Asset changes
    ASSET_DISCOVERED = "asset_discovered"
    ASSET_REMOVED = "asset_removed"
    ASSET_OFFLINE = "asset_offline"
    ASSET_ONLINE = "asset_online"

    # Service changes
    SERVICE_DISCOVERED = "service_discovered"
    SERVICE_REMOVED = "service_removed"

    # Topology changes
    NEW_EXTERNAL_CONNECTION = "new_external_connection"
    CRITICAL_PATH_CHANGE = "critical_path_change"


class ChangeEvent(Base, UUIDMixin, TimestampMixin):
    """Record of a detected change in the dependency graph.

    Change events are created by the resolution service when
    it detects new dependencies, stale dependencies, or other
    topology changes.
    """

    __tablename__ = "change_events"

    # Change classification
    change_type: Mapped[ChangeType] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # When the change was detected
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # When the change actually occurred (if known)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Related entities
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    dependency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dependencies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # For dependency changes, store both endpoints
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    target_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Change summary
    summary: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Change details
    previous_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    new_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Impact assessment
    impact_score: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    affected_assets_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Processing status
    is_processed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Metadata
    metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert",
        back_populates="change_event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_changes_type_detected", "change_type", "detected_at"),
        Index("ix_changes_unprocessed", "detected_at", postgresql_where="is_processed = false"),
        CheckConstraint("impact_score >= 0 AND impact_score <= 100"),
    )

    def __repr__(self) -> str:
        return f"<ChangeEvent {self.change_type.value} at {self.detected_at}>"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Alert(Base, UUIDMixin, TimestampMixin):
    """Alert generated from a change event.

    Alerts are the user-facing notifications about changes
    in the dependency graph.
    """

    __tablename__ = "alerts"

    # Alert classification
    severity: Mapped[AlertSeverity] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Source change event
    change_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("change_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Alert content
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Related entities (denormalized for query efficiency)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    dependency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Alert lifecycle
    is_acknowledged: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    acknowledged_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_resolved: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Notification tracking
    notification_sent: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    notification_channels: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Metadata
    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    change_event: Mapped["ChangeEvent"] = relationship(
        "ChangeEvent",
        back_populates="alerts",
    )

    __table_args__ = (
        Index("ix_alerts_severity_created", "severity", "created_at"),
        Index(
            "ix_alerts_unacknowledged",
            "severity", "created_at",
            postgresql_where="is_acknowledged = false",
        ),
        Index(
            "ix_alerts_unresolved",
            "severity", "created_at",
            postgresql_where="is_resolved = false",
        ),
    )

    def __repr__(self) -> str:
        return f"<Alert [{self.severity.value}] {self.title}>"

    def acknowledge(self, by: str) -> None:
        """Acknowledge the alert.

        Args:
            by: User or system that acknowledged.
        """
        self.is_acknowledged = True
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = by

    def resolve(self, by: str, notes: str | None = None) -> None:
        """Resolve the alert.

        Args:
            by: User or system that resolved.
            notes: Optional resolution notes.
        """
        self.is_resolved = True
        self.resolved_at = datetime.utcnow()
        self.resolved_by = by
        self.resolution_notes = notes

        # Also acknowledge if not already
        if not self.is_acknowledged:
            self.acknowledge(by)
