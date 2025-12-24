"""Graph tables - dependencies, dependency_history, change_events, alerts

Revision ID: 003
Revises: 002
Create Date: 2024-01-01 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dependencies table (edges in the graph)
    op.create_table(
        "dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Integer(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("packets_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_last_24h", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_last_7d", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("p95_latency_ms", sa.Float(), nullable=True),
        sa.Column("dependency_type", sa.String(50), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("discovered_by", sa.String(50), nullable=False, server_default="flow_analysis"),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("target_port >= 0 AND target_port <= 65535"),
        sa.CheckConstraint("protocol >= 0 AND protocol <= 255"),
        sa.CheckConstraint("source_asset_id != target_asset_id"),
    )

    op.create_index("ix_dependencies_id", "dependencies", ["id"])
    op.create_index("ix_dependencies_source_asset_id", "dependencies", ["source_asset_id"])
    op.create_index("ix_dependencies_target_asset_id", "dependencies", ["target_asset_id"])
    op.create_index("ix_dependencies_last_seen", "dependencies", ["last_seen"])
    op.create_index("ix_deps_valid_from", "dependencies", ["valid_from"])
    op.create_index("ix_deps_valid_to", "dependencies", ["valid_to"])

    # Partial indexes for current dependencies
    op.execute("""
        CREATE UNIQUE INDEX ix_deps_source_target_port_proto_current
        ON dependencies (source_asset_id, target_asset_id, target_port, protocol)
        WHERE valid_to IS NULL
    """)
    op.execute("""
        CREATE INDEX ix_deps_source_current
        ON dependencies (source_asset_id)
        WHERE valid_to IS NULL
    """)
    op.execute("""
        CREATE INDEX ix_deps_target_current
        ON dependencies (target_asset_id)
        WHERE valid_to IS NULL
    """)
    op.execute("""
        CREATE INDEX ix_deps_last_seen_current
        ON dependencies (last_seen)
        WHERE valid_to IS NULL
    """)

    # Dependency history table
    op.create_table(
        "dependency_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Integer(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("flows_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("triggered_by", sa.String(100), nullable=True),
        sa.Column("previous_state", postgresql.JSONB(), nullable=True),
        sa.Column("new_state", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_dependency_history_id", "dependency_history", ["id"])
    op.create_index("ix_dependency_history_dependency_id", "dependency_history", ["dependency_id"])
    op.create_index("ix_dependency_history_change_type", "dependency_history", ["change_type"])
    op.create_index("ix_dependency_history_changed_at", "dependency_history", ["changed_at"])
    op.create_index("ix_dep_history_dep_changed", "dependency_history", ["dependency_id", "changed_at"])
    op.create_index("ix_dep_history_source_changed", "dependency_history", ["source_asset_id", "changed_at"])
    op.create_index("ix_dep_history_target_changed", "dependency_history", ["target_asset_id", "changed_at"])

    # Change events table
    op.create_table(
        "change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("previous_state", postgresql.JSONB(), nullable=True),
        sa.Column("new_state", postgresql.JSONB(), nullable=True),
        sa.Column("impact_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("affected_assets_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("impact_score >= 0 AND impact_score <= 100"),
    )

    op.create_index("ix_change_events_id", "change_events", ["id"])
    op.create_index("ix_change_events_change_type", "change_events", ["change_type"])
    op.create_index("ix_change_events_detected_at", "change_events", ["detected_at"])
    op.create_index("ix_change_events_asset_id", "change_events", ["asset_id"])
    op.create_index("ix_change_events_dependency_id", "change_events", ["dependency_id"])
    op.create_index("ix_change_events_source_asset_id", "change_events", ["source_asset_id"])
    op.create_index("ix_change_events_target_asset_id", "change_events", ["target_asset_id"])
    op.create_index("ix_change_events_is_processed", "change_events", ["is_processed"])
    op.create_index("ix_changes_type_detected", "change_events", ["change_type", "detected_at"])
    op.execute("""
        CREATE INDEX ix_changes_unprocessed
        ON change_events (detected_at)
        WHERE is_processed = false
    """)

    # Alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("change_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notification_channels", postgresql.JSONB(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["change_event_id"], ["change_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_alerts_id", "alerts", ["id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_change_event_id", "alerts", ["change_event_id"])
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])
    op.create_index("ix_alerts_dependency_id", "alerts", ["dependency_id"])
    op.create_index("ix_alerts_is_acknowledged", "alerts", ["is_acknowledged"])
    op.create_index("ix_alerts_is_resolved", "alerts", ["is_resolved"])
    op.create_index("ix_alerts_severity_created", "alerts", ["severity", "created_at"])
    op.execute("""
        CREATE INDEX ix_alerts_unacknowledged
        ON alerts (severity, created_at)
        WHERE is_acknowledged = false
    """)
    op.execute("""
        CREATE INDEX ix_alerts_unresolved
        ON alerts (severity, created_at)
        WHERE is_resolved = false
    """)

    # Create graph traversal functions

    # Get downstream dependencies (what does this asset depend on)
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
            ORDER BY downstream.asset_id, downstream.depth;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Get upstream dependencies (what assets depend on this one)
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
            ORDER BY upstream.asset_id, upstream.depth;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Calculate blast radius (all assets affected if this one fails)
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
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger to track dependency changes
    op.execute("""
        CREATE OR REPLACE FUNCTION track_dependency_changes()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO dependency_history (
                    id, dependency_id, change_type, source_asset_id, target_asset_id,
                    target_port, protocol, bytes_total, flows_total,
                    reason, triggered_by, new_state
                ) VALUES (
                    gen_random_uuid(),
                    NEW.id,
                    'created',
                    NEW.source_asset_id,
                    NEW.target_asset_id,
                    NEW.target_port,
                    NEW.protocol,
                    NEW.bytes_total,
                    NEW.flows_total,
                    'New dependency discovered',
                    'system',
                    row_to_json(NEW)::jsonb
                );
            ELSIF TG_OP = 'UPDATE' THEN
                -- Only log if valid_to changed (dependency became inactive)
                IF OLD.valid_to IS NULL AND NEW.valid_to IS NOT NULL THEN
                    INSERT INTO dependency_history (
                        id, dependency_id, change_type, source_asset_id, target_asset_id,
                        target_port, protocol, bytes_total, flows_total,
                        reason, triggered_by, previous_state, new_state
                    ) VALUES (
                        gen_random_uuid(),
                        NEW.id,
                        'deleted',
                        NEW.source_asset_id,
                        NEW.target_asset_id,
                        NEW.target_port,
                        NEW.protocol,
                        NEW.bytes_total,
                        NEW.flows_total,
                        'Dependency marked as inactive',
                        'system',
                        row_to_json(OLD)::jsonb,
                        row_to_json(NEW)::jsonb
                    );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER dependency_audit_trigger
        AFTER INSERT OR UPDATE ON dependencies
        FOR EACH ROW EXECUTE FUNCTION track_dependency_changes();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS dependency_audit_trigger ON dependencies")
    op.execute("DROP FUNCTION IF EXISTS track_dependency_changes()")
    op.execute("DROP FUNCTION IF EXISTS calculate_blast_radius(UUID, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_upstream_dependencies(UUID, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_downstream_dependencies(UUID, INTEGER)")
    op.drop_table("alerts")
    op.drop_table("change_events")
    op.drop_table("dependency_history")
    op.drop_table("dependencies")
