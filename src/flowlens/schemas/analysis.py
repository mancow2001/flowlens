"""Pydantic schemas for Analysis API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BlastRadiusResult(BaseModel):
    """Result of blast radius calculation."""

    asset_id: UUID
    asset_name: str
    total_affected: int
    critical_affected: int
    affected_assets: list[dict]  # List of {id, name, depth, is_critical}
    max_depth: int
    calculated_at: datetime


class ImpactAnalysisRequest(BaseModel):
    """Request for impact analysis."""

    asset_id: UUID
    failure_type: str = Field(
        "complete",
        pattern=r"^(complete|degraded|intermittent)$",
    )
    include_indirect: bool = True
    max_depth: int = Field(5, ge=1, le=10)


class ImpactedAsset(BaseModel):
    """Asset impacted by a failure."""

    id: UUID
    name: str
    ip_address: str
    is_critical: bool
    impact_level: str  # "direct", "indirect"
    depth: int
    dependency_path: list[UUID]


class ImpactAnalysisResult(BaseModel):
    """Result of impact analysis."""

    source_asset_id: UUID
    source_asset_name: str
    failure_type: str
    total_impacted: int
    critical_impacted: int
    impacted_assets: list[ImpactedAsset]
    impacted_applications: list[dict]  # List of {id, name, asset_count}
    severity_score: int = Field(ge=0, le=100)
    calculated_at: datetime


class SPOFCandidate(BaseModel):
    """Single Point of Failure candidate."""

    asset_id: UUID
    asset_name: str
    ip_address: str
    is_critical: bool

    # SPOF metrics
    dependents_count: int  # Assets that depend on this
    critical_dependents: int
    unique_path_count: int  # Number of paths through this node
    centrality_score: float  # Betweenness centrality

    # Risk assessment
    risk_score: int = Field(ge=0, le=100)
    risk_level: str  # "low", "medium", "high", "critical"


class SPOFAnalysisResult(BaseModel):
    """Result of SPOF detection."""

    scope: str  # "global", "application:{id}", "environment:{name}"
    candidates: list[SPOFCandidate]
    total_analyzed: int
    high_risk_count: int
    calculated_at: datetime


class ChangeAnalysisRequest(BaseModel):
    """Request for change analysis between two time points."""

    time_before: datetime
    time_after: datetime
    asset_id: UUID | None = None
    application_id: UUID | None = None


class DependencyChange(BaseModel):
    """A single dependency change."""

    change_type: str  # "added", "removed", "modified"
    dependency_id: UUID | None
    source_asset_id: UUID
    source_asset_name: str
    target_asset_id: UUID
    target_asset_name: str
    target_port: int
    protocol: int

    # For modifications
    before: dict | None = None
    after: dict | None = None


class ChangeAnalysisResult(BaseModel):
    """Result of change analysis."""

    time_before: datetime
    time_after: datetime
    scope: str

    # Counts
    dependencies_added: int
    dependencies_removed: int
    dependencies_modified: int
    assets_discovered: int
    assets_removed: int

    # Details
    changes: list[DependencyChange]
    calculated_at: datetime


class CriticalPathRequest(BaseModel):
    """Request for critical path analysis."""

    source_asset_id: UUID
    target_asset_id: UUID
    criteria: str = Field(
        "bytes",
        pattern=r"^(bytes|flows|latency|hops)$",
    )


class CriticalPathResult(BaseModel):
    """Result of critical path analysis."""

    source_id: UUID
    target_id: UUID
    criteria: str
    path: list[dict]  # List of {asset_id, asset_name, edge_metrics}
    total_bytes: int
    total_hops: int
    avg_latency_ms: float | None
    calculated_at: datetime
