"""Add application baselines table.

Revision ID: 029
Revises: 028
Create Date: 2025-01-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create application_baselines table
    op.create_table(
        "application_baselines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("dependency_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("member_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("entry_point_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_traffic_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
        "ix_baselines_application_id",
        "application_baselines",
        ["application_id"],
    )
    op.create_index(
        "ix_baselines_app_active",
        "application_baselines",
        ["application_id", "is_active"],
    )
    op.create_index(
        "ix_baselines_captured_at",
        "application_baselines",
        ["captured_at"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_baselines_captured_at", table_name="application_baselines")
    op.drop_index("ix_baselines_app_active", table_name="application_baselines")
    op.drop_index("ix_baselines_application_id", table_name="application_baselines")

    # Drop table
    op.drop_table("application_baselines")
