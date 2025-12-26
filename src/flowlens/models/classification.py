"""CIDR classification rules for dynamic asset grouping.

Classification rules define how assets are grouped based on their IP addresses.
Rules are evaluated at query time to determine environment, datacenter, and location.
More specific CIDRs (longer prefix) take priority over broader ones.
"""

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CIDR
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
