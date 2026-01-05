"""Schemas for discovery status responses."""

from datetime import datetime

from pydantic import BaseModel


class DiscoveryStatusResponse(BaseModel):
    """Discovery sync status response."""

    provider: str
    status: str
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class DiscoveryLastScanResponse(BaseModel):
    """Discovery last scan response."""

    provider: str
    last_scan_at: datetime | None
    last_success_at: datetime | None
    status: str
