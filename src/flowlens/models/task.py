"""Background task model for tracking async operations.

Provides visibility into long-running tasks like classification
rule application, bulk updates, and other batch operations.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base, TimestampMixin, UUIDMixin


class TaskStatus(str, Enum):
    """Status of a background task."""

    PENDING = "pending"  # Task created but not started
    RUNNING = "running"  # Task is actively processing
    COMPLETED = "completed"  # Task finished successfully
    FAILED = "failed"  # Task failed with error
    CANCELLED = "cancelled"  # Task was cancelled by user


class TaskType(str, Enum):
    """Types of background tasks."""

    APPLY_CLASSIFICATION_RULES = "apply_classification_rules"
    BULK_ASSET_UPDATE = "bulk_asset_update"
    BULK_ASSET_DELETE = "bulk_asset_delete"
    EXPORT_ASSETS = "export_assets"
    IMPORT_ASSETS = "import_assets"


class BackgroundTask(Base, UUIDMixin, TimestampMixin):
    """Background task for tracking async operations.

    Provides progress tracking, error handling, and result storage
    for long-running operations.
    """

    __tablename__ = "background_tasks"

    # Task identification
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TaskStatus.PENDING.value,
        index=True,
    )

    # Progress tracking
    total_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    processed_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    successful_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failed_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    skipped_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Task configuration and results
    parameters: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Who triggered the task
    triggered_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Related entity (e.g., rule_id that triggered the task)
    related_entity_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_items == 0:
            return 0.0
        return round((self.processed_items / self.total_items) * 100, 1)

    @property
    def is_complete(self) -> bool:
        """Check if task has finished (success or failure)."""
        return self.status in (
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate task duration in seconds."""
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.now(timezone.utc)
        # Ensure both are timezone-aware
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        return (end_time - started).total_seconds()

    def start(self, total_items: int = 0) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING.value
        self.started_at = datetime.now(timezone.utc)
        self.total_items = total_items

    def update_progress(
        self,
        processed: int = 0,
        successful: int = 0,
        failed: int = 0,
        skipped: int = 0,
    ) -> None:
        """Update task progress counters."""
        self.processed_items += processed
        self.successful_items += successful
        self.failed_items += failed
        self.skipped_items += skipped

    def complete(self, result: dict | None = None) -> None:
        """Mark task as completed successfully."""
        self.status = TaskStatus.COMPLETED.value
        self.completed_at = datetime.now(timezone.utc)
        self.result = result

    def fail(self, error_message: str, error_details: dict | None = None) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED.value
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
        self.error_details = error_details

    def cancel(self) -> None:
        """Mark task as cancelled."""
        self.status = TaskStatus.CANCELLED.value
        self.completed_at = datetime.now(timezone.utc)
