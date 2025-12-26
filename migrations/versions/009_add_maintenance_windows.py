"""Add maintenance_windows table for alert suppression during planned maintenance

Revision ID: 009
Revises: 008
Create Date: 2024-12-26 00:00:09.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create maintenance_windows table
    op.create_table(
        "maintenance_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Scope
        sa.Column("asset_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("environments", postgresql.ARRAY(sa.String(50)), nullable=True),
        sa.Column("datacenters", postgresql.ARRAY(sa.String(100)), nullable=True),
        # Schedule
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, default=False),
        sa.Column("recurrence_rule", sa.String(500), nullable=True),
        # Settings
        sa.Column("suppress_alerts", sa.Boolean(), nullable=False, default=True),
        sa.Column("suppress_notifications", sa.Boolean(), nullable=False, default=True),
        # Tracking
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
        sa.Column("suppressed_alerts_count", sa.Integer(), nullable=False, default=0),
        # Tags
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.CheckConstraint("end_time > start_time", name="ck_maintenance_windows_valid_time_range"),
    )

    # Create index for finding active windows in a time range
    op.create_index(
        "ix_maintenance_windows_active_time",
        "maintenance_windows",
        ["is_active", "start_time", "end_time"],
    )

    # Create a function to check if an asset is in maintenance
    op.execute("""
        CREATE OR REPLACE FUNCTION is_asset_in_maintenance(
            p_asset_id uuid,
            p_environment varchar(50) DEFAULT NULL,
            p_datacenter varchar(100) DEFAULT NULL
        )
        RETURNS boolean AS $$
        DECLARE
            window_count integer;
        BEGIN
            SELECT COUNT(*) INTO window_count
            FROM maintenance_windows mw
            WHERE mw.is_active = true
              AND mw.suppress_alerts = true
              AND NOW() BETWEEN mw.start_time AND mw.end_time
              AND (
                  -- No scope = affects all
                  (mw.asset_ids IS NULL AND mw.environments IS NULL AND mw.datacenters IS NULL)
                  -- Or asset is explicitly listed
                  OR (mw.asset_ids IS NOT NULL AND p_asset_id = ANY(mw.asset_ids))
                  -- Or environment matches
                  OR (mw.environments IS NOT NULL AND p_environment = ANY(mw.environments))
                  -- Or datacenter matches
                  OR (mw.datacenters IS NOT NULL AND p_datacenter = ANY(mw.datacenters))
              );

            RETURN window_count > 0;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create a function to get active maintenance windows for an asset
    op.execute("""
        CREATE OR REPLACE FUNCTION get_active_maintenance_windows(
            p_asset_id uuid DEFAULT NULL,
            p_environment varchar(50) DEFAULT NULL,
            p_datacenter varchar(100) DEFAULT NULL
        )
        RETURNS TABLE (
            id uuid,
            name varchar(255),
            start_time timestamptz,
            end_time timestamptz,
            suppress_alerts boolean,
            suppress_notifications boolean
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                mw.id,
                mw.name,
                mw.start_time,
                mw.end_time,
                mw.suppress_alerts,
                mw.suppress_notifications
            FROM maintenance_windows mw
            WHERE mw.is_active = true
              AND NOW() BETWEEN mw.start_time AND mw.end_time
              AND (
                  -- No scope = affects all
                  (mw.asset_ids IS NULL AND mw.environments IS NULL AND mw.datacenters IS NULL)
                  -- Or asset is explicitly listed
                  OR (p_asset_id IS NOT NULL AND mw.asset_ids IS NOT NULL AND p_asset_id = ANY(mw.asset_ids))
                  -- Or environment matches
                  OR (p_environment IS NOT NULL AND mw.environments IS NOT NULL AND p_environment = ANY(mw.environments))
                  -- Or datacenter matches
                  OR (p_datacenter IS NOT NULL AND mw.datacenters IS NOT NULL AND p_datacenter = ANY(mw.datacenters))
              )
            ORDER BY mw.start_time;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_active_maintenance_windows(uuid, varchar, varchar)")
    op.execute("DROP FUNCTION IF EXISTS is_asset_in_maintenance(uuid, varchar, varchar)")
    op.drop_index("ix_maintenance_windows_active_time", table_name="maintenance_windows")
    op.drop_table("maintenance_windows")
