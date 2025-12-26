"""Add classification_rules table for CIDR-based asset classification

Revision ID: 006
Revises: 005
Create Date: 2024-12-25 00:00:06.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create classification_rules table
    op.create_table(
        "classification_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cidr", postgresql.CIDR(), nullable=False, index=True),
        sa.Column("priority", sa.Integer(), nullable=False, default=100),
        sa.Column("environment", sa.String(50), nullable=True, index=True),
        sa.Column("datacenter", sa.String(100), nullable=True, index=True),
        sa.Column("location", sa.String(100), nullable=True, index=True),
        sa.Column("asset_type", sa.String(50), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=True),
        sa.Column("default_owner", sa.String(255), nullable=True),
        sa.Column("default_team", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, index=True),
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
    )

    # Create unique constraint on name
    op.create_unique_constraint(
        "uq_classification_rules_name",
        "classification_rules",
        ["name"],
    )

    # Create GiST index for efficient CIDR matching
    # Note: Using btree instead of gist for CIDR as it's simpler and sufficient
    op.create_index(
        "ix_classification_rules_cidr_active",
        "classification_rules",
        ["cidr", "is_active"],
    )

    # Create a function to get classification for an IP
    op.execute("""
        CREATE OR REPLACE FUNCTION get_ip_classification(ip_addr inet)
        RETURNS TABLE (
            environment varchar(50),
            datacenter varchar(100),
            location varchar(100),
            asset_type varchar(50),
            is_internal boolean,
            default_owner varchar(255),
            default_team varchar(100),
            rule_id uuid,
            rule_name varchar(255)
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                cr.environment,
                cr.datacenter,
                cr.location,
                cr.asset_type,
                cr.is_internal,
                cr.default_owner,
                cr.default_team,
                cr.id as rule_id,
                cr.name as rule_name
            FROM classification_rules cr
            WHERE cr.is_active = true
              AND ip_addr <<= cr.cidr
            ORDER BY
                masklen(cr.cidr) DESC,  -- More specific CIDR first
                cr.priority ASC          -- Lower priority number wins for ties
            LIMIT 1;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create a function to get all matching rules for an IP (for debugging/UI)
    op.execute("""
        CREATE OR REPLACE FUNCTION get_all_ip_classifications(ip_addr inet)
        RETURNS TABLE (
            rule_id uuid,
            rule_name varchar(255),
            cidr cidr,
            prefix_length int,
            priority int,
            environment varchar(50),
            datacenter varchar(100),
            location varchar(100),
            is_winning boolean
        ) AS $$
        DECLARE
            winning_id uuid;
        BEGIN
            -- Get the winning rule ID first
            SELECT cr.id INTO winning_id
            FROM classification_rules cr
            WHERE cr.is_active = true
              AND ip_addr <<= cr.cidr
            ORDER BY masklen(cr.cidr) DESC, cr.priority ASC
            LIMIT 1;

            RETURN QUERY
            SELECT
                cr.id as rule_id,
                cr.name as rule_name,
                cr.cidr,
                masklen(cr.cidr) as prefix_length,
                cr.priority,
                cr.environment,
                cr.datacenter,
                cr.location,
                (cr.id = winning_id) as is_winning
            FROM classification_rules cr
            WHERE cr.is_active = true
              AND ip_addr <<= cr.cidr
            ORDER BY masklen(cr.cidr) DESC, cr.priority ASC;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_all_ip_classifications(inet)")
    op.execute("DROP FUNCTION IF EXISTS get_ip_classification(inet)")
    op.drop_index("ix_classification_rules_cidr_active", table_name="classification_rules")
    op.drop_constraint("uq_classification_rules_name", "classification_rules", type_="unique")
    op.drop_table("classification_rules")
