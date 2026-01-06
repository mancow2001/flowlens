"""Add folders table for organizing applications hierarchically.

Revision ID: 026
Revises: 025
Create Date: 2026-01-06

This migration adds support for organizing applications into folders
for the arc-based topology visualization.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create folders table and add folder_id to applications."""
    # Create folders table
    op.create_table(
        "folders",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Name and display
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        # Hierarchy (self-referential)
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Visual styling
        sa.Column("color", sa.String(7), nullable=True),  # Hex color
        sa.Column("icon", sa.String(50), nullable=True),
        # Ordering
        sa.Column("order", sa.Integer, nullable=False, server_default="0"),
        # Ownership
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("team", sa.String(100), nullable=True),
        # Metadata
        sa.Column("tags", JSONB, nullable=True),
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

    # Create indexes for folders
    op.create_index("ix_folders_name", "folders", ["name"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.create_index("ix_folders_team", "folders", ["team"])
    op.create_index("ix_folders_parent_order", "folders", ["parent_id", "order"])

    # Create unique constraint for folder name within parent
    op.create_unique_constraint(
        "uq_folders_parent_name",
        "folders",
        ["parent_id", "name"],
    )

    # Add folder_id column to applications table
    op.add_column(
        "applications",
        sa.Column(
            "folder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Create index for folder_id on applications
    op.create_index("ix_applications_folder_id", "applications", ["folder_id"])


def downgrade() -> None:
    """Remove folders table and folder_id from applications."""
    # Remove index and column from applications
    op.drop_index("ix_applications_folder_id", table_name="applications")
    op.drop_column("applications", "folder_id")

    # Remove folders table constraints and indexes
    op.drop_constraint("uq_folders_parent_name", "folders", type_="unique")
    op.drop_index("ix_folders_parent_order", table_name="folders")
    op.drop_index("ix_folders_team", table_name="folders")
    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_index("ix_folders_name", table_name="folders")

    # Drop folders table
    op.drop_table("folders")
