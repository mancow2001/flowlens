"""Segmentation policy models for micro-segmentation rule management.

Provides models for generating, storing, and versioning segmentation
policies derived from application topology maps.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from flowlens.models.asset import Application


class PolicyStance(str, Enum):
    """Policy stance enumeration."""

    ALLOW_LIST = "allow_list"  # Zero trust: deny by default, allow specified
    DENY_LIST = "deny_list"  # Allow by default, deny specified


class PolicyStatus(str, Enum):
    """Policy approval workflow status."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RuleType(str, Enum):
    """Rule type classification."""

    INBOUND = "inbound"  # External -> Entry point
    OUTBOUND = "outbound"  # App member -> External
    INTERNAL = "internal"  # App member -> App member


class RuleAction(str, Enum):
    """Rule action."""

    ALLOW = "allow"
    DENY = "deny"


class SegmentationPolicy(Base, UUIDMixin, TimestampMixin):
    """Segmentation policy for an application.

    Represents a set of network segmentation rules generated from
    or defined for a specific application's topology.
    """

    __tablename__ = "segmentation_policies"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    stance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PolicyStance.ALLOW_LIST.value,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PolicyStatus.DRAFT.value,
    )

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Generation metadata
    generated_from_topology_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Approval workflow
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Rule count statistics (cached for display)
    rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    inbound_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    outbound_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    internal_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)

    # Extra metadata
    extra_data: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )

    # Relationships
    application: Mapped["Application"] = relationship(
        "Application", back_populates="policies"
    )
    rules: Mapped[list["SegmentationPolicyRule"]] = relationship(
        "SegmentationPolicyRule",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="SegmentationPolicyRule.priority, SegmentationPolicyRule.rule_order",
    )
    versions: Mapped[list["SegmentationPolicyVersion"]] = relationship(
        "SegmentationPolicyVersion",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="SegmentationPolicyVersion.version_number.desc()",
    )

    def update_rule_counts(self) -> None:
        """Update cached rule count statistics."""
        self.rule_count = len(self.rules)
        self.inbound_rule_count = sum(
            1 for r in self.rules if r.rule_type == RuleType.INBOUND.value
        )
        self.outbound_rule_count = sum(
            1 for r in self.rules if r.rule_type == RuleType.OUTBOUND.value
        )
        self.internal_rule_count = sum(
            1 for r in self.rules if r.rule_type == RuleType.INTERNAL.value
        )


class SegmentationPolicyRule(Base, UUIDMixin, TimestampMixin):
    """Individual rule within a segmentation policy.

    Defines a single allow or deny rule for network traffic
    between specified sources and destinations.
    """

    __tablename__ = "segmentation_policy_rules"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("segmentation_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Rule ordering
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    rule_order: Mapped[int] = mapped_column(nullable=False, default=0)

    # Rule type: 'inbound', 'outbound', 'internal'
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Source specification
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_cidr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Destination specification
    dest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dest_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    dest_cidr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dest_app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    dest_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Service specification
    port: Mapped[int | None] = mapped_column(nullable=True)
    port_range_end: Mapped[int | None] = mapped_column(nullable=True)
    protocol: Mapped[int] = mapped_column(nullable=False, default=6)
    service_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Action: 'allow' or 'deny'
    action: Mapped[str] = mapped_column(
        String(10), nullable=False, default=RuleAction.ALLOW.value
    )

    # Rule metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_auto_generated: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Evidence (for auto-generated rules)
    generated_from_dependency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    generated_from_entry_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Traffic metrics at generation time
    bytes_observed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    policy: Mapped["SegmentationPolicy"] = relationship(
        "SegmentationPolicy", back_populates="rules"
    )

    def to_dict(self) -> dict:
        """Convert rule to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "rule_type": self.rule_type,
            "priority": self.priority,
            "rule_order": self.rule_order,
            "source_type": self.source_type,
            "source_asset_id": str(self.source_asset_id) if self.source_asset_id else None,
            "source_cidr": self.source_cidr,
            "source_app_id": str(self.source_app_id) if self.source_app_id else None,
            "source_label": self.source_label,
            "dest_type": self.dest_type,
            "dest_asset_id": str(self.dest_asset_id) if self.dest_asset_id else None,
            "dest_cidr": self.dest_cidr,
            "dest_app_id": str(self.dest_app_id) if self.dest_app_id else None,
            "dest_label": self.dest_label,
            "port": self.port,
            "port_range_end": self.port_range_end,
            "protocol": self.protocol,
            "service_label": self.service_label,
            "action": self.action,
            "description": self.description,
            "is_auto_generated": self.is_auto_generated,
            "is_enabled": self.is_enabled,
            "bytes_observed": self.bytes_observed,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class SegmentationPolicyVersion(Base, UUIDMixin):
    """Historical version snapshot of a policy.

    Captures the complete state of a policy at a point in time,
    enabling version comparison and rollback capabilities.
    """

    __tablename__ = "segmentation_policy_versions"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("segmentation_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version info
    version_number: Mapped[int] = mapped_column(nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Snapshot of policy state at this version
    stance: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rules_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Change summary
    rules_added: Mapped[int] = mapped_column(nullable=False, default=0)
    rules_removed: Mapped[int] = mapped_column(nullable=False, default=0)
    rules_modified: Mapped[int] = mapped_column(nullable=False, default=0)

    # Who made this version
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Approval info (if this version was approved)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamp (no updated_at since versions are immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    policy: Mapped["SegmentationPolicy"] = relationship(
        "SegmentationPolicy", back_populates="versions"
    )
