"""Topology exclusion model for hiding entities from the arc view.

Allows users to exclude specific folders or applications from the
topology visualization and dependency aggregations.
"""

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base, TimestampMixin, UUIDMixin


class ExclusionEntityType(str, Enum):
    """Type of entity being excluded."""

    FOLDER = "folder"
    APPLICATION = "application"


class TopologyExclusion(Base, UUIDMixin, TimestampMixin):
    """User-specific exclusion of a folder or application from topology views.

    Excluded entities are:
    - Not rendered in the arc visualization
    - Not included in dependency aggregations
    - Filtered out from folder-level and app-level dependency calculations
    """

    __tablename__ = "topology_exclusions"

    # User who created the exclusion
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Type of entity being excluded
    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # ID of the excluded entity (folder or application)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Optional note about why this entity was excluded
    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    __table_args__ = (
        # Each user can only exclude a specific entity once
        UniqueConstraint(
            "user_id",
            "entity_type",
            "entity_id",
            name="uq_topology_exclusions_user_entity",
        ),
    )

    def __repr__(self) -> str:
        return f"<TopologyExclusion user={self.user_id} {self.entity_type}={self.entity_id}>"
