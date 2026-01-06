"""Folder model for organizing applications hierarchically.

Folders provide a tree structure for grouping applications (maps)
in the arc-based topology visualization.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from flowlens.models.asset import Application


class Folder(Base, UUIDMixin, TimestampMixin):
    """Folder for organizing applications in a hierarchy.

    Folders can contain applications (maps) and other folders,
    enabling a tree structure for the arc-based topology view.
    """

    __tablename__ = "folders"

    # Identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Hierarchy (self-referential for nesting)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Visual styling
    color: Mapped[str | None] = mapped_column(
        String(7),  # Hex color e.g., #FF5733
        nullable=True,
    )

    icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Ordering within parent
    order: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Ownership
    owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    team: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Metadata
    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    extra_data: Mapped[dict | None] = mapped_column(
        "metadata",  # Column name in database
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    parent: Mapped["Folder | None"] = relationship(
        "Folder",
        remote_side="Folder.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )

    children: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="parent",
        foreign_keys=[parent_id],
        order_by="Folder.order, Folder.name",
    )

    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="folder",
        order_by="Application.name",
    )

    __table_args__ = (
        # Unique folder name within the same parent
        UniqueConstraint("parent_id", "name", name="uq_folders_parent_name"),
        Index("ix_folders_parent_order", "parent_id", "order"),
    )

    def __repr__(self) -> str:
        return f"<Folder {self.name} (id={self.id})>"

    @property
    def path(self) -> list["Folder"]:
        """Get the path from root to this folder."""
        path = [self]
        current = self.parent
        while current is not None:
            path.insert(0, current)
            current = current.parent
        return path

    @property
    def depth(self) -> int:
        """Get the depth of this folder in the hierarchy (root = 0)."""
        depth = 0
        current = self.parent
        while current is not None:
            depth += 1
            current = current.parent
        return depth

    def is_ancestor_of(self, other: "Folder") -> bool:
        """Check if this folder is an ancestor of another folder."""
        current = other.parent
        while current is not None:
            if current.id == self.id:
                return True
            current = current.parent
        return False

    def is_descendant_of(self, other: "Folder") -> bool:
        """Check if this folder is a descendant of another folder."""
        return other.is_ancestor_of(self)
