"""Add segmentation policy tables for micro-segmentation rule management.

Revision ID: 025_segmentation_policies
Revises: 024_discovery_providers
Create Date: 2025-01-05

This migration adds support for generating and managing segmentation policies
from application topology maps, including version tracking and comparison.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create segmentation policy tables."""
    # Create segmentation_policies table
    op.create_table(
        "segmentation_policies",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Application reference
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Policy metadata
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Policy stance: 'allow_list' (zero trust) or 'deny_list'
        sa.Column(
            "stance",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'allow_list'"),
        ),
        # Status workflow: draft -> pending_review -> approved -> active -> archived
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        # Version tracking
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        # Generation metadata
        sa.Column("generated_from_topology_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by", sa.String(100), nullable=True),
        # Approval workflow
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # Rule count statistics (cached for display)
        sa.Column("rule_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inbound_rule_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("outbound_rule_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("internal_rule_count", sa.Integer, nullable=False, server_default="0"),
        # Extra metadata
        sa.Column("metadata", JSONB, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create indexes for segmentation_policies
    op.create_index(
        "ix_segmentation_policies_application_id",
        "segmentation_policies",
        ["application_id"],
    )
    op.create_index(
        "ix_segmentation_policies_status",
        "segmentation_policies",
        ["status"],
    )
    op.create_index(
        "ix_segmentation_policies_is_active",
        "segmentation_policies",
        ["is_active"],
    )
    op.create_index(
        "ix_segmentation_policies_app_active",
        "segmentation_policies",
        ["application_id", "is_active"],
    )

    # Create segmentation_policy_rules table
    op.create_table(
        "segmentation_policy_rules",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Policy reference
        sa.Column(
            "policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("segmentation_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Rule ordering
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("rule_order", sa.Integer, nullable=False, server_default="0"),
        # Rule type: 'inbound', 'outbound', 'internal'
        sa.Column("rule_type", sa.String(20), nullable=False),
        # Source specification
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column(
            "source_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_cidr", sa.String(50), nullable=True),
        sa.Column(
            "source_app_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_label", sa.String(255), nullable=True),
        # Destination specification
        sa.Column("dest_type", sa.String(20), nullable=False),
        sa.Column(
            "dest_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dest_cidr", sa.String(50), nullable=True),
        sa.Column(
            "dest_app_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dest_label", sa.String(255), nullable=True),
        # Service specification
        sa.Column("port", sa.Integer, nullable=True),
        sa.Column("port_range_end", sa.Integer, nullable=True),
        sa.Column("protocol", sa.Integer, nullable=False, server_default="6"),
        sa.Column("service_label", sa.String(50), nullable=True),
        # Action: 'allow' or 'deny'
        sa.Column("action", sa.String(10), nullable=False, server_default=sa.text("'allow'")),
        # Rule metadata
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_auto_generated", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        # Evidence (for auto-generated rules)
        sa.Column("generated_from_dependency_id", UUID(as_uuid=True), nullable=True),
        sa.Column("generated_from_entry_point_id", UUID(as_uuid=True), nullable=True),
        # Traffic metrics at generation time
        sa.Column("bytes_observed", sa.BigInteger, nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints
        sa.CheckConstraint("port IS NULL OR (port >= 0 AND port <= 65535)", name="ck_rule_port_range"),
        sa.CheckConstraint("protocol >= 0 AND protocol <= 255", name="ck_rule_protocol_range"),
    )

    # Create indexes for segmentation_policy_rules
    op.create_index(
        "ix_segmentation_policy_rules_policy_id",
        "segmentation_policy_rules",
        ["policy_id"],
    )
    op.create_index(
        "ix_segmentation_policy_rules_rule_type",
        "segmentation_policy_rules",
        ["rule_type"],
    )
    op.create_index(
        "ix_segmentation_policy_rules_policy_order",
        "segmentation_policy_rules",
        ["policy_id", "priority", "rule_order"],
    )

    # Create segmentation_policy_versions table
    op.create_table(
        "segmentation_policy_versions",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Policy reference
        sa.Column(
            "policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("segmentation_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Version info
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("version_label", sa.String(100), nullable=True),
        # Snapshot of policy state at this version
        sa.Column("stance", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rules_snapshot", JSONB, nullable=False),
        # Change summary
        sa.Column("rules_added", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rules_removed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rules_modified", sa.Integer, nullable=False, server_default="0"),
        # Who made this version
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("change_reason", sa.Text, nullable=True),
        # Approval info
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create indexes for segmentation_policy_versions
    op.create_index(
        "ix_segmentation_policy_versions_policy_id",
        "segmentation_policy_versions",
        ["policy_id"],
    )
    # Unique constraint: one version number per policy
    op.create_unique_constraint(
        "uq_policy_version_number",
        "segmentation_policy_versions",
        ["policy_id", "version_number"],
    )


def downgrade() -> None:
    """Remove segmentation policy tables."""
    # Drop segmentation_policy_versions table
    op.drop_constraint(
        "uq_policy_version_number",
        "segmentation_policy_versions",
        type_="unique",
    )
    op.drop_index(
        "ix_segmentation_policy_versions_policy_id",
        table_name="segmentation_policy_versions",
    )
    op.drop_table("segmentation_policy_versions")

    # Drop segmentation_policy_rules table
    op.drop_index(
        "ix_segmentation_policy_rules_policy_order",
        table_name="segmentation_policy_rules",
    )
    op.drop_index(
        "ix_segmentation_policy_rules_rule_type",
        table_name="segmentation_policy_rules",
    )
    op.drop_index(
        "ix_segmentation_policy_rules_policy_id",
        table_name="segmentation_policy_rules",
    )
    op.drop_table("segmentation_policy_rules")

    # Drop segmentation_policies table
    op.drop_index(
        "ix_segmentation_policies_app_active",
        table_name="segmentation_policies",
    )
    op.drop_index(
        "ix_segmentation_policies_is_active",
        table_name="segmentation_policies",
    )
    op.drop_index(
        "ix_segmentation_policies_status",
        table_name="segmentation_policies",
    )
    op.drop_index(
        "ix_segmentation_policies_application_id",
        table_name="segmentation_policies",
    )
    op.drop_table("segmentation_policies")
