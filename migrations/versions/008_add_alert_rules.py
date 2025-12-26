"""Add alert_rules table for configurable alert generation

Revision ID: 008
Revises: 007
Create Date: 2024-12-26 00:00:08.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create alert_rules table
    op.create_table(
        "alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
        # Trigger conditions
        sa.Column("change_types", postgresql.ARRAY(sa.String(50)), nullable=False),
        sa.Column("asset_filter", postgresql.JSONB(), nullable=True),
        # Alert configuration
        sa.Column("severity", sa.String(20), nullable=False, default="warning"),
        sa.Column("title_template", sa.String(255), nullable=False, default="{change_type} detected"),
        sa.Column("description_template", sa.Text(), nullable=False, default="{summary}"),
        # Notification settings
        sa.Column("notify_channels", postgresql.ARRAY(sa.String(50)), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, default=60),
        sa.Column("priority", sa.Integer(), nullable=False, default=100),
        # Tracking
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False, default=0),
        # Optional schedule
        sa.Column("schedule", postgresql.JSONB(), nullable=True),
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
        sa.CheckConstraint("cooldown_minutes >= 0", name="ck_alert_rules_cooldown_positive"),
        sa.CheckConstraint("priority >= 0", name="ck_alert_rules_priority_positive"),
    )

    # Create index for active rules by priority
    op.create_index(
        "ix_alert_rules_active_priority",
        "alert_rules",
        ["is_active", "priority"],
    )

    # Create GIN index for efficient array searches on change_types
    op.execute("""
        CREATE INDEX ix_alert_rules_change_types ON alert_rules USING GIN (change_types);
    """)

    # Insert default rules that match the current hardcoded behavior
    op.execute("""
        INSERT INTO alert_rules (id, name, description, is_active, change_types, severity, title_template, description_template, notify_channels, cooldown_minutes, priority)
        VALUES
        (
            gen_random_uuid(),
            'Critical Asset Changes',
            'Alert on changes affecting critical assets',
            true,
            ARRAY['asset_removed', 'asset_offline', 'critical_path_change'],
            'critical',
            '{change_type}: {asset_name}',
            '{summary}',
            ARRAY['email', 'webhook'],
            30,
            10
        ),
        (
            gen_random_uuid(),
            'New External Connections',
            'Alert when new external connections are detected',
            true,
            ARRAY['new_external_connection'],
            'warning',
            'New external connection detected',
            '{summary}',
            ARRAY['email'],
            60,
            50
        ),
        (
            gen_random_uuid(),
            'Dependency Changes',
            'Alert on dependency creation and removal',
            true,
            ARRAY['dependency_created', 'dependency_removed'],
            'info',
            'Dependency {change_type}',
            '{summary}',
            NULL,
            120,
            100
        ),
        (
            gen_random_uuid(),
            'Traffic Anomalies',
            'Alert on significant traffic spikes or drops',
            true,
            ARRAY['dependency_traffic_spike', 'dependency_traffic_drop'],
            'warning',
            'Traffic anomaly: {change_type}',
            '{summary}',
            ARRAY['webhook'],
            60,
            75
        ),
        (
            gen_random_uuid(),
            'Asset Discovery',
            'Alert when new assets are discovered',
            true,
            ARRAY['asset_discovered', 'service_discovered'],
            'info',
            'New {change_type}',
            '{summary}',
            NULL,
            0,
            150
        );
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_rules_change_types")
    op.drop_index("ix_alert_rules_active_priority", table_name="alert_rules")
    op.drop_table("alert_rules")
