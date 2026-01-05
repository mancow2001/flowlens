"""Schemas for discovery provider CRUD operations."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class DiscoveryProviderType(str, Enum):
    """Discovery provider type enumeration."""

    KUBERNETES = "kubernetes"
    VCENTER = "vcenter"
    NUTANIX = "nutanix"


class DiscoveryProviderStatus(str, Enum):
    """Discovery provider sync status enumeration."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# Type-specific configuration schemas


class KubernetesConfig(BaseModel):
    """Kubernetes-specific configuration."""

    cluster_name: str = Field(default="default-cluster", max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    token: str | None = Field(default=None, description="Service account token (write-only)")
    ca_cert: str | None = Field(default=None, description="CA certificate PEM content")


class VCenterConfig(BaseModel):
    """vCenter-specific configuration."""

    include_tags: bool = Field(default=True, description="Fetch and sync vSphere tags")


class NutanixConfig(BaseModel):
    """Nutanix-specific configuration (extensible)."""

    pass


# Request schemas


class DiscoveryProviderCreate(BaseModel):
    """Request schema for creating a discovery provider."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique provider name")
    display_name: str | None = Field(default=None, max_length=255)
    provider_type: DiscoveryProviderType
    api_url: str = Field(..., min_length=1, max_length=500, description="API endpoint URL")
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, description="Password (write-only, encrypted at rest)")
    verify_ssl: bool = Field(default=True)
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    is_enabled: bool = Field(default=True)
    priority: int = Field(default=100, ge=1, le=1000, description="Lower = higher priority for IP collisions")
    sync_interval_minutes: int = Field(default=15, ge=5, le=1440)

    # Type-specific configs
    kubernetes_config: KubernetesConfig | None = None
    vcenter_config: VCenterConfig | None = None
    nutanix_config: NutanixConfig | None = None


class DiscoveryProviderUpdate(BaseModel):
    """Request schema for updating a discovery provider."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    api_url: str | None = Field(default=None, min_length=1, max_length=500)
    username: str | None = None
    password: str | None = Field(default=None, description="New password (leave empty to keep existing)")
    verify_ssl: bool | None = None
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=60.0)
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    sync_interval_minutes: int | None = Field(default=None, ge=5, le=1440)

    # Type-specific configs
    kubernetes_config: KubernetesConfig | None = None
    vcenter_config: VCenterConfig | None = None
    nutanix_config: NutanixConfig | None = None


# Response schemas


class DiscoveryProviderResponse(BaseModel):
    """Response schema for a discovery provider."""

    id: UUID
    name: str
    display_name: str | None
    provider_type: str
    api_url: str
    username: str | None
    has_password: bool
    verify_ssl: bool
    timeout_seconds: float
    is_enabled: bool
    priority: int
    sync_interval_minutes: int

    # Type-specific configs (tokens/passwords masked)
    kubernetes_config: dict | None
    vcenter_config: dict | None
    nutanix_config: dict | None

    # Status
    status: str
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None

    # Statistics
    assets_discovered: int
    applications_discovered: int

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiscoveryProviderSummary(BaseModel):
    """Summary response for listing discovery providers."""

    id: UUID
    name: str
    display_name: str | None
    provider_type: str
    api_url: str
    is_enabled: bool
    status: str
    last_success_at: datetime | None
    assets_discovered: int

    class Config:
        from_attributes = True


class DiscoveryProviderListResponse(BaseModel):
    """Response schema for listing discovery providers."""

    items: list[DiscoveryProviderSummary]
    total: int


class ConnectionTestRequest(BaseModel):
    """Request schema for testing provider connection before saving."""

    test_values: dict | None = Field(
        default=None,
        description="Override values to test (for testing before save)",
    )


class ConnectionTestResponse(BaseModel):
    """Response schema for connection test results."""

    success: bool
    message: str
    details: dict | None = Field(
        default=None,
        description="Additional details (e.g., namespaces found, VMs found)",
    )


class SyncTriggerResponse(BaseModel):
    """Response schema for triggering a sync."""

    success: bool
    message: str
    provider_id: UUID
