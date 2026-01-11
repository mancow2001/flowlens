"""ML model registry SQLAlchemy models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base


class MLModelRegistry(Base):
    """Registry for ML classification models.

    Tracks both shipped (bundled) and custom (user-trained) models
    with their training metadata and performance metrics.
    """

    __tablename__ = "ml_model_registry"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom"
    )  # 'shipped' or 'custom'

    # Training metadata
    training_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    class_distribution: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    feature_importances: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confusion_matrix: Mapped[list[list[int]] | None] = mapped_column(JSONB, nullable=True)
    training_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Storage info
    model_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA256

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MLModelRegistry(version={self.version!r}, "
            f"algorithm={self.algorithm!r}, is_active={self.is_active})>"
        )
