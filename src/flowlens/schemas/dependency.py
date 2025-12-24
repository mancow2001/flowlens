"""Pydantic schemas for Dependency API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DependencyBase(BaseModel):
    """Base schema for dependency data."""

    target_port: int = Field(..., ge=0, le=65535)
    protocol: int = Field(..., ge=0, le=255)
    dependency_type: str | None = Field(None, max_length=50)
    is_critical: bool = False
    is_confirmed: bool = False
    is_ignored: bool = False
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class DependencyCreate(DependencyBase):
    """Schema for creating a dependency manually."""

    source_asset_id: UUID
    target_asset_id: UUID


class DependencyUpdate(BaseModel):
    """Schema for updating a dependency."""

    dependency_type: str | None = Field(None, max_length=50)
    is_critical: bool | None = None
    is_confirmed: bool | None = None
    is_ignored: bool | None = None
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class AssetInfo(BaseModel):
    """Minimal asset info for dependency responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ip_address: str
    hostname: str | None
    is_critical: bool


class DependencyResponse(DependencyBase):
    """Schema for dependency response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID

    # Aggregation metrics
    bytes_total: int
    packets_total: int
    flows_total: int
    bytes_last_24h: int
    bytes_last_7d: int

    # Timing
    first_seen: datetime
    last_seen: datetime
    valid_from: datetime
    valid_to: datetime | None

    # Latency
    avg_latency_ms: float | None
    p95_latency_ms: float | None

    # Source
    discovered_by: str

    created_at: datetime
    updated_at: datetime


class DependencyWithAssets(DependencyResponse):
    """Dependency with source and target asset info."""

    source_asset: AssetInfo
    target_asset: AssetInfo


class DependencySummary(BaseModel):
    """Minimal dependency info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    target_port: int
    protocol: int
    bytes_total: int
    bytes_last_24h: int
    last_seen: datetime
    valid_to: datetime | None
    is_critical: bool
    source_asset: AssetInfo | None = None
    target_asset: AssetInfo | None = None


class DependencyList(BaseModel):
    """Paginated list of dependencies."""

    items: list[DependencySummary]
    total: int
    page: int
    page_size: int
    pages: int


class DependencyHistoryEntry(BaseModel):
    """Single entry in dependency history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dependency_id: UUID
    change_type: str
    changed_at: datetime
    source_asset_id: UUID
    target_asset_id: UUID
    target_port: int
    protocol: int
    bytes_total: int
    flows_total: int
    reason: str | None
    triggered_by: str | None
    previous_state: dict | None
    new_state: dict | None


class DependencyDiff(BaseModel):
    """Difference between two time points."""

    added: list[DependencySummary]
    removed: list[DependencySummary]
    changed: list[dict]  # Contains before/after snapshots
