"""Task Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TaskSummary(BaseModel):
    """Summary of a background task."""

    id: UUID
    task_type: str
    name: str
    status: str
    progress_percent: float
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    skipped_items: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class TaskResponse(BaseModel):
    """Full task details."""

    id: UUID
    task_type: str
    name: str
    description: str | None = None
    status: str
    progress_percent: float
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    skipped_items: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    parameters: dict | None = None
    result: dict | None = None
    error_message: str | None = None
    error_details: dict | None = None
    triggered_by: str | None = None
    related_entity_type: str | None = None
    related_entity_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    """Paginated list of tasks."""

    items: list[TaskSummary]
    total: int
    page: int
    page_size: int


class TaskCreate(BaseModel):
    """Request to create a task."""

    task_type: str
    name: str
    description: str | None = None
    parameters: dict | None = None


class ApplyRulesTaskCreate(BaseModel):
    """Request to apply classification rules."""

    force: bool = Field(
        default=False,
        description="If true, overwrite existing asset values",
    )
    rule_id: UUID | None = Field(
        default=None,
        description="If specified, only apply this specific rule",
    )
