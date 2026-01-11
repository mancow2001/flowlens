"""Alert and notification schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AlertBase(BaseModel):
    """Base alert fields."""

    title: str = Field(..., max_length=255)
    message: str
    severity: str = Field(..., pattern="^(info|warning|error|critical)$")


class AlertCreate(AlertBase):
    """Schema for creating an alert."""

    change_event_id: UUID | None = None
    asset_id: UUID | None = None
    dependency_id: UUID | None = None
    tags: dict | None = None


class AlertUpdate(BaseModel):
    """Schema for updating an alert."""

    is_acknowledged: bool | None = None
    acknowledged_by: str | None = None
    is_resolved: bool | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None


class AlertAcknowledge(BaseModel):
    """Schema for acknowledging an alert."""

    acknowledged_by: str = Field(..., max_length=255)


class AlertResolve(BaseModel):
    """Schema for resolving an alert."""

    resolved_by: str = Field(..., max_length=255)
    resolution_notes: str | None = None


class AlertResponse(AlertBase):
    """Schema for alert response."""

    id: UUID
    change_event_id: UUID
    asset_id: UUID | None = None
    dependency_id: UUID | None = None
    is_acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    is_resolved: bool = False
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None
    notification_sent: bool = False
    auto_clear_eligible: bool = False
    condition_cleared_at: datetime | None = None
    tags: dict | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertSummary(BaseModel):
    """Summary of alert counts by severity."""

    total: int = 0
    critical: int = 0
    error: int = 0
    warning: int = 0
    info: int = 0
    unacknowledged: int = 0
    unresolved: int = 0


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: list[AlertResponse]
    total: int
    page: int
    page_size: int
    summary: AlertSummary


class NotificationRecipient(BaseModel):
    """Notification recipient configuration."""

    channel: str = Field(..., pattern="^(email|slack|webhook)$")
    address: str


class NotificationTestRequest(BaseModel):
    """Request to test notification channel."""

    channel: str = Field(..., pattern="^(email)$")
    recipient: str


class NotificationTestResponse(BaseModel):
    """Response from notification test."""

    success: bool
    channel: str
    recipient: str
    message: str | None = None
    error: str | None = None
