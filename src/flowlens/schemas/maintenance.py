"""Maintenance window schemas for API serialization."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MaintenanceWindowBase(BaseModel):
    """Base maintenance window fields."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    asset_ids: list[UUID] | None = None
    environments: list[str] | None = None
    datacenters: list[str] | None = None
    start_time: datetime
    end_time: datetime
    is_recurring: bool = False
    recurrence_rule: str | None = None
    suppress_alerts: bool = True
    suppress_notifications: bool = True
    tags: dict | None = None

    @field_validator('end_time')
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start_time = info.data.get('start_time')
        if start_time and v <= start_time:
            raise ValueError('end_time must be after start_time')
        return v


class MaintenanceWindowCreate(MaintenanceWindowBase):
    """Schema for creating a maintenance window."""

    created_by: str = Field(..., min_length=1, max_length=255)


class MaintenanceWindowUpdate(BaseModel):
    """Schema for updating a maintenance window."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    asset_ids: list[UUID] | None = None
    environments: list[str] | None = None
    datacenters: list[str] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_recurring: bool | None = None
    recurrence_rule: str | None = None
    suppress_alerts: bool | None = None
    suppress_notifications: bool | None = None
    is_active: bool | None = None
    tags: dict | None = None


class MaintenanceWindowSummary(BaseModel):
    """Summary view of a maintenance window for list views."""

    id: UUID
    name: str
    start_time: datetime
    end_time: datetime
    is_active: bool
    is_recurring: bool
    suppress_alerts: bool
    environments: list[str] | None = None
    datacenters: list[str] | None = None
    asset_count: int = 0
    suppressed_alerts_count: int = 0


class MaintenanceWindowResponse(MaintenanceWindowBase):
    """Full maintenance window response."""

    id: UUID
    is_active: bool
    created_by: str
    suppressed_alerts_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaintenanceWindowList(BaseModel):
    """Paginated list of maintenance windows."""

    items: list[MaintenanceWindowSummary]
    total: int
    page: int
    page_size: int


class ActiveMaintenanceCheck(BaseModel):
    """Result of checking if an asset is in maintenance."""

    asset_id: UUID
    in_maintenance: bool
    windows: list[MaintenanceWindowSummary] = []
