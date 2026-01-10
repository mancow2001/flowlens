"""Add auto-clear fields to alerts.

Revision ID: 031
Revises: 030
Create Date: 2025-01-10

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auto_clear_eligible column
    op.add_column(
        "alerts",
        sa.Column(
            "auto_clear_eligible",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Add condition_cleared_at column
    op.add_column(
        "alerts",
        sa.Column(
            "condition_cleared_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Create index for auto_clear_eligible
    op.create_index(
        "ix_alerts_auto_clear_eligible",
        "alerts",
        ["auto_clear_eligible"],
    )

    # Create partial index for auto-clear candidates (unresolved, eligible alerts)
    op.execute(
        """
        CREATE INDEX ix_alerts_auto_clear_candidates
        ON alerts (auto_clear_eligible, condition_cleared_at)
        WHERE is_resolved = false AND auto_clear_eligible = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alerts_auto_clear_candidates")
    op.drop_index("ix_alerts_auto_clear_eligible", table_name="alerts")
    op.drop_column("alerts", "condition_cleared_at")
    op.drop_column("alerts", "auto_clear_eligible")
