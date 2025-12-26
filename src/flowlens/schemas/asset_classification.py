"""Pydantic schemas for asset classification API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SignalBreakdown(BaseModel):
    """Breakdown of signals contributing to a score."""

    score: float = Field(..., ge=0, le=100, description="Normalized score 0-100")
    breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Individual signal contributions",
    )


class FeaturesUsed(BaseModel):
    """Summary of features used for classification."""

    window_size: str = Field(..., description="Aggregation window size")
    total_flows: int = Field(..., ge=0, description="Total flow count")
    fan_in_count: int = Field(..., ge=0, description="Unique sources connecting to this IP")
    fan_out_count: int = Field(..., ge=0, description="Unique destinations this IP connects to")
    listening_ports: list[int] = Field(default_factory=list, description="Top listening ports")
    has_db_ports: bool = Field(default=False, description="Listening on database ports")
    has_web_ports: bool = Field(default=False, description="Listening on web ports")
    has_storage_ports: bool = Field(default=False, description="Listening on storage ports")
    active_hours: int | None = Field(None, description="Number of active hours")
    business_hours_ratio: float | None = Field(None, description="Ratio of traffic during business hours")


class ClassificationScores(BaseModel):
    """Classification scores for all asset types."""

    server: SignalBreakdown | None = None
    workstation: SignalBreakdown | None = None
    database: SignalBreakdown | None = None
    load_balancer: SignalBreakdown | None = None
    network_device: SignalBreakdown | None = None
    storage: SignalBreakdown | None = None
    cloud_service: SignalBreakdown | None = None
    container: SignalBreakdown | None = None
    virtual_machine: SignalBreakdown | None = None
    unknown: SignalBreakdown | None = None


class ClassificationResponse(BaseModel):
    """Response for asset classification endpoint."""

    ip_address: str = Field(..., description="Asset IP address")
    current_type: str | None = Field(None, description="Current asset type")
    recommended_type: str = Field(..., description="Recommended asset type")
    confidence: float = Field(..., ge=0, le=1, description="Classification confidence 0-1")
    should_auto_update: bool = Field(..., description="Whether auto-update threshold is met")
    scores: dict[str, SignalBreakdown] = Field(
        ...,
        description="Scores for each asset type",
    )
    features_used: FeaturesUsed = Field(..., description="Summary of features used")


class ReclassifyRequest(BaseModel):
    """Request to reclassify an asset."""

    apply: bool = Field(
        default=False,
        description="Whether to apply the classification result",
    )


class ReclassifyResponse(BaseModel):
    """Response from reclassification request."""

    success: bool
    classification: ClassificationResponse | None = None
    applied: bool = Field(default=False, description="Whether the classification was applied")
    message: str | None = None


class LockClassificationRequest(BaseModel):
    """Request to lock/unlock classification for an asset."""

    locked: bool = Field(..., description="Whether to lock classification")


class LockClassificationResponse(BaseModel):
    """Response from lock classification request."""

    success: bool
    asset_id: UUID
    classification_locked: bool
    message: str


class ClassificationHistoryEntry(BaseModel):
    """Single entry in classification history."""

    id: UUID
    classified_at: datetime
    previous_type: str | None
    new_type: str
    confidence: float
    triggered_by: str = Field(..., description="What triggered the classification: auto, manual, api")
    scores: dict[str, SignalBreakdown] | None = None
    features_snapshot: dict | None = None


class ClassificationHistoryResponse(BaseModel):
    """Response for classification history endpoint."""

    asset_id: UUID
    ip_address: str
    history: list[ClassificationHistoryEntry]
    total: int


class AssetFeaturesResponse(BaseModel):
    """Response containing computed behavioral features."""

    asset_id: UUID
    ip_address: str
    window_size: str
    computed_at: datetime

    # Traffic directionality
    inbound_flows: int
    outbound_flows: int
    inbound_bytes: int
    outbound_bytes: int
    fan_in_count: int
    fan_out_count: int
    fan_in_ratio: float | None

    # Port behavior
    unique_dst_ports: int
    unique_src_ports: int
    well_known_port_ratio: float | None
    ephemeral_port_ratio: float | None
    persistent_listener_ports: list[int] | None
    protocol_distribution: dict[int, int] | None

    # Temporal patterns
    active_hours_count: int | None
    business_hours_ratio: float | None
    traffic_variance: float | None

    # Port flags
    has_db_ports: bool
    has_storage_ports: bool
    has_web_ports: bool
    has_ssh_ports: bool
