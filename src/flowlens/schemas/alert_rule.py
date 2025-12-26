"""Alert rule schemas for API serialization."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AlertRuleBase(BaseModel):
    """Base alert rule fields."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    change_types: list[str] = Field(..., min_length=1)
    asset_filter: dict | None = None
    severity: str = "warning"
    title_template: str = "{change_type} detected"
    description_template: str = "{summary}"
    notify_channels: list[str] | None = None
    cooldown_minutes: int = Field(default=60, ge=0)
    priority: int = Field(default=100, ge=0)
    schedule: dict | None = None
    tags: dict | None = None


class AlertRuleCreate(AlertRuleBase):
    """Schema for creating an alert rule."""

    pass


class AlertRuleUpdate(BaseModel):
    """Schema for updating an alert rule."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    change_types: list[str] | None = None
    asset_filter: dict | None = None
    severity: str | None = None
    title_template: str | None = None
    description_template: str | None = None
    notify_channels: list[str] | None = None
    cooldown_minutes: int | None = Field(None, ge=0)
    priority: int | None = Field(None, ge=0)
    schedule: dict | None = None
    tags: dict | None = None


class AlertRuleSummary(BaseModel):
    """Summary view of an alert rule for list views."""

    id: UUID
    name: str
    is_active: bool
    change_types: list[str]
    severity: str
    cooldown_minutes: int
    priority: int
    trigger_count: int
    last_triggered_at: datetime | None = None


class AlertRuleResponse(AlertRuleBase):
    """Full alert rule response."""

    id: UUID
    last_triggered_at: datetime | None = None
    trigger_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertRuleList(BaseModel):
    """Paginated list of alert rules."""

    items: list[AlertRuleSummary]
    total: int
    page: int
    page_size: int


class AlertRuleTestRequest(BaseModel):
    """Request to test an alert rule."""

    change_type: str
    asset_data: dict | None = None


class AlertRuleTestResult(BaseModel):
    """Result of testing an alert rule."""

    would_trigger: bool
    reason: str | None = None
    rendered_title: str | None = None
    rendered_description: str | None = None


class ChangeTypeInfo(BaseModel):
    """Information about a change type."""

    value: str
    label: str
    category: str
