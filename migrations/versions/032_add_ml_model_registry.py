"""Add ML model registry table.

Revision ID: 032
Revises: 031
Create Date: 2025-01-10

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ml_model_registry table
    op.create_table(
        "ml_model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(50), unique=True, nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, default=False, nullable=False),
        sa.Column(
            "model_type",
            sa.String(20),
            nullable=False,
            server_default="custom",
        ),  # 'shipped' or 'custom'

        # Training metadata
        sa.Column("training_samples", sa.Integer, nullable=False),
        sa.Column("accuracy", sa.Float, nullable=False),
        sa.Column("f1_score", sa.Float, nullable=True),
        sa.Column("class_distribution", postgresql.JSONB, nullable=True),
        sa.Column("feature_importances", postgresql.JSONB, nullable=True),
        sa.Column("confusion_matrix", postgresql.JSONB, nullable=True),
        sa.Column("training_params", postgresql.JSONB, nullable=True),

        # Storage info
        sa.Column("model_path", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),  # SHA256

        # Notes
        sa.Column("notes", sa.Text, nullable=True),
    )

    # Create index for finding active model
    op.create_index(
        "ix_ml_model_registry_active",
        "ml_model_registry",
        ["is_active"],
        postgresql_where="is_active = true",
    )

    # Create index for model type lookup
    op.create_index(
        "ix_ml_model_registry_type",
        "ml_model_registry",
        ["model_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_model_registry_type", table_name="ml_model_registry")
    op.drop_index("ix_ml_model_registry_active", table_name="ml_model_registry")
    op.drop_table("ml_model_registry")
