"""Add entry_points table for multiple entry points per asset.

This migration refactors entry points from single port/protocol on
ApplicationMember to a separate EntryPoint table, allowing multiple
entry points per asset (e.g., a web server on ports 80 and 443).

Changes:
- Creates new 'entry_points' table with member_id, port, protocol, order, label
- Migrates existing entry point data from application_members to entry_points
- Drops old entry point columns from application_members (is_entry_point,
  entry_point_order, entry_point_port, entry_point_protocol)
- Drops the ix_app_members_entry_points index (no longer needed)

Revision ID: 022
Revises: 021
Create Date: 2025-12-30 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the new entry_points table
    op.create_table(
        "entry_points",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("application_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("port >= 1 AND port <= 65535", name="ck_entry_points_port_range"),
        sa.CheckConstraint("protocol >= 0 AND protocol <= 255", name="ck_entry_points_protocol_range"),
    )

    # Create indexes
    op.create_index("ix_entry_points_member_id", "entry_points", ["member_id"])
    op.create_index(
        "ix_entry_points_member_port_proto",
        "entry_points",
        ["member_id", "port", "protocol"],
        unique=True,
    )

    # 2. Migrate existing entry point data from application_members to entry_points
    # Only migrate rows where is_entry_point=True and entry_point_port is not null
    op.execute("""
        INSERT INTO entry_points (id, member_id, port, protocol, "order", label, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            id,
            entry_point_port,
            COALESCE(entry_point_protocol, 6),
            COALESCE(entry_point_order, 0),
            NULL,
            created_at,
            updated_at
        FROM application_members
        WHERE is_entry_point = true AND entry_point_port IS NOT NULL
    """)

    # 3. Drop the old index that depended on is_entry_point
    op.drop_index("ix_app_members_entry_points", table_name="application_members")

    # 4. Drop the old entry point columns from application_members
    op.drop_column("application_members", "is_entry_point")
    op.drop_column("application_members", "entry_point_order")
    op.drop_column("application_members", "entry_point_port")
    op.drop_column("application_members", "entry_point_protocol")


def downgrade() -> None:
    # 1. Re-add the old columns to application_members
    op.add_column(
        "application_members",
        sa.Column("is_entry_point", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "application_members",
        sa.Column("entry_point_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "application_members",
        sa.Column("entry_point_port", sa.Integer(), nullable=True),
    )
    op.add_column(
        "application_members",
        sa.Column("entry_point_protocol", sa.Integer(), nullable=True),
    )

    # 2. Re-create the old index
    op.create_index(
        "ix_app_members_entry_points",
        "application_members",
        ["application_id", "is_entry_point"],
    )

    # 3. Migrate data back from entry_points to application_members
    # For each member, take the entry point with the lowest order
    op.execute("""
        UPDATE application_members am
        SET
            is_entry_point = true,
            entry_point_port = ep.port,
            entry_point_protocol = ep.protocol,
            entry_point_order = ep."order"
        FROM (
            SELECT DISTINCT ON (member_id)
                member_id, port, protocol, "order"
            FROM entry_points
            ORDER BY member_id, "order" ASC
        ) ep
        WHERE am.id = ep.member_id
    """)

    # 4. Drop the entry_points table
    op.drop_index("ix_entry_points_member_port_proto", table_name="entry_points")
    op.drop_index("ix_entry_points_member_id", table_name="entry_points")
    op.drop_table("entry_points")
