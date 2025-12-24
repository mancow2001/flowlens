"""Add is_processed column to flow_aggregates table

Revision ID: 004
Revises: 003
Create Date: 2024-01-01 00:00:04.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_processed column to flow_aggregates
    op.add_column(
        "flow_aggregates",
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Create index for unprocessed aggregates
    op.create_index(
        "ix_agg_unprocessed",
        "flow_aggregates",
        ["window_start"],
        postgresql_where=sa.text("is_processed = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_agg_unprocessed", table_name="flow_aggregates")
    op.drop_column("flow_aggregates", "is_processed")
