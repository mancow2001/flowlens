"""Add port and protocol to application entry points.

Extends entry point support with specific port/protocol:
- entry_point_port: port number for the entry point
- entry_point_protocol: IANA protocol number (6=TCP, 17=UDP)

Revision ID: 017
Revises: 016
Create Date: 2025-12-28 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entry_point_port column
    op.add_column(
        "application_members",
        sa.Column("entry_point_port", sa.Integer(), nullable=True),
    )

    # Add entry_point_protocol column (IANA protocol number)
    op.add_column(
        "application_members",
        sa.Column("entry_point_protocol", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_members", "entry_point_protocol")
    op.drop_column("application_members", "entry_point_port")
