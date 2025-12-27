"""Add gateway detection tables and fields

Adds:
- gateway_observations table for intermediate gateway observations
- asset_gateways table for inferred gateway relationships
- Gateway fields to flow_aggregates table

Revision ID: 011
Revises: 010
Create Date: 2024-12-26 00:00:11.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add gateway fields to flow_aggregates table
    op.add_column(
        "flow_aggregates",
        sa.Column("primary_gateway_ip", postgresql.INET(), nullable=True),
    )
    op.add_column(
        "flow_aggregates",
        sa.Column("exporter_ip", postgresql.INET(), nullable=True),
    )

    # Create index on gateway IP for efficient lookups
    op.create_index(
        "ix_flow_aggregates_gateway",
        "flow_aggregates",
        ["primary_gateway_ip"],
        postgresql_where=sa.text("primary_gateway_ip IS NOT NULL"),
    )

    # Create gateway_observations table for intermediate observations
    op.create_table(
        "gateway_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_ip", postgresql.INET(), nullable=False),
        sa.Column("gateway_ip", postgresql.INET(), nullable=False),
        sa.Column("destination_ip", postgresql.INET(), nullable=True),
        sa.Column("observation_source", sa.String(20), nullable=False),  # next_hop, exporter
        sa.Column("exporter_ip", postgresql.INET(), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for gateway_observations
    op.create_index(
        "ix_gateway_obs_unprocessed",
        "gateway_observations",
        ["window_start"],
        postgresql_where=sa.text("is_processed = false"),
    )
    op.create_index(
        "ix_gateway_obs_source_window",
        "gateway_observations",
        ["source_ip", "window_start"],
    )
    op.create_index(
        "ix_gateway_obs_gateway",
        "gateway_observations",
        ["gateway_ip"],
    )

    # Create asset_gateways table for inferred gateway relationships
    op.create_table(
        "asset_gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Relationship endpoints
        sa.Column(
            "source_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gateway_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Destination context
        sa.Column("destination_network", postgresql.CIDR(), nullable=True),
        # Gateway classification
        sa.Column(
            "gateway_role",
            sa.String(20),
            nullable=False,
            server_default="primary",
        ),
        sa.Column("is_default_gateway", sa.Boolean(), nullable=False, server_default="false"),
        # Traffic metrics
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_last_24h", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_last_7d", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_share", sa.Float(), nullable=True),
        # Confidence scoring
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_scores", postgresql.JSONB(), nullable=True),
        # Temporal tracking
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        # Discovery metadata
        sa.Column(
            "inference_method",
            sa.String(50),
            nullable=False,
            server_default="'next_hop'",
        ),
        sa.Column("last_inferred_at", sa.DateTime(timezone=True), nullable=True),
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.CheckConstraint(
            "source_asset_id != gateway_asset_id",
            name="asset_gateways_no_self_gateway",
        ),
        sa.CheckConstraint(
            "gateway_role IN ('primary', 'secondary', 'ecmp')",
            name="asset_gateways_role_check",
        ),
    )

    # Indexes for asset_gateways
    op.create_index(
        "ix_gateways_source_current",
        "asset_gateways",
        ["source_asset_id"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_gateways_gateway_current",
        "asset_gateways",
        ["gateway_asset_id"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_gateways_last_seen",
        "asset_gateways",
        ["last_seen"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    # Unique constraint for current gateway per source/gateway/destination combo
    op.create_index(
        "ix_gateways_source_gateway_dest_current",
        "asset_gateways",
        ["source_asset_id", "gateway_asset_id", "destination_network"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    # Drop asset_gateways table and indexes
    op.drop_index("ix_gateways_source_gateway_dest_current", table_name="asset_gateways")
    op.drop_index("ix_gateways_last_seen", table_name="asset_gateways")
    op.drop_index("ix_gateways_gateway_current", table_name="asset_gateways")
    op.drop_index("ix_gateways_source_current", table_name="asset_gateways")
    op.drop_table("asset_gateways")

    # Drop gateway_observations table and indexes
    op.drop_index("ix_gateway_obs_gateway", table_name="gateway_observations")
    op.drop_index("ix_gateway_obs_source_window", table_name="gateway_observations")
    op.drop_index("ix_gateway_obs_unprocessed", table_name="gateway_observations")
    op.drop_table("gateway_observations")

    # Drop flow_aggregates gateway columns
    op.drop_index("ix_flow_aggregates_gateway", table_name="flow_aggregates")
    op.drop_column("flow_aggregates", "exporter_ip")
    op.drop_column("flow_aggregates", "primary_gateway_ip")
