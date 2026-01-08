"""Application layout models for persistent view positioning.

Stores per-application, per-hop-depth node positions and asset groups
for system-wide layout persistence in the application details view.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from flowlens.models.asset import Application


class ApplicationLayout(Base, UUIDMixin, TimestampMixin):
    """Per-application, per-hop-depth layout configuration.

    System-wide - all users see the same layout. Each combination of
    application_id and hop_depth has exactly one layout record.
    """

    __tablename__ = "application_layouts"

    # Parent application
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hop depth this layout applies to (1-5)
    hop_depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Node positions stored as JSONB: {asset_id: {x: float, y: float}}
    positions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Viewport state: {scale: float, x: float, y: float}
    viewport: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Last modified by (username or email)
    modified_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    application: Mapped["Application"] = relationship(
        "Application",
        back_populates="layouts",
    )
    asset_groups: Mapped[list["AssetGroup"]] = relationship(
        "AssetGroup",
        back_populates="layout",
        cascade="all, delete-orphan",
        order_by="AssetGroup.created_at",
    )

    __table_args__ = (
        # Unique constraint: one layout per application per hop depth
        Index(
            "ix_application_layouts_app_hop",
            "application_id",
            "hop_depth",
            unique=True,
        ),
        # Hop depth must be between 1 and 5
        CheckConstraint(
            "hop_depth >= 1 AND hop_depth <= 5",
            name="ck_application_layouts_hop_depth_range",
        ),
    )


class AssetGroup(Base, UUIDMixin, TimestampMixin):
    """Visual grouping of assets within an application layout.

    Allows users to group related assets together with a named
    bounding box that can be collapsed/expanded.
    """

    __tablename__ = "asset_groups"

    # Parent layout
    layout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application_layouts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Group metadata
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Visual styling
    color: Mapped[str] = mapped_column(
        String(7),
        default="#3b82f6",
        nullable=False,
    )

    # Position of the group container
    position_x: Mapped[float] = mapped_column(
        Float,
        default=0,
        nullable=False,
    )

    position_y: Mapped[float] = mapped_column(
        Float,
        default=0,
        nullable=False,
    )

    # Dimensions (computed from members or manually set)
    width: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    height: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Visual state
    is_collapsed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    # Member assets
    asset_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
    )

    # Relationships
    layout: Mapped["ApplicationLayout"] = relationship(
        "ApplicationLayout",
        back_populates="asset_groups",
    )
