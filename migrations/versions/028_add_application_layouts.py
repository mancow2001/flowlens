"""Add application_layouts and asset_groups tables for persistent view positioning.

Revision ID: 028
Revises: 027
Create Date: 2026-01-08

This migration adds support for per-application, per-hop-depth layout persistence
in the application details view. Layouts are system-wide (all users see the same
positions) and each hop depth level can have its own layout configuration.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


# revision identifiers, used by Alembic.
revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create application_layouts and asset_groups tables."""
    # Create application_layouts table
    op.create_table(
        "application_layouts",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Parent application
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Hop depth (1-5)
        sa.Column("hop_depth", sa.Integer(), nullable=False),
        # Node positions as JSONB: {asset_id: {x, y}}
        sa.Column(
            "positions",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Viewport state: {scale, x, y}
        sa.Column("viewport", JSONB(), nullable=True),
        # Last modified by
        sa.Column("modified_by", sa.String(255), nullable=True),
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
        # Constraint: hop_depth between 1 and 5
        sa.CheckConstraint(
            "hop_depth >= 1 AND hop_depth <= 5",
            name="ck_application_layouts_hop_depth_range",
        ),
    )

    # Create indexes for application_layouts
    op.create_index(
        "ix_application_layouts_application_id",
        "application_layouts",
        ["application_id"],
    )

    # Create unique constraint: one layout per application per hop depth
    op.create_index(
        "ix_application_layouts_app_hop",
        "application_layouts",
        ["application_id", "hop_depth"],
        unique=True,
    )

    # Create asset_groups table
    op.create_table(
        "asset_groups",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Parent layout
        sa.Column(
            "layout_id",
            UUID(as_uuid=True),
            sa.ForeignKey("application_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Group metadata
        sa.Column("name", sa.String(255), nullable=False),
        # Visual styling
        sa.Column("color", sa.String(7), nullable=False, server_default="#3b82f6"),
        # Position of the group container
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        # Dimensions
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        # Visual state
        sa.Column("is_collapsed", sa.Boolean(), nullable=False, server_default="false"),
        # Member assets
        sa.Column("asset_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
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

    # Create index for asset_groups
    op.create_index(
        "ix_asset_groups_layout_id",
        "asset_groups",
        ["layout_id"],
    )


def downgrade() -> None:
    """Remove application_layouts and asset_groups tables."""
    # Drop asset_groups table and indexes
    op.drop_index("ix_asset_groups_layout_id", table_name="asset_groups")
    op.drop_table("asset_groups")

    # Drop application_layouts table and indexes
    op.drop_index("ix_application_layouts_app_hop", table_name="application_layouts")
    op.drop_index("ix_application_layouts_application_id", table_name="application_layouts")
    op.drop_table("application_layouts")
