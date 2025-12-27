"""Add indexes and optimizations for topology queries.

Revision ID: 013
Revises: 012
Create Date: 2025-12-27 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Composite indexes for topology graph queries
    # ==========================================================================

    # Composite index for asset filtering in topology queries
    # Covers: asset_type, is_internal, deleted_at filters
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_assets_topology_filter
        ON assets (asset_type, is_internal)
        WHERE deleted_at IS NULL
    """)

    # Index for asset IP address lookups (CIDR classification)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_assets_ip_active
        ON assets (ip_address)
        WHERE deleted_at IS NULL
    """)

    # ==========================================================================
    # Dependency query optimization indexes
    # ==========================================================================

    # Composite index for dependency queries with bytes filter
    # Covers: source_asset_id, target_asset_id, bytes_last_24h for current deps
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deps_source_target_bytes_current
        ON dependencies (source_asset_id, target_asset_id, bytes_last_24h)
        WHERE valid_to IS NULL
    """)

    # Index for temporal dependency queries (point-in-time)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deps_temporal
        ON dependencies (valid_from, valid_to)
        INCLUDE (source_asset_id, target_asset_id)
    """)

    # ==========================================================================
    # Classification rules optimization
    # ==========================================================================

    # GiST index for CIDR containment queries (ip <<= cidr)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_classification_rules_cidr_gist
        ON classification_rules USING gist (cidr inet_ops)
        WHERE is_active = true
    """)

    # Composite index for rule priority ordering
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_classification_rules_active_priority
        ON classification_rules (priority ASC)
        WHERE is_active = true
    """)

    # ==========================================================================
    # Gateway query optimization
    # ==========================================================================

    # Composite index for gateway lookups by source
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_asset_gateways_source_current
        ON asset_gateways (source_asset_id, confidence DESC)
        WHERE valid_to IS NULL
    """)

    # Index for gateway clients lookup
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_asset_gateways_gateway_current
        ON asset_gateways (gateway_asset_id)
        WHERE valid_to IS NULL
    """)

    # ==========================================================================
    # Optimized graph traversal functions
    # ==========================================================================

    # Replace get_downstream_dependencies with optimized version
    # that uses materialized path and limits results
    op.execute("""
        CREATE OR REPLACE FUNCTION get_downstream_dependencies(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5,
            p_max_results INTEGER DEFAULT 1000
        )
        RETURNS TABLE (
            asset_id UUID,
            asset_name VARCHAR(255),
            depth INTEGER,
            path UUID[],
            target_port INTEGER,
            protocol INTEGER,
            bytes_total BIGINT,
            last_seen TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH RECURSIVE downstream AS (
                -- Base case: direct dependencies
                SELECT
                    d.target_asset_id AS asset_id,
                    a.name AS asset_name,
                    1 AS depth,
                    ARRAY[d.source_asset_id, d.target_asset_id] AS path,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM dependencies d
                JOIN assets a ON a.id = d.target_asset_id
                WHERE d.source_asset_id = p_asset_id
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL

                UNION ALL

                -- Recursive case
                SELECT
                    d.target_asset_id,
                    a.name,
                    ds.depth + 1,
                    ds.path || d.target_asset_id,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM downstream ds
                JOIN dependencies d ON d.source_asset_id = ds.asset_id
                JOIN assets a ON a.id = d.target_asset_id
                WHERE ds.depth < p_max_depth
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL
                  AND NOT d.target_asset_id = ANY(ds.path)  -- Prevent cycles
            )
            SELECT DISTINCT ON (downstream.asset_id)
                downstream.asset_id,
                downstream.asset_name,
                downstream.depth,
                downstream.path,
                downstream.target_port,
                downstream.protocol,
                downstream.bytes_total,
                downstream.last_seen
            FROM downstream
            ORDER BY downstream.asset_id, downstream.depth
            LIMIT p_max_results;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Replace get_upstream_dependencies with optimized version
    op.execute("""
        CREATE OR REPLACE FUNCTION get_upstream_dependencies(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5,
            p_max_results INTEGER DEFAULT 1000
        )
        RETURNS TABLE (
            asset_id UUID,
            asset_name VARCHAR(255),
            depth INTEGER,
            path UUID[],
            target_port INTEGER,
            protocol INTEGER,
            bytes_total BIGINT,
            last_seen TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH RECURSIVE upstream AS (
                -- Base case: assets that depend on this one
                SELECT
                    d.source_asset_id AS asset_id,
                    a.name AS asset_name,
                    1 AS depth,
                    ARRAY[d.target_asset_id, d.source_asset_id] AS path,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM dependencies d
                JOIN assets a ON a.id = d.source_asset_id
                WHERE d.target_asset_id = p_asset_id
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL

                UNION ALL

                -- Recursive case
                SELECT
                    d.source_asset_id,
                    a.name,
                    us.depth + 1,
                    us.path || d.source_asset_id,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM upstream us
                JOIN dependencies d ON d.target_asset_id = us.asset_id
                JOIN assets a ON a.id = d.source_asset_id
                WHERE us.depth < p_max_depth
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL
                  AND NOT d.source_asset_id = ANY(us.path)
            )
            SELECT DISTINCT ON (upstream.asset_id)
                upstream.asset_id,
                upstream.asset_name,
                upstream.depth,
                upstream.path,
                upstream.target_port,
                upstream.protocol,
                upstream.bytes_total,
                upstream.last_seen
            FROM upstream
            ORDER BY upstream.asset_id, upstream.depth
            LIMIT p_max_results;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # ==========================================================================
    # Statistics for query planner
    # ==========================================================================

    # Ensure statistics are up to date for query optimization
    op.execute("ANALYZE assets")
    op.execute("ANALYZE dependencies")
    op.execute("ANALYZE classification_rules")
    op.execute("ANALYZE asset_gateways")


def downgrade() -> None:
    # Drop new indexes
    op.execute("DROP INDEX IF EXISTS ix_assets_topology_filter")
    op.execute("DROP INDEX IF EXISTS ix_assets_ip_active")
    op.execute("DROP INDEX IF EXISTS ix_deps_source_target_bytes_current")
    op.execute("DROP INDEX IF EXISTS ix_deps_temporal")
    op.execute("DROP INDEX IF EXISTS ix_classification_rules_cidr_gist")
    op.execute("DROP INDEX IF EXISTS ix_classification_rules_active_priority")
    op.execute("DROP INDEX IF EXISTS ix_asset_gateways_source_current")
    op.execute("DROP INDEX IF EXISTS ix_asset_gateways_gateway_current")

    # Restore original functions (without max_results parameter)
    op.execute("""
        CREATE OR REPLACE FUNCTION get_downstream_dependencies(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5
        )
        RETURNS TABLE (
            asset_id UUID,
            asset_name VARCHAR(255),
            depth INTEGER,
            path UUID[],
            target_port INTEGER,
            protocol INTEGER,
            bytes_total BIGINT,
            last_seen TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH RECURSIVE downstream AS (
                SELECT
                    d.target_asset_id AS asset_id,
                    a.name AS asset_name,
                    1 AS depth,
                    ARRAY[d.source_asset_id, d.target_asset_id] AS path,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM dependencies d
                JOIN assets a ON a.id = d.target_asset_id
                WHERE d.source_asset_id = p_asset_id
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL

                UNION ALL

                SELECT
                    d.target_asset_id,
                    a.name,
                    ds.depth + 1,
                    ds.path || d.target_asset_id,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM downstream ds
                JOIN dependencies d ON d.source_asset_id = ds.asset_id
                JOIN assets a ON a.id = d.target_asset_id
                WHERE ds.depth < p_max_depth
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL
                  AND NOT d.target_asset_id = ANY(ds.path)
            )
            SELECT DISTINCT ON (downstream.asset_id)
                downstream.asset_id,
                downstream.asset_name,
                downstream.depth,
                downstream.path,
                downstream.target_port,
                downstream.protocol,
                downstream.bytes_total,
                downstream.last_seen
            FROM downstream
            ORDER BY downstream.asset_id, downstream.depth;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION get_upstream_dependencies(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5
        )
        RETURNS TABLE (
            asset_id UUID,
            asset_name VARCHAR(255),
            depth INTEGER,
            path UUID[],
            target_port INTEGER,
            protocol INTEGER,
            bytes_total BIGINT,
            last_seen TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH RECURSIVE upstream AS (
                SELECT
                    d.source_asset_id AS asset_id,
                    a.name AS asset_name,
                    1 AS depth,
                    ARRAY[d.target_asset_id, d.source_asset_id] AS path,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM dependencies d
                JOIN assets a ON a.id = d.source_asset_id
                WHERE d.target_asset_id = p_asset_id
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL

                UNION ALL

                SELECT
                    d.source_asset_id,
                    a.name,
                    us.depth + 1,
                    us.path || d.source_asset_id,
                    d.target_port,
                    d.protocol,
                    d.bytes_total,
                    d.last_seen
                FROM upstream us
                JOIN dependencies d ON d.target_asset_id = us.asset_id
                JOIN assets a ON a.id = d.source_asset_id
                WHERE us.depth < p_max_depth
                  AND d.valid_to IS NULL
                  AND a.deleted_at IS NULL
                  AND NOT d.source_asset_id = ANY(us.path)
            )
            SELECT DISTINCT ON (upstream.asset_id)
                upstream.asset_id,
                upstream.asset_name,
                upstream.depth,
                upstream.path,
                upstream.target_port,
                upstream.protocol,
                upstream.bytes_total,
                upstream.last_seen
            FROM upstream
            ORDER BY upstream.asset_id, upstream.depth;
        END;
        $$ LANGUAGE plpgsql;
    """)
