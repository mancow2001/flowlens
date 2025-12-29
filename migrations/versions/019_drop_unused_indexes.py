"""Drop unused indexes to improve write performance and reduce storage.

Based on pg_stat_user_indexes analysis showing these indexes have 0 scans.
Saves approximately 100 MB of storage and improves write performance.

Revision ID: 019
Revises: 018
Create Date: 2025-12-29 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # flow_records_default: Drop 6 unused indexes (~91 MB savings)
    # These indexes were designed for ad-hoc queries that don't occur.
    # The application uses PK lookups and partial timestamp indexes instead.
    # ==========================================================================

    # Composite index for src+dst+time queries - never used (25 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_src_ip_dst_ip_timestamp_idx")

    # Composite index for dst+port+time queries - never used (23 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_dst_ip_dst_port_timestamp_idx")

    # Single-column dst_ip index - never used (12 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_dst_ip_idx")

    # Single-column dst_port index - never used (11 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_dst_port_idx")

    # Single-column protocol index - never used, low selectivity (10 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_protocol_idx")

    # Single-column exporter_ip index - never used (9.7 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_exporter_ip_idx")

    # Single-column src_ip index - 1 scan total, redundant with composite (11 MB)
    op.execute("DROP INDEX IF EXISTS flow_records_default_src_ip_idx")

    # ==========================================================================
    # flow_aggregates: Drop unused indexes (~9.5 MB savings)
    # Queries use ix_agg_key_window and ix_agg_unprocessed instead.
    # ==========================================================================

    # Asset-based window index - never used (5.4 MB)
    op.execute("DROP INDEX IF EXISTS ix_agg_assets_window")

    # Single-column src_ip index - never used (1.5 MB)
    op.execute("DROP INDEX IF EXISTS ix_flow_aggregates_src_ip")

    # Single-column dst_ip index - never used (1.4 MB)
    op.execute("DROP INDEX IF EXISTS ix_flow_aggregates_dst_ip")

    # Single-column src_asset_id index - never used (1.4 MB)
    op.execute("DROP INDEX IF EXISTS ix_flow_aggregates_src_asset_id")

    # Single-column dst_asset_id index - never used (1.4 MB)
    op.execute("DROP INDEX IF EXISTS ix_flow_aggregates_dst_asset_id")

    # Gateway IP index - never used (296 KB)
    op.execute("DROP INDEX IF EXISTS ix_flow_aggregates_gateway")

    # ==========================================================================
    # dependencies: Drop redundant/unused indexes (~5 MB savings)
    # ix_deps_source_target_bytes_current (35K scans) covers these use cases.
    # ==========================================================================

    # Redundant with ix_deps_source_target_bytes_current (2.5 MB)
    op.execute("DROP INDEX IF EXISTS ix_deps_source_target_port_proto_current")

    # Temporal index - never used, queries use current deps only (2.3 MB)
    op.execute("DROP INDEX IF EXISTS ix_deps_temporal")

    # valid_from index - never used (248 KB)
    op.execute("DROP INDEX IF EXISTS ix_deps_valid_from")

    # valid_to index - never used (248 KB)
    op.execute("DROP INDEX IF EXISTS ix_deps_valid_to")

    # ==========================================================================
    # Update statistics after index changes
    # ==========================================================================
    op.execute("ANALYZE flow_records")
    op.execute("ANALYZE flow_aggregates")
    op.execute("ANALYZE dependencies")


def downgrade() -> None:
    # ==========================================================================
    # Recreate flow_records_default indexes
    # ==========================================================================

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_src_ip_dst_ip_timestamp_idx
        ON flow_records_default (src_ip, dst_ip, timestamp)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_dst_ip_dst_port_timestamp_idx
        ON flow_records_default (dst_ip, dst_port, timestamp)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_dst_ip_idx
        ON flow_records_default (dst_ip)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_dst_port_idx
        ON flow_records_default (dst_port)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_protocol_idx
        ON flow_records_default (protocol)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_exporter_ip_idx
        ON flow_records_default (exporter_ip)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS flow_records_default_src_ip_idx
        ON flow_records_default (src_ip)
    """)

    # ==========================================================================
    # Recreate flow_aggregates indexes
    # ==========================================================================

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agg_assets_window
        ON flow_aggregates (src_asset_id, dst_asset_id, window_start)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_flow_aggregates_src_ip
        ON flow_aggregates (src_ip)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_flow_aggregates_dst_ip
        ON flow_aggregates (dst_ip)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_flow_aggregates_src_asset_id
        ON flow_aggregates (src_asset_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_flow_aggregates_dst_asset_id
        ON flow_aggregates (dst_asset_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_flow_aggregates_gateway
        ON flow_aggregates (primary_gateway_ip)
    """)

    # ==========================================================================
    # Recreate dependencies indexes
    # ==========================================================================

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_deps_source_target_port_proto_current
        ON dependencies (source_asset_id, target_asset_id, target_port, protocol)
        WHERE valid_to IS NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deps_temporal
        ON dependencies (valid_from, valid_to)
        INCLUDE (source_asset_id, target_asset_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deps_valid_from
        ON dependencies (valid_from)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deps_valid_to
        ON dependencies (valid_to)
    """)

    # Update statistics
    op.execute("ANALYZE flow_records")
    op.execute("ANALYZE flow_aggregates")
    op.execute("ANALYZE dependencies")
