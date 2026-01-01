"""Pydantic schemas for Asset API endpoints."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator

from flowlens.models.asset import AssetType, Environment


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
    environment: Environment | None = None
    is_internal: bool = True
    is_critical: bool = False
    criticality_score: int = Field(0, ge=0, le=100)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None

    @field_validator("environment", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Environment | None:
        """Convert empty string to None for environment field."""
        if v == "" or v is None:
            return None
        return v


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
    environment: Environment | None = None
    is_internal: bool | None = None
    is_critical: bool | None = None
    criticality_score: int | None = Field(None, ge=0, le=100)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None

    @field_validator("environment", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Environment | None:
        """Convert empty string to None for environment field."""
        if v == "" or v is None:
            return None
        return v


class AssetResponse(BaseModel):
    """Schema for asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None = None
    asset_type: AssetType
    ip_address: str  # String for response serialization
    hostname: str | None = None
    fqdn: str | None = None
    mac_address: str | None = None
    subnet: str | None = None
    vlan_id: int | None = None
    datacenter: str | None = None
    environment: str | None = None
    is_internal: bool = True
    is_critical: bool = False
    criticality_score: int = 0
    owner: str | None = None
    team: str | None = None
    external_id: str | None = None
    description: str | None = None
    tags: dict[str, str] | None = None
    metadata: dict | None = None
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

    @field_validator("ip_address", "subnet", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str | None:
        """Convert INET/CIDR types to string."""
        if v is None:
            return None
        return str(v)


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


class EntryPointCreate(BaseModel):
    """Schema for creating an entry point on an application member."""

    port: int = Field(..., ge=1, le=65535)
    protocol: int = Field(6, ge=0, le=255)  # IANA protocol number, default TCP
    order: int = Field(0, ge=0)
    label: str | None = Field(None, max_length=50)


class EntryPointUpdate(BaseModel):
    """Schema for updating an entry point."""

    port: int | None = Field(None, ge=1, le=65535)
    protocol: int | None = Field(None, ge=0, le=255)
    order: int | None = Field(None, ge=0)
    label: str | None = Field(None, max_length=50)


class EntryPointResponse(BaseModel):
    """Schema for entry point response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    member_id: UUID
    port: int
    protocol: int
    order: int
    label: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationMemberCreate(BaseModel):
    """Schema for adding an asset to an application."""

    asset_id: UUID
    role: str | None = Field(None, max_length=50)
    entry_points: list[EntryPointCreate] | None = None


class ApplicationMemberUpdate(BaseModel):
    """Schema for updating an application member."""

    role: str | None = Field(None, max_length=50)


class ApplicationMemberResponse(BaseModel):
    """Schema for application member response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    asset: AssetSummary
    role: str | None
    entry_points: list[EntryPointResponse]
    created_at: datetime
    updated_at: datetime

    @property
    def is_entry_point(self) -> bool:
        """Convenience property to check if member has any entry points."""
        return len(self.entry_points) > 0


class ApplicationCreate(ApplicationBase):
    """Schema for creating an application."""

    members: list[ApplicationMemberCreate] | None = None


class ApplicationUpdate(BaseModel):
    """Schema for updating an application (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    environment: str | None = Field(None, max_length=50)
    criticality: str | None = Field(None, pattern=r"^(low|medium|high|critical)$")
    tags: dict[str, str] | None = None
    metadata: dict | None = None


class ApplicationResponse(ApplicationBase):
    """Schema for application response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ApplicationWithMembers(ApplicationResponse):
    """Application with its member assets."""

    members: list[ApplicationMemberResponse]


class ApplicationList(BaseModel):
    """Paginated list of applications."""

    items: list[ApplicationResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Bulk import/export schemas
class AssetExportRow(BaseModel):
    """Single row in asset export (CSV/JSON)."""

    ip_address: str
    name: str
    hostname: str | None = None
    asset_type: str | None = None
    owner: str | None = None
    team: str | None = None
    description: str | None = None
    is_critical: bool = False
    environment: str | None = None
    datacenter: str | None = None
    tags: str | None = None  # JSON string for CSV compatibility


class AssetImportRow(BaseModel):
    """Single row for asset import."""

    ip_address: str
    name: str | None = None
    hostname: str | None = None
    asset_type: str | None = None
    owner: str | None = None
    team: str | None = None
    description: str | None = None
    is_critical: bool | None = None
    tags: str | None = None  # JSON string


class AssetImportValidation(BaseModel):
    """Validation result for a single import row."""

    row_number: int
    ip_address: str
    status: str  # "create", "update", "skip", "error"
    message: str | None = None
    changes: dict[str, dict[str, Any]] | None = None  # field -> {old, new}


class AssetImportPreview(BaseModel):
    """Preview of what an import will do before committing."""

    total_rows: int
    to_create: int
    to_update: int
    to_skip: int
    errors: int
    validations: list[AssetImportValidation]


class AssetImportResult(BaseModel):
    """Result of committing an asset import."""

    created: int
    updated: int
    skipped: int
    errors: int
    error_details: list[str] | None = None
