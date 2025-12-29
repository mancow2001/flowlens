"""Pydantic schemas for Search API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssetInfo(BaseModel):
    """Minimal asset info for search results."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ip_address: str
    hostname: str | None
    is_critical: bool


class AssetMatch(BaseModel):
    """Asset search result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None
    asset_type: str
    ip_address: str
    hostname: str | None
    is_internal: bool
    is_critical: bool
    last_seen: datetime


class ConnectionMatch(BaseModel):
    """Connection/dependency search result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: AssetInfo
    target: AssetInfo
    target_port: int
    protocol: int
    bytes_last_24h: int
    last_seen: datetime


class SearchResponse(BaseModel):
    """Unified search response with both assets and connections."""

    assets: list[AssetMatch]
    connections: list[ConnectionMatch]
