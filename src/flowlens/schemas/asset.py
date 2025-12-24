"""Pydantic schemas for Asset API endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress

from flowlens.models.asset import AssetType


class AssetBase(BaseModel):
    """Base schema for asset data."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    asset_type: AssetType = AssetType.UNKNOWN
    ip_address: IPvAnyAddress
    hostname: str | None = Field(None, max_length=255)
    fqdn: str | None = Field(None, max_length=255)
    mac_address: str | None = Field(None, pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    subnet: str | None = None
    vlan_id: int | None = Field(None, ge=0, le=4095)
    datacenter: str | None = Field(None, max_length=100)
    environment: str | None = Field(None, max_length=50)
    is_internal: bool = True
    is_critical: bool = False
    criticality_score: int = Field(0, ge=0, le=100)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    pass


class AssetUpdate(BaseModel):
    """Schema for updating an asset (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    asset_type: AssetType | None = None
    hostname: str | None = Field(None, max_length=255)
    fqdn: str | None = Field(None, max_length=255)
    mac_address: str | None = Field(None, pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    subnet: str | None = None
    vlan_id: int | None = Field(None, ge=0, le=4095)
    datacenter: str | None = Field(None, max_length=100)
    environment: str | None = Field(None, max_length=50)
    is_internal: bool | None = None
    is_critical: bool | None = None
    criticality_score: int | None = Field(None, ge=0, le=100)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class AssetResponse(AssetBase):
    """Schema for asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str | None = None
    city: str | None = None
    first_seen: datetime
    last_seen: datetime
    bytes_in_total: int
    bytes_out_total: int
    connections_in: int
    connections_out: int
    created_at: datetime
    updated_at: datetime


class AssetSummary(BaseModel):
    """Minimal asset info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None
    asset_type: AssetType
    ip_address: str
    hostname: str | None
    is_internal: bool
    is_critical: bool
    last_seen: datetime


class AssetList(BaseModel):
    """Paginated list of assets."""

    items: list[AssetSummary]
    total: int
    page: int
    page_size: int
    pages: int


class ServiceResponse(BaseModel):
    """Schema for service response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    port: int
    protocol: int
    name: str | None
    service_type: str | None
    version: str | None
    first_seen: datetime
    last_seen: datetime
    bytes_total: int
    connections_total: int


class AssetWithServices(AssetResponse):
    """Asset with its services."""

    services: list[ServiceResponse]


class ApplicationBase(BaseModel):
    """Base schema for application."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    environment: str | None = Field(None, max_length=50)
    criticality: str | None = Field(None, pattern=r"^(low|medium|high|critical)$")
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class ApplicationCreate(ApplicationBase):
    """Schema for creating an application."""

    asset_ids: list[UUID] | None = None


class ApplicationResponse(ApplicationBase):
    """Schema for application response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ApplicationWithAssets(ApplicationResponse):
    """Application with its member assets."""

    assets: list[AssetSummary]
