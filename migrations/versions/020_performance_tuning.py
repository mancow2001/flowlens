"""Performance tuning: fillfactor, autovacuum, and table-specific settings.

Addresses:
1. 0% HOT updates on high-write tables (reduce fillfactor)
2. Aggressive autovacuum for high-churn tables
3. Statistics targets for better query planning

Note: PostgreSQL server-level settings (shared_buffers, work_mem, etc.)
must be configured in postgresql.conf or via ALTER SYSTEM by a superuser.
See docstring below for recommended settings.

Revision ID: 020
Revises: 019
Create Date: 2025-12-29 21:30:00.000000

RECOMMENDED POSTGRESQL.CONF SETTINGS (requires superuser):
---------------------------------------------------------
# Memory (adjust based on available RAM, assuming 8GB server)
shared_buffers = '2GB'              # 25% of RAM
effective_cache_size = '6GB'        # 75% of RAM
work_mem = '64MB'                   # Per-operation memory
maintenance_work_mem = '512MB'      # For VACUUM, CREATE INDEX

# SSD-optimized settings
random_page_cost = 1.1              # SSD has near-sequential access
effective_io_concurrency = 200      # SSD can handle parallel I/O
seq_page_cost = 1.0

# WAL settings
wal_buffers = '64MB'
max_wal_size = '4GB'
min_wal_size = '1GB'
checkpoint_completion_target = 0.9

# Parallelism
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_parallel_maintenance_workers = 4

Apply with:
  ALTER SYSTEM SET shared_buffers = '2GB';
  -- ... (requires restart for shared_buffers)
  SELECT pg_reload_conf();  -- for runtime settings
---------------------------------------------------------
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # 1. FILLFACTOR: Enable HOT updates on high-write tables
    #
    # HOT (Heap-Only Tuple) updates avoid index updates when:
    # - Updated columns are not indexed
    # - There's free space on the same page
    #
    # Current: 0% HOT on flow_records (1.2M updates), gateway_observations (74K)
    # Target: 50-70% HOT updates
    # ==========================================================================

    # flow_records_default: Heavy updates to is_processed, is_enriched (not indexed)
    # Reduce fillfactor from 100 to 70 (30% free space for HOT)
    op.execute("""
        ALTER TABLE flow_records_default SET (
            fillfactor = 70,
            autovacuum_vacuum_scale_factor = 0.05,
            autovacuum_analyze_scale_factor = 0.02,
            autovacuum_vacuum_cost_delay = 0
        )
    """)

    # gateway_observations: Heavy updates to is_processed
    op.execute("""
        ALTER TABLE gateway_observations SET (
            fillfactor = 70,
            autovacuum_vacuum_scale_factor = 0.05,
            autovacuum_analyze_scale_factor = 0.02,
            autovacuum_vacuum_cost_delay = 0
        )
    """)

    # flow_aggregates: Moderate updates, ~36% HOT currently
    # Reduce fillfactor to improve HOT further
    op.execute("""
        ALTER TABLE flow_aggregates SET (
            fillfactor = 80,
            autovacuum_vacuum_scale_factor = 0.05,
            autovacuum_analyze_scale_factor = 0.02
        )
    """)

    # dependencies: Lower update rate but want to maximize HOT
    op.execute("""
        ALTER TABLE dependencies SET (
            fillfactor = 85,
            autovacuum_vacuum_scale_factor = 0.1
        )
    """)

    # assets: Moderate updates, want good HOT rate
    op.execute("""
        ALTER TABLE assets SET (
            fillfactor = 85,
            autovacuum_vacuum_scale_factor = 0.1
        )
    """)

    # ==========================================================================
    # 2. AUTOVACUUM: Aggressive settings for high-churn tables
    #
    # Default autovacuum triggers at 20% dead tuples - too late for large tables.
    # Set table-specific thresholds for faster cleanup.
    # ==========================================================================

    # dependency_history: Write-only table, append-only pattern
    # Less aggressive vacuum needed, but ensure analyze runs
    op.execute("""
        ALTER TABLE dependency_history SET (
            autovacuum_vacuum_scale_factor = 0.2,
            autovacuum_analyze_scale_factor = 0.05
        )
    """)

    # ==========================================================================
    # 3. STATISTICS TARGETS: Better estimates for skewed columns
    #
    # Increase statistics on columns with high cardinality or skewed distribution
    # for better query plans.
    # ==========================================================================

    # flow_records: src_ip and dst_ip have high cardinality
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN src_ip SET STATISTICS 500")
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN dst_ip SET STATISTICS 500")
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN dst_port SET STATISTICS 200")

    # flow_aggregates: IP columns
    op.execute("ALTER TABLE flow_aggregates ALTER COLUMN src_ip SET STATISTICS 500")
    op.execute("ALTER TABLE flow_aggregates ALTER COLUMN dst_ip SET STATISTICS 500")

    # assets: ip_address is unique, high cardinality
    op.execute("ALTER TABLE assets ALTER COLUMN ip_address SET STATISTICS 500")
    op.execute("ALTER TABLE assets ALTER COLUMN asset_type SET STATISTICS 200")

    # dependencies: asset IDs have moderate cardinality
    op.execute("ALTER TABLE dependencies ALTER COLUMN source_asset_id SET STATISTICS 300")
    op.execute("ALTER TABLE dependencies ALTER COLUMN target_asset_id SET STATISTICS 300")

    # ==========================================================================
    # 4. VACUUM FULL high-bloat tables (run during maintenance window)
    #
    # Note: This is commented out as it locks tables. Run manually:
    # VACUUM FULL flow_records_default;
    # VACUUM FULL gateway_observations;
    # ==========================================================================

    # ==========================================================================
    # 5. Refresh statistics after setting changes
    # ==========================================================================
    op.execute("ANALYZE flow_records_default")
    op.execute("ANALYZE flow_aggregates")
    op.execute("ANALYZE gateway_observations")
    op.execute("ANALYZE dependencies")
    op.execute("ANALYZE assets")
    op.execute("ANALYZE dependency_history")


def downgrade() -> None:
    # Reset to default settings

    # flow_records_default
    op.execute("""
        ALTER TABLE flow_records_default SET (
            fillfactor = 100
        )
    """)
    op.execute("ALTER TABLE flow_records_default RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE flow_records_default RESET (autovacuum_analyze_scale_factor)")
    op.execute("ALTER TABLE flow_records_default RESET (autovacuum_vacuum_cost_delay)")
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN src_ip SET STATISTICS -1")
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN dst_ip SET STATISTICS -1")
    op.execute("ALTER TABLE flow_records_default ALTER COLUMN dst_port SET STATISTICS -1")

    # gateway_observations
    op.execute("""
        ALTER TABLE gateway_observations SET (
            fillfactor = 100
        )
    """)
    op.execute("ALTER TABLE gateway_observations RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE gateway_observations RESET (autovacuum_analyze_scale_factor)")
    op.execute("ALTER TABLE gateway_observations RESET (autovacuum_vacuum_cost_delay)")

    # flow_aggregates
    op.execute("""
        ALTER TABLE flow_aggregates SET (
            fillfactor = 100
        )
    """)
    op.execute("ALTER TABLE flow_aggregates RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE flow_aggregates RESET (autovacuum_analyze_scale_factor)")
    op.execute("ALTER TABLE flow_aggregates ALTER COLUMN src_ip SET STATISTICS -1")
    op.execute("ALTER TABLE flow_aggregates ALTER COLUMN dst_ip SET STATISTICS -1")

    # dependencies
    op.execute("""
        ALTER TABLE dependencies SET (
            fillfactor = 100
        )
    """)
    op.execute("ALTER TABLE dependencies RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE dependencies ALTER COLUMN source_asset_id SET STATISTICS -1")
    op.execute("ALTER TABLE dependencies ALTER COLUMN target_asset_id SET STATISTICS -1")

    # assets
    op.execute("""
        ALTER TABLE assets SET (
            fillfactor = 100
        )
    """)
    op.execute("ALTER TABLE assets RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE assets ALTER COLUMN ip_address SET STATISTICS -1")
    op.execute("ALTER TABLE assets ALTER COLUMN asset_type SET STATISTICS -1")

    # dependency_history
    op.execute("ALTER TABLE dependency_history RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE dependency_history RESET (autovacuum_analyze_scale_factor)")

    # Refresh statistics
    op.execute("ANALYZE flow_records_default")
    op.execute("ANALYZE flow_aggregates")
    op.execute("ANALYZE gateway_observations")
    op.execute("ANALYZE dependencies")
    op.execute("ANALYZE assets")
    op.execute("ANALYZE dependency_history")
