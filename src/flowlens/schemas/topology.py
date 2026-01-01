"""Pydantic schemas for Topology and Graph API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TopologyNode(BaseModel):
    """Node in the topology graph."""

    id: UUID
    name: str
    label: str | None = None
    asset_type: str
    ip_address: str
    is_internal: bool
    is_critical: bool
    environment: str | None = None
    datacenter: str | None = None
    location: str | None = None  # Dynamic from CIDR rules

    # Metrics for sizing
    connections_in: int
    connections_out: int
    bytes_in_24h: int = 0
    bytes_out_24h: int = 0


class TopologyEdge(BaseModel):
    """Edge in the topology graph."""

    id: UUID
    source: UUID
    target: UUID
    target_port: int
    protocol: int
    protocol_name: str | None = None  # e.g., "TCP", "UDP"
    service_type: str | None = None   # e.g., "http", "mysql"

    # Metrics for edge weight
    bytes_total: int
    bytes_last_24h: int
    is_critical: bool
    last_seen: datetime


class TopologyGraph(BaseModel):
    """Complete topology graph for visualization."""

    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    generated_at: datetime


class TopologyFilter(BaseModel):
    """Filters for topology queries."""

    model_config = ConfigDict(extra='ignore')

    asset_ids: list[UUID] | None = None
    application_id: UUID | None = None
    asset_types: list[str] | None = None
    environments: list[str] | None = None
    datacenters: list[str] | None = None
    locations: list[str] | None = None
    include_external: bool = True
    min_bytes_24h: int = 0
    max_depth: int = Field(5, ge=1, le=10)
    as_of: datetime | None = None  # Point-in-time query
    use_cidr_classification: bool = True  # Apply CIDR rules for dynamic grouping


class TraversalNode(BaseModel):
    """Node in a traversal result."""

    asset_id: UUID
    asset_name: str
    depth: int
    path: list[UUID]
    target_port: int
    protocol: int
    bytes_total: int
    last_seen: datetime


class TraversalResult(BaseModel):
    """Result of a graph traversal operation."""

    root_asset_id: UUID
    direction: str  # "upstream" or "downstream"
    max_depth: int
    nodes: list[TraversalNode]
    total_nodes: int


class PathResult(BaseModel):
    """Result of a path finding operation."""

    source_id: UUID
    target_id: UUID
    path_exists: bool
    path: list[UUID] | None = None
    path_length: int | None = None
    edges: list[TopologyEdge] | None = None


class SubgraphRequest(BaseModel):
    """Request for extracting a subgraph."""

    center_asset_id: UUID
    depth: int = Field(2, ge=1, le=5)
    direction: str = Field("both", pattern=r"^(upstream|downstream|both)$")
    include_external: bool = True
    as_of: datetime | None = None


class TopologyConfig(BaseModel):
    """Configuration settings that affect topology display and filtering.

    This is exposed to the frontend to control which UI elements to show.
    """

    # When True, external flows are completely discarded at ingestion time,
    # so the "Include External" toggle should be hidden in the UI
    discard_external_flows: bool = False
