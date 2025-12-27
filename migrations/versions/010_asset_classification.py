"""Add asset classification engine tables and fields

Adds:
- Classification fields to assets table (classification_locked, confidence, scores, etc.)
- asset_features table for storing computed behavioral features
- classification_history table for audit trail

Revision ID: 010
Revises: 009
Create Date: 2024-12-26 00:00:10.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add classification fields to assets table
    op.add_column(
        "assets",
        sa.Column(
            "classification_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "assets",
        sa.Column("classification_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("classification_scores", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column(
            "last_classified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "classification_method",
            sa.String(50),
            nullable=True,
        ),
    )

    # Create partial index for finding assets needing classification
    op.create_index(
        "ix_assets_classification_needed",
        "assets",
        ["last_classified_at", "classification_locked"],
        postgresql_where=sa.text("classification_locked = false AND deleted_at IS NULL"),
    )

    # Create asset_features table for storing computed behavioral features
    op.create_table(
        "asset_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=False, index=True),
        sa.Column("window_size", sa.String(20), nullable=False, index=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        # Traffic directionality
        sa.Column("inbound_flows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("outbound_flows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("inbound_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("outbound_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fan_in_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fan_out_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fan_in_ratio", sa.Float(), nullable=True),
        # Port & protocol behavior
        sa.Column("unique_dst_ports", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_src_ports", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("well_known_port_ratio", sa.Float(), nullable=True),
        sa.Column("ephemeral_port_ratio", sa.Float(), nullable=True),
        sa.Column("persistent_listener_ports", postgresql.JSONB(), nullable=True),
        sa.Column("protocol_distribution", postgresql.JSONB(), nullable=True),
        # Flow characteristics
        sa.Column("avg_flow_duration_ms", sa.Float(), nullable=True),
        sa.Column("avg_packets_per_flow", sa.Float(), nullable=True),
        sa.Column("avg_bytes_per_packet", sa.Float(), nullable=True),
        sa.Column("connection_churn_rate", sa.Float(), nullable=True),
        # Temporal patterns
        sa.Column("active_hours_count", sa.Integer(), nullable=True),
        sa.Column("business_hours_ratio", sa.Float(), nullable=True),
        sa.Column("traffic_variance", sa.Float(), nullable=True),
        # Port-specific flags
        sa.Column("has_db_ports", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_storage_ports", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_web_ports", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_ssh_ports", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Composite index for efficient feature lookup
    op.create_index(
        "ix_asset_features_asset_window",
        "asset_features",
        ["asset_id", "window_size", "computed_at"],
    )

    # Create classification_history table for audit trail
    op.create_table(
        "classification_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("previous_type", sa.String(50), nullable=True),
        sa.Column("new_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("scores", postgresql.JSONB(), nullable=False),
        sa.Column("features_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=False),  # 'auto', 'manual', 'api'
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("classification_history")
    op.drop_table("asset_features")

    # Drop index
    op.drop_index("ix_assets_classification_needed", table_name="assets")

    # Remove columns from assets
    op.drop_column("assets", "classification_method")
    op.drop_column("assets", "last_classified_at")
    op.drop_column("assets", "classification_scores")
    op.drop_column("assets", "classification_confidence")
    op.drop_column("assets", "classification_locked")
