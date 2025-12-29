"""Add authentication tables.

Creates tables for RBAC with SAML authentication:
- users: Local and SAML-provisioned users
- saml_providers: SAML IdP configuration
- auth_sessions: Refresh token tracking
- auth_audit_log: Authentication events

Revision ID: 018
Revises: 017
Create Date: 2025-12-29 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_local", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("saml_subject_id", sa.String(255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for users
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_saml_subject_id", "users", ["saml_subject_id"])
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_is_active", "users", ["is_active"])

    # Create saml_providers table
    op.create_table(
        "saml_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),  # azure_ad, okta, ping_identity
        sa.Column("entity_id", sa.String(500), nullable=False),
        sa.Column("sso_url", sa.String(500), nullable=False),
        sa.Column("slo_url", sa.String(500), nullable=True),
        sa.Column("certificate", sa.Text(), nullable=False),
        sa.Column("sp_entity_id", sa.String(500), nullable=False),
        sa.Column("role_attribute", sa.String(255), nullable=True),
        sa.Column("role_mapping", JSONB(), nullable=True),
        sa.Column("default_role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("auto_provision_users", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for saml_providers
    op.create_index("ix_saml_providers_is_active", "saml_providers", ["is_active"])
    op.create_index("ix_saml_providers_provider_type", "saml_providers", ["provider_type"])

    # Create auth_sessions table
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for auth_sessions
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    # Create auth_audit_log table
    op.create_table(
        "auth_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),  # Nullable for failed login attempts
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_details", JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for auth_audit_log
    op.create_index("ix_auth_audit_log_user_id", "auth_audit_log", ["user_id"])
    op.create_index("ix_auth_audit_log_event_type", "auth_audit_log", ["event_type"])
    op.create_index("ix_auth_audit_log_created_at", "auth_audit_log", ["created_at"])
    op.create_index("ix_auth_audit_log_email", "auth_audit_log", ["email"])

    # Add check constraint for role values
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT check_user_role
        CHECK (role IN ('admin', 'analyst', 'viewer'))
    """)

    op.execute("""
        ALTER TABLE saml_providers
        ADD CONSTRAINT check_provider_type
        CHECK (provider_type IN ('azure_ad', 'okta', 'ping_identity'))
    """)

    op.execute("""
        ALTER TABLE saml_providers
        ADD CONSTRAINT check_default_role
        CHECK (default_role IN ('admin', 'analyst', 'viewer'))
    """)


def downgrade() -> None:
    # Drop constraints
    op.execute("ALTER TABLE saml_providers DROP CONSTRAINT IF EXISTS check_default_role")
    op.execute("ALTER TABLE saml_providers DROP CONSTRAINT IF EXISTS check_provider_type")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_user_role")

    # Drop indexes and tables in reverse order
    op.drop_index("ix_auth_audit_log_email", table_name="auth_audit_log")
    op.drop_index("ix_auth_audit_log_created_at", table_name="auth_audit_log")
    op.drop_index("ix_auth_audit_log_event_type", table_name="auth_audit_log")
    op.drop_index("ix_auth_audit_log_user_id", table_name="auth_audit_log")
    op.drop_table("auth_audit_log")

    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_refresh_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_saml_providers_provider_type", table_name="saml_providers")
    op.drop_index("ix_saml_providers_is_active", table_name="saml_providers")
    op.drop_table("saml_providers")

    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_saml_subject_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
