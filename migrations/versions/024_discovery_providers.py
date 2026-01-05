"""Add discovery_providers table for multi-instance discovery support.

Revision ID: 024_discovery_providers
Revises: 023_add_discovery_status
Create Date: 2025-01-05

This migration adds support for multiple discovery provider instances
(Kubernetes clusters, vCenter servers, Nutanix clusters) by storing
configurations in the database instead of environment variables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create discovery_providers table and add foreign key to assets."""
    # Create discovery_providers table
    op.create_table(
        "discovery_providers",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("provider_type", sa.String(50), nullable=False),
        # Connection settings
        sa.Column("api_url", sa.String(500), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.Text, nullable=True),
        sa.Column("verify_ssl", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("timeout_seconds", sa.Float, nullable=False, server_default="15.0"),
        # Type-specific configs
        sa.Column("k8s_config", JSONB, nullable=True),
        sa.Column("vcenter_config", JSONB, nullable=True),
        sa.Column("nutanix_config", JSONB, nullable=True),
        # State
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("sync_interval_minutes", sa.Integer, nullable=False, server_default="15"),
        # Status tracking
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'idle'")),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        # Statistics
        sa.Column("assets_discovered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("applications_discovered", sa.Integer, nullable=False, server_default="0"),
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

    # Create indexes
    op.create_index(
        "ix_discovery_providers_name",
        "discovery_providers",
        ["name"],
    )
    op.create_index(
        "ix_discovery_providers_provider_type",
        "discovery_providers",
        ["provider_type"],
    )
    op.create_index(
        "ix_discovery_providers_is_enabled",
        "discovery_providers",
        ["is_enabled"],
    )
    op.create_index(
        "ix_discovery_providers_type_enabled",
        "discovery_providers",
        ["provider_type", "is_enabled"],
    )

    # Add discovered_by_provider_id to assets table
    op.add_column(
        "assets",
        sa.Column("discovered_by_provider_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assets_discovery_provider",
        "assets",
        "discovery_providers",
        ["discovered_by_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_assets_discovered_by_provider_id",
        "assets",
        ["discovered_by_provider_id"],
    )


def downgrade() -> None:
    """Remove discovery_providers table and foreign key from assets."""
    # Remove foreign key and column from assets
    op.drop_index("ix_assets_discovered_by_provider_id", table_name="assets")
    op.drop_constraint("fk_assets_discovery_provider", "assets", type_="foreignkey")
    op.drop_column("assets", "discovered_by_provider_id")

    # Drop indexes
    op.drop_index("ix_discovery_providers_type_enabled", table_name="discovery_providers")
    op.drop_index("ix_discovery_providers_is_enabled", table_name="discovery_providers")
    op.drop_index("ix_discovery_providers_provider_type", table_name="discovery_providers")
    op.drop_index("ix_discovery_providers_name", table_name="discovery_providers")

    # Drop table
    op.drop_table("discovery_providers")
