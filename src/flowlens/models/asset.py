"""Asset and Service models for dependency graph nodes.

Assets represent network entities (servers, workstations, etc.)
Services represent logical services running on ports.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import SoftDeleteModel, TimestampMixin, UUIDMixin, Base

if TYPE_CHECKING:
    from flowlens.models.dependency import Dependency
    from flowlens.models.discovery import DiscoveryProvider
    from flowlens.models.gateway import AssetGateway
    from flowlens.models.segmentation import SegmentationPolicy


class AssetType(str, Enum):
    """Types of assets in the dependency graph.

    Note: The is_internal field on Asset tracks whether an asset is
    internal or external to the network. All auto-discovered assets
    start as UNKNOWN.
    """

    SERVER = "server"
    WORKSTATION = "workstation"
    DATABASE = "database"
    LOAD_BALANCER = "load_balancer"
    FIREWALL = "firewall"
    ROUTER = "router"
    SWITCH = "switch"
    STORAGE = "storage"
    CONTAINER = "container"
    VIRTUAL_MACHINE = "virtual_machine"
    CLOUD_SERVICE = "cloud_service"
    UNKNOWN = "unknown"


class Environment(str, Enum):
    """Environment types for assets and classification rules."""

    PROD = "prod"
    UAT = "uat"
    QA = "qa"
    TEST = "test"
    DEV = "dev"


class Asset(SoftDeleteModel):
    """Network asset (node in the dependency graph).

    Represents any addressable entity on the network that can be
    a source or destination of network flows.
    """

    __tablename__ = "assets"

    # Identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    asset_type: Mapped[AssetType] = mapped_column(
        String(50),
        nullable=False,
        default=AssetType.UNKNOWN,
        index=True,
    )

    # Network identity
    ip_address: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        unique=True,
        index=True,
    )

    mac_address: Mapped[str | None] = mapped_column(
        String(17),  # XX:XX:XX:XX:XX:XX
        nullable=True,
    )

    hostname: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    fqdn: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Network context
    subnet: Mapped[str | None] = mapped_column(
        CIDR,
        nullable=True,
        index=True,
    )

    vlan_id: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # Location
    datacenter: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    environment: Mapped[str | None] = mapped_column(
        String(50),  # production, staging, development
        nullable=True,
        index=True,
    )

    # GeoIP enrichment
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Classification
    is_internal: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )

    is_critical: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    criticality_score: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Auto-classification fields
    classification_locked: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    classification_confidence: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    classification_scores: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    last_classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    classification_method: Mapped[str | None] = mapped_column(
        String(50),  # 'auto', 'manual', 'api'
        nullable=True,
    )

    # Ownership
    owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    team: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Integration
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    extra_data: Mapped[dict | None] = mapped_column(
        "metadata",  # Keep column name as 'metadata' in database
        JSONB,
        nullable=True,
        default=dict,
    )

    # Discovery info
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        index=True,
    )

    # Discovery provider tracking
    discovered_by_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Traffic stats (updated by aggregation)
    bytes_in_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    bytes_out_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    connections_in: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    connections_out: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    # Relationships
    services: Mapped[list["Service"]] = relationship(
        "Service",
        back_populates="asset",
        cascade="all, delete-orphan",
    )

    outbound_dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        foreign_keys="Dependency.source_asset_id",
        back_populates="source_asset",
    )

    inbound_dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        foreign_keys="Dependency.target_asset_id",
        back_populates="target_asset",
    )

    # Gateway relationships
    gateway_relationships: Mapped[list["AssetGateway"]] = relationship(
        "AssetGateway",
        foreign_keys="AssetGateway.source_asset_id",
        back_populates="source_asset",
    )

    gateway_clients: Mapped[list["AssetGateway"]] = relationship(
        "AssetGateway",
        foreign_keys="AssetGateway.gateway_asset_id",
        back_populates="gateway_asset",
    )

    __table_args__ = (
        CheckConstraint("criticality_score >= 0 AND criticality_score <= 100"),
        Index("ix_assets_type_environment", "asset_type", "environment"),
        Index("ix_assets_subnet_type", "subnet", "asset_type"),
        Index("ix_assets_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Asset {self.name} ({self.ip_address})>"


class Service(Base, UUIDMixin, TimestampMixin):
    """Service running on an asset.

    Represents a logical service identified by port and protocol.
    """

    __tablename__ = "services"

    # Parent asset
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Service identity
    port: Mapped[int] = mapped_column(
        nullable=False,
    )

    protocol: Mapped[int] = mapped_column(
        nullable=False,  # 6=TCP, 17=UDP
    )

    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Inferred or configured service info
    service_type: Mapped[str | None] = mapped_column(
        String(50),  # http, https, ssh, mysql, etc.
        nullable=True,
        index=True,
    )

    version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Discovery
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    # Traffic stats
    bytes_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    connections_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    # Relationship
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="services",
    )

    __table_args__ = (
        Index(
            "ix_services_asset_port_proto",
            "asset_id", "port", "protocol",
            unique=True,
        ),
        CheckConstraint("port >= 0 AND port <= 65535"),
        CheckConstraint("protocol >= 0 AND protocol <= 255"),
    )

    def __repr__(self) -> str:
        proto = "TCP" if self.protocol == 6 else "UDP" if self.protocol == 17 else str(self.protocol)
        return f"<Service {self.port}/{proto} on {self.asset_id}>"


class Application(Base, UUIDMixin, TimestampMixin):
    """Logical application grouping multiple assets.

    Applications are user-defined groupings that help organize
    assets into business-meaningful units.
    """

    __tablename__ = "applications"

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

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    team: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    environment: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    criticality: Mapped[str | None] = mapped_column(
        String(20),  # low, medium, high, critical
        nullable=True,
    )

    tags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    extra_data: Mapped[dict | None] = mapped_column(
        "metadata",  # Keep column name as 'metadata' in database
        JSONB,
        nullable=True,
        default=dict,
    )

    # Relationships
    members: Mapped[list["ApplicationMember"]] = relationship(
        "ApplicationMember",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    policies: Mapped[list["SegmentationPolicy"]] = relationship(
        "SegmentationPolicy",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Application {self.name}>"


class ApplicationMember(Base, UUIDMixin, TimestampMixin):
    """Association between applications and assets."""

    __tablename__ = "application_members"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str | None] = mapped_column(
        String(50),  # frontend, backend, database, cache, etc.
        nullable=True,
    )

    # Relationships
    application: Mapped["Application"] = relationship(
        "Application",
        back_populates="members",
    )

    asset: Mapped["Asset"] = relationship("Asset")

    entry_points: Mapped[list["EntryPoint"]] = relationship(
        "EntryPoint",
        back_populates="member",
        cascade="all, delete-orphan",
        order_by="EntryPoint.order",
    )

    __table_args__ = (
        Index(
            "ix_app_members_app_asset",
            "application_id", "asset_id",
            unique=True,
        ),
    )

    @property
    def is_entry_point(self) -> bool:
        """Check if this member has any entry points defined."""
        return len(self.entry_points) > 0


class EntryPoint(Base, UUIDMixin, TimestampMixin):
    """Entry point definition for an application member.

    Allows defining multiple entry points (port/protocol combinations)
    for a single asset within an application. For example, a web server
    might have entry points on both port 80 and 443.
    """

    __tablename__ = "entry_points"

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application_members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    port: Mapped[int] = mapped_column(
        nullable=False,
    )

    protocol: Mapped[int] = mapped_column(
        nullable=False,
        default=6,  # TCP by default
    )

    order: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    label: Mapped[str | None] = mapped_column(
        String(50),  # e.g., "HTTP", "HTTPS", "API"
        nullable=True,
    )

    # Relationship
    member: Mapped["ApplicationMember"] = relationship(
        "ApplicationMember",
        back_populates="entry_points",
    )

    __table_args__ = (
        CheckConstraint("port >= 1 AND port <= 65535"),
        CheckConstraint("protocol >= 0 AND protocol <= 255"),
        Index(
            "ix_entry_points_member_port_proto",
            "member_id", "port", "protocol",
            unique=True,
        ),
    )
