"""Application baseline models for point-in-time snapshots."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from flowlens.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from flowlens.models.asset import Application


class ApplicationBaseline(Base, UUIDMixin, TimestampMixin):
    """Point-in-time snapshot of an application's state.

    Baselines capture dependencies, traffic volumes, node positions,
    and entry points for comparison and alerting purposes.
    """

    __tablename__ = "application_baselines"

    # Foreign key to application
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Baseline metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Capture timestamp (when the baseline was captured, may differ from created_at)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Snapshot data stored as JSONB
    # Contains:
    # - dependencies: [{id, source_asset_id, target_asset_id, target_port, protocol, bytes_total, bytes_last_24h, ...}]
    # - traffic_volumes: {asset_id: {bytes_in_24h, bytes_out_24h, connections_in, connections_out}}
    # - node_positions: {asset_id: {x, y}}
    # - entry_points: [{id, member_id, asset_id, port, protocol, label}]
    # - member_asset_ids: [uuid]
    # - hop_depth: int
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Summary statistics for quick reference
    dependency_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entry_point_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_traffic_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Optional tags for categorization
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    application: Mapped["Application"] = relationship(
        "Application",
        back_populates="baselines",
    )

    def __repr__(self) -> str:
        return f"<ApplicationBaseline {self.id} name={self.name}>"
