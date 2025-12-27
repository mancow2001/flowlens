"""Flow tables - flow_records (partitioned), flow_aggregates, dependency_stats

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Flow records table (partitioned by timestamp)
    # Note: We create this as a partitioned table
    op.execute("""
        CREATE TABLE flow_records (
            id UUID NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            src_ip INET NOT NULL,
            src_port INTEGER NOT NULL,
            dst_ip INET NOT NULL,
            dst_port INTEGER NOT NULL,
            protocol SMALLINT NOT NULL,
            bytes_count BIGINT NOT NULL,
            packets_count BIGINT NOT NULL,
            tcp_flags SMALLINT,
            flow_start TIMESTAMPTZ,
            flow_end TIMESTAMPTZ,
            flow_duration_ms INTEGER,
            exporter_ip INET NOT NULL,
            exporter_id INTEGER,
            sampling_rate INTEGER NOT NULL DEFAULT 1,
            flow_source VARCHAR(20) NOT NULL,
            input_interface INTEGER,
            output_interface INTEGER,
            tos SMALLINT,
            extended_fields JSONB,
            is_enriched BOOLEAN NOT NULL DEFAULT false,
            is_processed BOOLEAN NOT NULL DEFAULT false,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, timestamp),
            CONSTRAINT flow_records_src_port_check CHECK (src_port >= 0 AND src_port <= 65535),
            CONSTRAINT flow_records_dst_port_check CHECK (dst_port >= 0 AND dst_port <= 65535),
            CONSTRAINT flow_records_protocol_check CHECK (protocol >= 0 AND protocol <= 255)
        ) PARTITION BY RANGE (timestamp)
    """)

    # Create initial partitions (7 days)
    op.execute("""
        CREATE TABLE flow_records_default PARTITION OF flow_records DEFAULT
    """)

    # Flow records indexes
    op.execute("CREATE INDEX ix_flows_timestamp ON flow_records (timestamp)")
    op.execute("CREATE INDEX ix_flows_src_ip ON flow_records (src_ip)")
    op.execute("CREATE INDEX ix_flows_dst_ip ON flow_records (dst_ip)")
    op.execute("CREATE INDEX ix_flows_dst_port ON flow_records (dst_port)")
    op.execute("CREATE INDEX ix_flows_protocol ON flow_records (protocol)")
    op.execute("CREATE INDEX ix_flows_exporter_ip ON flow_records (exporter_ip)")
    op.execute("CREATE INDEX ix_flows_src_dst_time ON flow_records (src_ip, dst_ip, timestamp)")
    op.execute("CREATE INDEX ix_flows_dst_port_time ON flow_records (dst_ip, dst_port, timestamp)")
    op.execute("CREATE INDEX ix_flows_unenriched ON flow_records (timestamp) WHERE is_enriched = false")
    op.execute("CREATE INDEX ix_flows_unprocessed ON flow_records (timestamp) WHERE is_processed = false")

    # Flow aggregates table
    op.create_table(
        "flow_aggregates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size", sa.String(20), nullable=False),
        sa.Column("src_ip", postgresql.INET(), nullable=False),
        sa.Column("dst_ip", postgresql.INET(), nullable=False),
        sa.Column("dst_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.SmallInteger(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("packets_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_min", sa.BigInteger(), nullable=True),
        sa.Column("bytes_max", sa.BigInteger(), nullable=True),
        sa.Column("bytes_avg", sa.Float(), nullable=True),
        sa.Column("unique_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_destinations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("src_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dst_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("dst_port >= 0 AND dst_port <= 65535"),
        sa.CheckConstraint("protocol >= 0 AND protocol <= 255"),
    )

    op.create_index("ix_flow_aggregates_window_start", "flow_aggregates", ["window_start"])
    op.create_index("ix_flow_aggregates_window_size", "flow_aggregates", ["window_size"])
    op.create_index("ix_flow_aggregates_src_ip", "flow_aggregates", ["src_ip"])
    op.create_index("ix_flow_aggregates_dst_ip", "flow_aggregates", ["dst_ip"])
    op.create_index("ix_flow_aggregates_dst_port", "flow_aggregates", ["dst_port"])
    op.create_index("ix_flow_aggregates_src_asset_id", "flow_aggregates", ["src_asset_id"])
    op.create_index("ix_flow_aggregates_dst_asset_id", "flow_aggregates", ["dst_asset_id"])
    op.create_index(
        "ix_agg_key_window",
        "flow_aggregates",
        ["src_ip", "dst_ip", "dst_port", "protocol", "window_start", "window_size"],
        unique=True,
    )
    op.create_index(
        "ix_agg_assets_window",
        "flow_aggregates",
        ["src_asset_id", "dst_asset_id", "window_start"],
    )

    # Dependency stats table
    op.create_table(
        "dependency_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stat_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.SmallInteger(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("packets_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_by_hour", postgresql.JSONB(), nullable=True),
        sa.Column("peak_bytes_per_sec", sa.BigInteger(), nullable=True),
        sa.Column("avg_bytes_per_sec", sa.Float(), nullable=True),
        sa.Column("active_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_dependency_stats_stat_date", "dependency_stats", ["stat_date"])
    op.create_index("ix_dependency_stats_dependency_id", "dependency_stats", ["dependency_id"])
    op.create_index("ix_dependency_stats_source_asset_id", "dependency_stats", ["source_asset_id"])
    op.create_index("ix_dependency_stats_target_asset_id", "dependency_stats", ["target_asset_id"])
    op.create_index("ix_stats_dep_date", "dependency_stats", ["dependency_id", "stat_date"], unique=True)
    op.create_index("ix_stats_date_source", "dependency_stats", ["stat_date", "source_asset_id"])
    op.create_index("ix_stats_date_target", "dependency_stats", ["stat_date", "target_asset_id"])

    # Create function for automatic partition creation
    op.execute("""
        CREATE OR REPLACE FUNCTION create_flow_partition(partition_date DATE)
        RETURNS void AS $$
        DECLARE
            partition_name TEXT;
            start_date DATE;
            end_date DATE;
        BEGIN
            partition_name := 'flow_records_' || to_char(partition_date, 'YYYYMMDD');
            start_date := partition_date;
            end_date := partition_date + INTERVAL '1 day';

            -- Check if partition already exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE tablename = partition_name
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF flow_records
                     FOR VALUES FROM (%L) TO (%L)',
                    partition_name, start_date, end_date
                );
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function for partition cleanup
    op.execute("""
        CREATE OR REPLACE FUNCTION drop_old_flow_partitions(retention_days INTEGER DEFAULT 7)
        RETURNS void AS $$
        DECLARE
            partition_record RECORD;
            cutoff_date DATE;
        BEGIN
            cutoff_date := CURRENT_DATE - retention_days;

            FOR partition_record IN
                SELECT tablename
                FROM pg_tables
                WHERE tablename LIKE 'flow_records_%'
                  AND tablename != 'flow_records_default'
                  AND to_date(substring(tablename from 14), 'YYYYMMDD') < cutoff_date
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || partition_record.tablename;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS drop_old_flow_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_flow_partition(DATE)")
    op.drop_table("dependency_stats")
    op.drop_table("flow_aggregates")
    op.execute("DROP TABLE IF EXISTS flow_records CASCADE")
