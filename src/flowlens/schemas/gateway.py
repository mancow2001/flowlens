"""Pydantic schemas for Gateway API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GatewayRelationship(BaseModel):
    """Gateway relationship summary."""

    gateway_id: UUID
    gateway_asset_id: UUID
    gateway_ip: str
    gateway_name: str
    gateway_role: str
    is_default: bool
    traffic_share: float | None
    bytes_total: int
    confidence: float
    last_seen: datetime

    class Config:
        from_attributes = True


class ConfidenceBreakdown(BaseModel):
    """Breakdown of confidence score factors."""

    flow_count: float = 0.0
    observation_count: float = 0.0
    time_consistency: float = 0.0
    bytes_volume: float = 0.0


class AssetGatewayResponse(BaseModel):
    """Full gateway relationship response."""

    id: UUID
    source_asset_id: UUID
    gateway_asset_id: UUID
    destination_network: str | None
    gateway_role: str
    is_default_gateway: bool
    bytes_total: int
    flows_total: int
    bytes_last_24h: int
    bytes_last_7d: int
    traffic_share: float | None
    confidence: float
    confidence_scores: dict | None
    first_seen: datetime
    last_seen: datetime
    inference_method: str
    valid_from: datetime
    valid_to: datetime | None

    class Config:
        from_attributes = True


class GatewayListResponse(BaseModel):
    """Paginated gateway list response."""

    items: list[AssetGatewayResponse]
    total: int
    page: int
    page_size: int


class GatewayTopologyNode(BaseModel):
    """Node in gateway topology visualization."""

    id: str
    name: str
    ip_address: str
    asset_type: str
    is_gateway: bool
    client_count: int


class GatewayTopologyEdge(BaseModel):
    """Edge in gateway topology visualization."""

    id: str
    source: str
    target: str
    gateway_role: str
    is_default: bool
    traffic_share: float | None
    confidence: float
    bytes_total: int


class GatewayTopologyData(BaseModel):
    """Gateway topology for visualization."""

    nodes: list[GatewayTopologyNode]
    edges: list[GatewayTopologyEdge]
    generated_at: datetime


class GatewayForAssetResponse(BaseModel):
    """Gateway information for a specific asset."""

    asset_id: UUID
    asset_ip: str
    asset_name: str
    gateways: list[GatewayRelationship]
    total_gateways: int


class GatewayClientsResponse(BaseModel):
    """Clients using a specific gateway."""

    gateway_id: UUID
    gateway_ip: str
    gateway_name: str
    clients: list[GatewayRelationship]
    total_clients: int
