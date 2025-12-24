"""Dependency models for the dependency graph edges.

Dependencies represent network connections between assets,
with temporal validity and aggregation metrics.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TemporalMixin, TimestampMixin, UUIDMixin

# Import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from flowlens.models.asset import Asset


class Dependency(Base, UUIDMixin, TimestampMixin, TemporalMixin):
    """Dependency edge between two assets.

    Represents observed network communication from a source asset
    to a target asset on a specific port/protocol combination.

    Uses temporal validity (valid_from, valid_to) for point-in-time queries.
    """

    __tablename__ = "dependencies"

    # Edge endpoints
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Service identification
    target_port: Mapped[int] = mapped_column(
        nullable=False,
    )

    protocol: Mapped[int] = mapped_column(
        nullable=False,  # 6=TCP, 17=UDP, 1=ICMP
    )

    # Aggregation metrics (lifetime)
    bytes_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    packets_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    flows_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Rolling window metrics (updated by aggregation job)
    bytes_last_24h: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    bytes_last_7d: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Activity tracking
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Latency metrics (if available from flow data)
    avg_latency_ms: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    p95_latency_ms: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Classification
    dependency_type: Mapped[str | None] = mapped_column(
        String(50),  # synchronous, asynchronous, database, cache, etc.
        nullable=True,
    )

    is_critical: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # Source of truth
    discovered_by: Mapped[str] = mapped_column(
        String(50),
        default="flow_analysis",
        nullable=False,
    )

    # User overrides
    is_confirmed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    is_ignored: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    source_asset: Mapped["Asset"] = relationship(
        "Asset",
        foreign_keys=[source_asset_id],
        back_populates="outbound_dependencies",
    )

    target_asset: Mapped["Asset"] = relationship(
        "Asset",
        foreign_keys=[target_asset_id],
        back_populates="inbound_dependencies",
    )

    __table_args__ = (
        # Composite unique constraint for current dependencies
        Index(
            "ix_deps_source_target_port_proto_current",
            "source_asset_id", "target_asset_id", "target_port", "protocol",
            unique=True,
            postgresql_where="valid_to IS NULL",
        ),
        # For traversal queries
        Index(
            "ix_deps_source_current",
            "source_asset_id",
            postgresql_where="valid_to IS NULL",
        ),
        Index(
            "ix_deps_target_current",
            "target_asset_id",
            postgresql_where="valid_to IS NULL",
        ),
        # For temporal queries
        Index("ix_deps_valid_from", "valid_from"),
        Index("ix_deps_valid_to", "valid_to"),
        # For stale dependency detection
        Index("ix_deps_last_seen_current", "last_seen", postgresql_where="valid_to IS NULL"),
        # Port range constraint
        CheckConstraint("target_port >= 0 AND target_port <= 65535"),
        CheckConstraint("protocol >= 0 AND protocol <= 255"),
        # Prevent self-loops
        CheckConstraint("source_asset_id != target_asset_id"),
    )

    def __repr__(self) -> str:
        proto = "TCP" if self.protocol == 6 else "UDP" if self.protocol == 17 else str(self.protocol)
        return f"<Dependency {self.source_asset_id} -> {self.target_asset_id}:{self.target_port}/{proto}>"

    def update_metrics(
        self,
        bytes_count: int,
        packets_count: int,
        timestamp: datetime | None = None,
    ) -> None:
        """Update aggregation metrics with new flow data.

        Args:
            bytes_count: Bytes to add.
            packets_count: Packets to add.
            timestamp: Flow timestamp for last_seen update.
        """
        self.bytes_total += bytes_count
        self.packets_total += packets_count
        self.flows_total += 1

        ts = timestamp or datetime.utcnow()
        if ts > self.last_seen:
            self.last_seen = ts


class DependencyHistory(Base, UUIDMixin):
    """Historical record of dependency changes.

    Tracks when dependencies were created, modified, or removed
    for auditing and change detection.
    """

    __tablename__ = "dependency_history"

    # Reference to the dependency
    dependency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Change type
    change_type: Mapped[str] = mapped_column(
        String(20),  # created, updated, deleted, stale
        nullable=False,
        index=True,
    )

    # Timestamp of the change
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Snapshot of dependency state at change time
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    target_port: Mapped[int] = mapped_column(
        nullable=False,
    )

    protocol: Mapped[int] = mapped_column(
        nullable=False,
    )

    # Metrics at time of change
    bytes_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    flows_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Change context
    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    triggered_by: Mapped[str | None] = mapped_column(
        String(100),  # system, user:email, api
        nullable=True,
    )

    # Previous and new values for updates
    previous_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    new_state: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    __table_args__ = (
        Index("ix_dep_history_dep_changed", "dependency_id", "changed_at"),
        Index("ix_dep_history_source_changed", "source_asset_id", "changed_at"),
        Index("ix_dep_history_target_changed", "target_asset_id", "changed_at"),
    )

    def __repr__(self) -> str:
        return f"<DependencyHistory {self.change_type} {self.dependency_id} at {self.changed_at}>"
