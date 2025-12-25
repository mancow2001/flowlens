"""Asset and Service models for dependency graph nodes.

Assets represent network entities (servers, workstations, etc.)
Services represent logical services running on ports.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import SoftDeleteModel, TimestampMixin, UUIDMixin, Base

if TYPE_CHECKING:
    from flowlens.models.dependency import Dependency


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
        nullable=False,
        server_default="now()",
    )

    last_seen: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default="now()",
        index=True,
    )

    # Traffic stats (updated by aggregation)
    bytes_in_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    bytes_out_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    connections_in: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    connections_out: Mapped[int] = mapped_column(
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
        nullable=False,
        server_default="now()",
    )

    last_seen: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default="now()",
    )

    # Traffic stats
    bytes_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    connections_total: Mapped[int] = mapped_column(
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

    __table_args__ = (
        Index(
            "ix_app_members_app_asset",
            "application_id", "asset_id",
            unique=True,
        ),
    )
