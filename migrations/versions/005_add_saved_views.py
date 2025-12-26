"""Add saved_views table for topology view persistence

Revision ID: 005
Revises: 004
Create Date: 2024-12-25 00:00:05.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create saved_views table
    op.create_table(
        "saved_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, default=False),
        sa.Column("config", postgresql.JSON(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes
    op.create_index(
        "ix_saved_views_created_by",
        "saved_views",
        ["created_by"],
    )
    op.create_index(
        "ix_saved_views_public",
        "saved_views",
        ["is_public"],
        postgresql_where=sa.text("is_public = true"),
    )
    op.create_index(
        "ix_saved_views_default",
        "saved_views",
        ["created_by", "is_default"],
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_saved_views_default", table_name="saved_views")
    op.drop_index("ix_saved_views_public", table_name="saved_views")
    op.drop_index("ix_saved_views_created_by", table_name="saved_views")
    op.drop_table("saved_views")
