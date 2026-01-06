"""Add topology_exclusions table for user-specific entity hiding.

Revision ID: 027
Revises: 026
Create Date: 2026-01-06

This migration adds support for users to exclude specific folders or
applications from the topology visualization.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create topology_exclusions table."""
    op.create_table(
        "topology_exclusions",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # User reference
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Entity being excluded
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        # Optional reason
        sa.Column("reason", sa.String(500), nullable=True),
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
        "ix_topology_exclusions_user_id",
        "topology_exclusions",
        ["user_id"],
    )
    op.create_index(
        "ix_topology_exclusions_entity_type",
        "topology_exclusions",
        ["entity_type"],
    )
    op.create_index(
        "ix_topology_exclusions_entity_id",
        "topology_exclusions",
        ["entity_id"],
    )

    # Create unique constraint
    op.create_unique_constraint(
        "uq_topology_exclusions_user_entity",
        "topology_exclusions",
        ["user_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    """Remove topology_exclusions table."""
    # Drop constraint and indexes
    op.drop_constraint(
        "uq_topology_exclusions_user_entity",
        "topology_exclusions",
        type_="unique",
    )
    op.drop_index("ix_topology_exclusions_entity_id", table_name="topology_exclusions")
    op.drop_index("ix_topology_exclusions_entity_type", table_name="topology_exclusions")
    op.drop_index("ix_topology_exclusions_user_id", table_name="topology_exclusions")

    # Drop table
    op.drop_table("topology_exclusions")
