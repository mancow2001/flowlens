"""Add baseline change tracking columns to change_events.

Revision ID: 030
Revises: 029
Create Date: 2025-01-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add application_id column
    op.add_column(
        "change_events",
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Add baseline_id column
    op.add_column(
        "change_events",
        sa.Column(
            "baseline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application_baselines.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Create indexes
    op.create_index(
        "ix_change_events_application_id",
        "change_events",
        ["application_id"],
    )
    op.create_index(
        "ix_change_events_baseline_id",
        "change_events",
        ["baseline_id"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_change_events_baseline_id", table_name="change_events")
    op.drop_index("ix_change_events_application_id", table_name="change_events")

    # Drop columns
    op.drop_column("change_events", "baseline_id")
    op.drop_column("change_events", "application_id")
