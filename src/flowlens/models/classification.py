"""CIDR classification rules for dynamic asset grouping.

Classification rules define how assets are grouped based on their IP addresses.
Rules are evaluated at query time to determine environment, datacenter, and location.
More specific CIDRs (longer prefix) take priority over broader ones.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import BaseModel


class ClassificationRule(BaseModel):
    """CIDR-based classification rule.

    Defines how to classify assets based on their IP address.
    When an asset's IP matches the CIDR, the rule's attributes apply.

    Priority is determined by CIDR prefix length (more specific wins).
    For equal prefix lengths, lower priority value wins.
    """

    __tablename__ = "classification_rules"

    # Rule identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # CIDR range this rule applies to
    cidr: Mapped[str] = mapped_column(
        CIDR,
        nullable=False,
        index=True,
    )

    # Manual priority for same-length prefixes (lower wins)
    priority: Mapped[int] = mapped_column(
        default=100,
        nullable=False,
    )

    # Classification attributes
    environment: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    datacenter: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Asset type hint (can be overridden by discovery)
    asset_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Whether assets matching this CIDR are internal
    is_internal: Mapped[bool | None] = mapped_column(
        nullable=True,
    )

    # Owner/team defaults for matching assets
    default_owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    default_team: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Whether this rule is active
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # Index for efficient CIDR matching
        Index(
            "ix_classification_rules_cidr_lookup",
            "cidr",
            "is_active",
            postgresql_using="gist",
            postgresql_ops={"cidr": "inet_ops"},
        ),
        # Unique constraint on name
        UniqueConstraint("name", name="uq_classification_rules_name"),
    )

    def __repr__(self) -> str:
        return f"<ClassificationRule {self.name}: {self.cidr}>"


class AssetFeatures(BaseModel):
    """Computed behavioral features for an asset.

    Stores traffic pattern metrics computed from flow_aggregates,
    used by the classification engine to infer asset types.
    """

    __tablename__ = "asset_features"

    # Parent asset
    asset_id: Mapped["uuid.UUID"] = mapped_column(
        "asset_id",
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ip_address: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    # Window configuration
    window_size: Mapped[str] = mapped_column(
        String(20),  # '5min', '1hour', '24hour'
        nullable=False,
        index=True,
    )

    computed_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Traffic directionality
    inbound_flows: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    outbound_flows: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    inbound_bytes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    outbound_bytes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    fan_in_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    fan_out_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    fan_in_ratio: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Port & protocol behavior
    unique_dst_ports: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    unique_src_ports: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    well_known_port_ratio: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    ephemeral_port_ratio: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    persistent_listener_ports: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    protocol_distribution: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Flow characteristics
    avg_flow_duration_ms: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    avg_packets_per_flow: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    avg_bytes_per_packet: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    connection_churn_rate: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Temporal patterns
    active_hours_count: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    business_hours_ratio: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    traffic_variance: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Port-specific flags
    has_db_ports: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    has_storage_ports: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    has_web_ports: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    has_ssh_ports: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_asset_features_asset_window",
            "asset_id",
            "window_size",
            "computed_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<AssetFeatures {self.ip_address} ({self.window_size})>"


class ClassificationHistory(BaseModel):
    """Audit trail for asset classification changes.

    Records each time an asset's classification changes, including
    the scores and features that led to the decision.
    """

    __tablename__ = "classification_history"

    # Parent asset
    asset_id: Mapped["uuid.UUID"] = mapped_column(
        "asset_id",
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    classified_at: Mapped["datetime"] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Classification change
    previous_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    new_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        nullable=False,
    )

    # Score breakdown for all types
    scores: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Snapshot of features used for classification
    features_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Trigger source
    triggered_by: Mapped[str] = mapped_column(
        String(50),  # 'auto', 'manual', 'api'
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ClassificationHistory {self.asset_id}: {self.previous_type} -> {self.new_type}>"
