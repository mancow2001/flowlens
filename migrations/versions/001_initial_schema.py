"""Initial schema - assets, services, applications

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Assets table
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("asset_type", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column("mac_address", sa.String(17), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("fqdn", sa.String(255), nullable=True),
        sa.Column("subnet", postgresql.CIDR(), nullable=True),
        sa.Column("vlan_id", sa.Integer(), nullable=True),
        sa.Column("datacenter", sa.String(100), nullable=True),
        sa.Column("environment", sa.String(50), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("criticality_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("bytes_in_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_out_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("connections_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connections_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
        sa.CheckConstraint("criticality_score >= 0 AND criticality_score <= 100"),
    )

    # Asset indexes
    op.create_index("ix_assets_id", "assets", ["id"])
    op.create_index("ix_assets_name", "assets", ["name"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_ip_address", "assets", ["ip_address"])
    op.create_index("ix_assets_hostname", "assets", ["hostname"])
    op.create_index("ix_assets_subnet", "assets", ["subnet"])
    op.create_index("ix_assets_datacenter", "assets", ["datacenter"])
    op.create_index("ix_assets_environment", "assets", ["environment"])
    op.create_index("ix_assets_is_internal", "assets", ["is_internal"])
    op.create_index("ix_assets_is_critical", "assets", ["is_critical"])
    op.create_index("ix_assets_team", "assets", ["team"])
    op.create_index("ix_assets_external_id", "assets", ["external_id"])
    op.create_index("ix_assets_last_seen", "assets", ["last_seen"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])
    op.create_index("ix_assets_deleted_at", "assets", ["deleted_at"])
    op.create_index("ix_assets_type_environment", "assets", ["asset_type", "environment"])
    op.create_index("ix_assets_subnet_type", "assets", ["subnet", "asset_type"])
    op.create_index("ix_assets_tags", "assets", ["tags"], postgresql_using="gin")

    # Services table
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("service_type", sa.String(50), nullable=True),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("connections_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("port >= 0 AND port <= 65535"),
        sa.CheckConstraint("protocol >= 0 AND protocol <= 255"),
    )

    op.create_index("ix_services_id", "services", ["id"])
    op.create_index("ix_services_asset_id", "services", ["asset_id"])
    op.create_index("ix_services_service_type", "services", ["service_type"])
    op.create_index("ix_services_asset_port_proto", "services", ["asset_id", "port", "protocol"], unique=True)

    # Applications table
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("team", sa.String(100), nullable=True),
        sa.Column("environment", sa.String(50), nullable=True),
        sa.Column("criticality", sa.String(20), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_index("ix_applications_id", "applications", ["id"])
    op.create_index("ix_applications_name", "applications", ["name"])
    op.create_index("ix_applications_team", "applications", ["team"])
    op.create_index("ix_applications_environment", "applications", ["environment"])

    # Application members table
    op.create_table(
        "application_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_application_members_id", "application_members", ["id"])
    op.create_index("ix_app_members_app_asset", "application_members", ["application_id", "asset_id"], unique=True)


def downgrade() -> None:
    op.drop_table("application_members")
    op.drop_table("applications")
    op.drop_table("services")
    op.drop_table("assets")
