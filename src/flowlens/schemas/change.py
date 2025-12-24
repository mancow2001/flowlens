"""Change event schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChangeEventBase(BaseModel):
    """Base change event fields."""

    change_type: str
    summary: str = Field(..., max_length=500)
    description: str | None = None


class ChangeEventCreate(ChangeEventBase):
    """Schema for creating a change event."""

    asset_id: UUID | None = None
    dependency_id: UUID | None = None
    source_asset_id: UUID | None = None
    target_asset_id: UUID | None = None
    previous_state: dict | None = None
    new_state: dict | None = None
    impact_score: int = Field(default=0, ge=0, le=100)
    affected_assets_count: int = Field(default=0, ge=0)
    occurred_at: datetime | None = None
    metadata: dict | None = None


class ChangeEventResponse(ChangeEventBase):
    """Schema for change event response."""

    id: UUID
    detected_at: datetime
    occurred_at: datetime | None = None
    asset_id: UUID | None = None
    dependency_id: UUID | None = None
    source_asset_id: UUID | None = None
    target_asset_id: UUID | None = None
    previous_state: dict | None = None
    new_state: dict | None = None
    impact_score: int = 0
    affected_assets_count: int = 0
    is_processed: bool = False
    processed_at: datetime | None = None
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime

    # Related alert count
    alerts_count: int = 0

    class Config:
        from_attributes = True


class ChangeEventSummary(BaseModel):
    """Summary of change event counts by type."""

    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    unprocessed: int = 0
    last_24h: int = 0
    last_7d: int = 0


class ChangeEventListResponse(BaseModel):
    """Paginated list of change events."""

    items: list[ChangeEventResponse]
    total: int
    page: int
    page_size: int
    summary: ChangeEventSummary


class ChangeTypeCount(BaseModel):
    """Count of changes by type."""

    change_type: str
    count: int


class ChangeTimeline(BaseModel):
    """Timeline of changes over time."""

    period: str  # "hour", "day", "week"
    data: list[dict[str, Any]]


class DependencyChangeDetail(BaseModel):
    """Detailed info for dependency changes."""

    dependency_id: UUID
    source_asset_id: UUID
    source_asset_name: str
    target_asset_id: UUID
    target_asset_name: str
    target_port: int
    protocol: int
    change_type: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    bytes_total: int = 0


class AssetChangeDetail(BaseModel):
    """Detailed info for asset changes."""

    asset_id: UUID
    asset_name: str
    asset_type: str | None = None
    ip_address: str | None = None
    change_type: str
    previous_state: dict | None = None
    new_state: dict | None = None
