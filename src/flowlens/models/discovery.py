"""Discovery status tracking models."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import BaseModel


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


class DiscoveryProvider(BaseModel):
    """Configuration for a discovery provider instance.

    Stores connection settings and sync status for Kubernetes clusters,
    vCenter servers, and Nutanix clusters.
    """

    __tablename__ = "discovery_providers"

    # Identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    provider_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Connection settings (common fields)
    api_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    password_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    verify_ssl: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    timeout_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=15.0,
    )

    # Type-specific configs (JSONB for flexibility)
    # Kubernetes: {cluster_name, namespace, token_encrypted, ca_cert}
    k8s_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    # vCenter: {include_tags}
    vcenter_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    # Nutanix: (future extensibility)
    nutanix_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # State
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )
    sync_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="idle",
    )
    last_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Statistics
    assets_discovered: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    applications_discovered: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    @property
    def has_password(self) -> bool:
        """Check if password is configured."""
        return self.password_encrypted is not None

    @property
    def is_kubernetes(self) -> bool:
        """Check if this is a Kubernetes provider."""
        return self.provider_type == DiscoveryProviderType.KUBERNETES.value

    @property
    def is_vcenter(self) -> bool:
        """Check if this is a vCenter provider."""
        return self.provider_type == DiscoveryProviderType.VCENTER.value

    @property
    def is_nutanix(self) -> bool:
        """Check if this is a Nutanix provider."""
        return self.provider_type == DiscoveryProviderType.NUTANIX.value


class DiscoveryStatus(BaseModel):
    """Tracks discovery sync status for external systems.

    DEPRECATED: Use DiscoveryProvider.status fields instead.
    Kept for backward compatibility during migration.
    """

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="idle",
    )
    last_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
