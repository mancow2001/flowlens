"""Fix ambiguous function error and handle empty results.

Issues fixed:
1. get_upstream_dependencies and get_downstream_dependencies had both
   2-param and 3-param versions causing AmbiguousFunctionError
2. calculate_blast_radius was returning NULL instead of 0 for empty results

Revision ID: 015
Revises: 014
Create Date: 2025-12-27 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Fix ambiguous function signatures
    # ==========================================================================
    # Drop ALL versions of the functions to ensure clean state
    # The issue: both 2-param and 3-param versions exist, causing ambiguity

    # Drop all versions of get_downstream_dependencies
    op.execute("DROP FUNCTION IF EXISTS get_downstream_dependencies(UUID, INTEGER, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_downstream_dependencies(UUID, INTEGER)")

    # Drop all versions of get_upstream_dependencies
    op.execute("DROP FUNCTION IF EXISTS get_upstream_dependencies(UUID, INTEGER, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_upstream_dependencies(UUID, INTEGER)")

    # Drop calculate_blast_radius (depends on get_upstream_dependencies)
    op.execute("DROP FUNCTION IF EXISTS calculate_blast_radius(UUID, INTEGER)")

    # ==========================================================================
    # Recreate functions with single signatures (2-param with defaults)
    # ==========================================================================

    # Recreate get_downstream_dependencies
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
            LIMIT 1000;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Recreate get_upstream_dependencies
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
            LIMIT 1000;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # ==========================================================================
    # Fix calculate_blast_radius to handle empty results
    # ==========================================================================
    # The issue: when there are no upstream dependencies, SELECT INTO
    # with no matching rows leaves variables as NULL instead of 0
    op.execute("""
        CREATE OR REPLACE FUNCTION calculate_blast_radius(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5
        )
        RETURNS TABLE (
            total_affected INTEGER,
            critical_affected INTEGER,
            affected_assets JSONB
        ) AS $$
        DECLARE
            v_result JSONB;
            v_total INTEGER := 0;
            v_critical INTEGER := 0;
        BEGIN
            WITH upstream AS (
                SELECT * FROM get_upstream_dependencies(p_asset_id, p_max_depth)
            )
            SELECT
                COALESCE(COUNT(*)::INTEGER, 0),
                COALESCE(COUNT(*) FILTER (WHERE a.is_critical)::INTEGER, 0),
                COALESCE(jsonb_agg(jsonb_build_object(
                    'id', u.asset_id,
                    'name', u.asset_name,
                    'depth', u.depth,
                    'is_critical', a.is_critical
                )) FILTER (WHERE u.asset_id IS NOT NULL), '[]'::jsonb)
            INTO v_total, v_critical, v_result
            FROM upstream u
            LEFT JOIN assets a ON a.id = u.asset_id;

            -- Ensure non-null values
            v_total := COALESCE(v_total, 0);
            v_critical := COALESCE(v_critical, 0);
            v_result := COALESCE(v_result, '[]'::jsonb);

            RETURN QUERY SELECT v_total, v_critical, v_result;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)


def downgrade() -> None:
    # Drop the fixed functions
    op.execute("DROP FUNCTION IF EXISTS calculate_blast_radius(UUID, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_upstream_dependencies(UUID, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_downstream_dependencies(UUID, INTEGER)")

    # Restore 3-param versions from migration 013
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
            ORDER BY downstream.asset_id, downstream.depth
            LIMIT p_max_results;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

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
            ORDER BY upstream.asset_id, upstream.depth
            LIMIT p_max_results;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION calculate_blast_radius(
            p_asset_id UUID,
            p_max_depth INTEGER DEFAULT 5
        )
        RETURNS TABLE (
            total_affected INTEGER,
            critical_affected INTEGER,
            affected_assets JSONB
        ) AS $$
        DECLARE
            v_result JSONB;
            v_total INTEGER;
            v_critical INTEGER;
        BEGIN
            WITH upstream AS (
                SELECT * FROM get_upstream_dependencies(p_asset_id, p_max_depth)
            )
            SELECT
                COUNT(*)::INTEGER,
                COUNT(*) FILTER (WHERE a.is_critical)::INTEGER,
                jsonb_agg(jsonb_build_object(
                    'id', u.asset_id,
                    'name', u.asset_name,
                    'depth', u.depth,
                    'is_critical', a.is_critical
                ))
            INTO v_total, v_critical, v_result
            FROM upstream u
            JOIN assets a ON a.id = u.asset_id;

            RETURN QUERY SELECT v_total, v_critical, COALESCE(v_result, '[]'::jsonb);
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)
