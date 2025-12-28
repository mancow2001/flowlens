"""Fix calculate_blast_radius function to handle empty results.

When there are no upstream dependencies, the function was returning NULL
values instead of 0 for total_affected and critical_affected.

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
    # Fix calculate_blast_radius to handle empty results
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
    # Restore previous version (from migration 013)
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
