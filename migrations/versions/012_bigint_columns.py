"""Convert integer columns to bigint for large counters

Converts byte, packet, flow, and connection count columns from INTEGER
to BIGINT to prevent int32 overflow errors when values exceed ~2.1 billion.

Revision ID: 012
Revises: 011
Create Date: 2024-12-27 00:00:12.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # assets table - connection counters
    op.alter_column(
        "assets",
        "connections_in",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "assets",
        "connections_out",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # services table - connection counter
    op.alter_column(
        "services",
        "connections_total",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # flow_aggregates table - flows counter
    op.alter_column(
        "flow_aggregates",
        "flows_count",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # dependency_stats table - flows counter
    op.alter_column(
        "dependency_stats",
        "flows_total",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # gateway_observations table - flows counter
    op.alter_column(
        "gateway_observations",
        "flows_count",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Revert gateway_observations
    op.alter_column(
        "gateway_observations",
        "flows_count",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    # Revert dependency_stats
    op.alter_column(
        "dependency_stats",
        "flows_total",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    # Revert flow_aggregates
    op.alter_column(
        "flow_aggregates",
        "flows_count",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    # Revert services
    op.alter_column(
        "services",
        "connections_total",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    # Revert assets
    op.alter_column(
        "assets",
        "connections_out",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "assets",
        "connections_in",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
