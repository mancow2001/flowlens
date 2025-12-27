"""Gateway relationship models.

Models for tracking gateway/router relationships inferred from flow data.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TemporalMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from flowlens.models.asset import Asset


class GatewayRole(str, Enum):
    """Role of a gateway in the network path."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ECMP = "ecmp"


class InferenceMethod(str, Enum):
    """How the gateway relationship was discovered."""

    NEXT_HOP = "next_hop"
    EXPORTER = "exporter"
    MANUAL = "manual"
    API = "api"


class GatewayObservation(Base, UUIDMixin):
    """Intermediate gateway observation before rollup.

    Stores gateway observations from flow processing
    before they are aggregated into AssetGateway records.
    """

    __tablename__ = "gateway_observations"

    source_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    gateway_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    destination_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )

    observation_source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    exporter_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )

    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    bytes_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    flows_count: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    is_processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    __table_args__ = (
        Index(
            "ix_gateway_obs_unprocessed",
            "window_start",
            postgresql_where="is_processed = false",
        ),
        Index(
            "ix_gateway_obs_source_window",
            "source_ip",
            "window_start",
        ),
    )


class AssetGateway(Base, UUIDMixin, TimestampMixin, TemporalMixin):
    """Gateway relationship for an asset.

    Represents the gateway/router an asset uses to reach
    other networks. Supports multiple gateways (ECMP/failover).
    """

    __tablename__ = "asset_gateways"

    # Relationship endpoints
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    gateway_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Destination context
    destination_network: Mapped[str | None] = mapped_column(
        CIDR,
        nullable=True,  # NULL = default gateway
    )

    # Classification
    gateway_role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=GatewayRole.PRIMARY.value,
    )

    is_default_gateway: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Traffic metrics
    bytes_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    flows_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    bytes_last_24h: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    bytes_last_7d: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    traffic_share: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Confidence scoring
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    confidence_scores: Mapped[dict | None] = mapped_column(
        JSONB,
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
        index=True,
    )

    inference_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=InferenceMethod.NEXT_HOP.value,
    )

    last_inferred_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    # Relationships
    source_asset: Mapped["Asset"] = relationship(
        "Asset",
        foreign_keys="AssetGateway.source_asset_id",
        back_populates="gateway_relationships",
    )

    gateway_asset: Mapped["Asset"] = relationship(
        "Asset",
        foreign_keys="AssetGateway.gateway_asset_id",
        back_populates="gateway_clients",
    )

    __table_args__ = (
        # Unique current gateway per source/gateway/destination combo
        Index(
            "ix_gateways_source_gateway_dest_current",
            "source_asset_id",
            "gateway_asset_id",
            "destination_network",
            unique=True,
            postgresql_where="valid_to IS NULL",
        ),
        # For traversal queries
        Index(
            "ix_gateways_source_current",
            "source_asset_id",
            postgresql_where="valid_to IS NULL",
        ),
        Index(
            "ix_gateways_gateway_current",
            "gateway_asset_id",
            postgresql_where="valid_to IS NULL",
        ),
        Index(
            "ix_gateways_last_seen",
            "last_seen",
            postgresql_where="valid_to IS NULL",
        ),
        # Prevent self-references
        CheckConstraint(
            "source_asset_id != gateway_asset_id",
            name="asset_gateways_no_self_gateway",
        ),
        CheckConstraint(
            "gateway_role IN ('primary', 'secondary', 'ecmp')",
            name="asset_gateways_role_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<AssetGateway source={self.source_asset_id} gateway={self.gateway_asset_id}>"
