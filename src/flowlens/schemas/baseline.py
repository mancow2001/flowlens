"""Schemas for application baseline API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DependencySnapshot(BaseModel):
    """Snapshot of a single dependency."""

    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    target_port: int
    protocol: int
    bytes_total: int = 0
    bytes_last_24h: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class TrafficVolumeSnapshot(BaseModel):
    """Traffic volume snapshot for an asset."""

    bytes_in_24h: int = 0
    bytes_out_24h: int = 0
    connections_in: int = 0
    connections_out: int = 0


class NodePositionSnapshot(BaseModel):
    """Position snapshot for a node."""

    x: float
    y: float


class EntryPointSnapshot(BaseModel):
    """Snapshot of an entry point."""

    id: UUID
    member_id: UUID
    asset_id: UUID
    port: int
    protocol: int
    label: str | None = None


class BaselineSnapshot(BaseModel):
    """Full snapshot data structure."""

    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    traffic_volumes: dict[str, TrafficVolumeSnapshot] = Field(default_factory=dict)
    node_positions: dict[str, NodePositionSnapshot] = Field(default_factory=dict)
    entry_points: list[EntryPointSnapshot] = Field(default_factory=list)
    member_asset_ids: list[UUID] = Field(default_factory=list)
    hop_depth: int = 1


class ApplicationBaselineCreate(BaseModel):
    """Schema for creating a new baseline."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    hop_depth: int = Field(default=1, ge=1, le=5)
    include_positions: bool = True
    tags: dict[str, Any] | None = None


class ApplicationBaselineResponse(BaseModel):
    """Schema for baseline response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    name: str
    description: str | None
    is_active: bool
    captured_at: datetime
    created_by: str | None
    dependency_count: int
    member_count: int
    entry_point_count: int
    total_traffic_bytes: int
    tags: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ApplicationBaselineWithSnapshot(ApplicationBaselineResponse):
    """Baseline response including full snapshot data."""

    snapshot: dict[str, Any]


class BaselineComparisonRequest(BaseModel):
    """Request schema for baseline comparison."""

    hop_depth: int = Field(default=1, ge=1, le=5)
    include_positions: bool = False


class DependencyChange(BaseModel):
    """Represents a changed dependency."""

    id: UUID
    source_asset_id: UUID
    source_name: str | None = None
    source_ip: str | None = None
    target_asset_id: UUID
    target_name: str | None = None
    target_ip: str | None = None
    target_port: int
    protocol: int
    change_type: str  # "added", "removed"


class TrafficDeviation(BaseModel):
    """Represents a traffic volume deviation."""

    asset_id: UUID
    asset_name: str | None = None
    metric: str  # "bytes_in_24h", "bytes_out_24h", etc.
    baseline_value: int
    current_value: int
    deviation_percent: float


class EntryPointChange(BaseModel):
    """Represents an entry point change."""

    port: int
    protocol: int
    label: str | None = None
    member_id: UUID
    asset_id: UUID
    asset_name: str | None = None
    change_type: str  # "added", "removed"


class MemberChange(BaseModel):
    """Represents a member asset change."""

    asset_id: UUID
    asset_name: str | None = None
    ip_address: str | None = None
    change_type: str  # "added", "removed"


class BaselineComparisonResult(BaseModel):
    """Result of comparing a baseline to current state."""

    baseline_id: UUID
    baseline_name: str
    captured_at: datetime
    compared_at: datetime

    # Changes
    dependencies_added: list[DependencyChange] = Field(default_factory=list)
    dependencies_removed: list[DependencyChange] = Field(default_factory=list)
    traffic_deviations: list[TrafficDeviation] = Field(default_factory=list)
    entry_points_added: list[EntryPointChange] = Field(default_factory=list)
    entry_points_removed: list[EntryPointChange] = Field(default_factory=list)
    members_added: list[MemberChange] = Field(default_factory=list)
    members_removed: list[MemberChange] = Field(default_factory=list)

    # Summary
    total_changes: int = 0
    change_severity: str = "none"  # "none", "low", "medium", "high"

    def calculate_severity(self) -> None:
        """Calculate severity based on changes."""
        self.total_changes = (
            len(self.dependencies_added)
            + len(self.dependencies_removed)
            + len(self.traffic_deviations)
            + len(self.entry_points_added)
            + len(self.entry_points_removed)
            + len(self.members_added)
            + len(self.members_removed)
        )

        if self.total_changes == 0:
            self.change_severity = "none"
        elif self.total_changes <= 3:
            self.change_severity = "low"
        elif self.total_changes <= 10:
            self.change_severity = "medium"
        else:
            self.change_severity = "high"
