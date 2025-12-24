"""SQLAlchemy base model and mixins.

Provides common functionality for all database models including
timestamps, soft delete, and temporal validity patterns.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map = {
        str: String(255),
    }

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        # Convert CamelCase to snake_case
        name = cls.__name__
        return "".join(
            f"_{c.lower()}" if c.isupper() else c for c in name
        ).lstrip("_")


class UUIDMixin:
    """Mixin for UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality.

    Instead of actually deleting records, sets deleted_at timestamp.
    Queries should filter by deleted_at IS NULL to exclude deleted records.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark record as deleted."""
        self.deleted_at = datetime.utcnow()

    def restore(self) -> None:
        """Restore soft-deleted record."""
        self.deleted_at = None


class TemporalMixin:
    """Mixin for temporal validity (point-in-time queries).

    Enables tracking when a record was valid, supporting queries like
    "show me the state of dependencies at timestamp X".
    """

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_current(self) -> bool:
        """Check if record is currently valid."""
        return self.valid_to is None

    def invalidate(self, at: datetime | None = None) -> None:
        """Mark record as no longer valid.

        Args:
            at: Timestamp when record became invalid. Defaults to now.
        """
        self.valid_to = at or datetime.utcnow()


class AggregationMixin:
    """Mixin for aggregation fields used in dependency tracking."""

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

    bytes_last_24h: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def update_aggregates(
        self,
        bytes_count: int,
        packets_count: int,
        timestamp: datetime | None = None,
    ) -> None:
        """Update aggregation counters.

        Args:
            bytes_count: Bytes to add to total.
            packets_count: Packets to add to total.
            timestamp: Flow timestamp (updates last_seen if more recent).
        """
        self.bytes_total += bytes_count
        self.packets_total += packets_count
        self.flows_total += 1

        ts = timestamp or datetime.utcnow()
        if ts > self.last_seen:
            self.last_seen = ts


class BaseModel(Base, UUIDMixin, TimestampMixin):
    """Standard base model with UUID and timestamps.

    Use this as the base class for most entities.
    """

    __abstract__ = True


class SoftDeleteModel(BaseModel, SoftDeleteMixin):
    """Base model with soft delete support.

    Use for entities that should not be permanently deleted.
    """

    __abstract__ = True


class TemporalModel(BaseModel, TemporalMixin):
    """Base model with temporal validity.

    Use for entities that need point-in-time querying.
    """

    __abstract__ = True


def model_to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    """Convert SQLAlchemy model instance to dictionary.

    Args:
        obj: Model instance.
        exclude: Set of field names to exclude.

    Returns:
        Dictionary representation of the model.
    """
    exclude = exclude or set()
    result = {}

    for column in obj.__table__.columns:
        if column.name not in exclude:
            value = getattr(obj, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
            result[column.name] = value

    return result
