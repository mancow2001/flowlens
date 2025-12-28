"""Add entry point columns to application_members table.

Adds support for designating application entry points:
- is_entry_point: boolean flag to mark an asset as an entry point
- entry_point_order: optional ordering for multiple entry points

Revision ID: 016
Revises: 015
Create Date: 2025-12-28 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_entry_point column with default False
    op.add_column(
        "application_members",
        sa.Column("is_entry_point", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Add entry_point_order column (nullable for ordering multiple entry points)
    op.add_column(
        "application_members",
        sa.Column("entry_point_order", sa.Integer(), nullable=True),
    )

    # Create index for efficient entry point queries
    op.create_index(
        "ix_app_members_entry_points",
        "application_members",
        ["application_id", "is_entry_point"],
    )


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_app_members_entry_points", table_name="application_members")

    # Drop columns
    op.drop_column("application_members", "entry_point_order")
    op.drop_column("application_members", "is_entry_point")
