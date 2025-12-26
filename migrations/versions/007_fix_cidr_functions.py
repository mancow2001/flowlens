"""Fix CIDR type casting in classification functions

Revision ID: 007
Revises: 006
Create Date: 2024-12-25 00:00:07.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix the get_ip_classification function - remove ::inet cast
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
                masklen(cr.cidr) DESC,
                cr.priority ASC
            LIMIT 1;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Fix the get_all_ip_classifications function - remove ::inet casts
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
    # Restore original functions with ::inet casts
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
              AND ip_addr <<= cr.cidr::inet
            ORDER BY
                masklen(cr.cidr) DESC,
                cr.priority ASC
            LIMIT 1;
        END;
        $$ LANGUAGE plpgsql;
    """)

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
            SELECT cr.id INTO winning_id
            FROM classification_rules cr
            WHERE cr.is_active = true
              AND ip_addr <<= cr.cidr::inet
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
              AND ip_addr <<= cr.cidr::inet
            ORDER BY masklen(cr.cidr) DESC, cr.priority ASC;
        END;
        $$ LANGUAGE plpgsql;
    """)
