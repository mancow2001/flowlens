"""Authentication and authorization models.

Provides models for RBAC with SAML authentication:
- User: Local and SAML-provisioned users
- SAMLProvider: SAML IdP configuration
- AuthSession: Refresh token tracking
- AuthAuditLog: Authentication events
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowlens.models.base import Base


class UserRole(str, Enum):
    """User role enumeration."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class SAMLProviderType(str, Enum):
    """SAML provider type enumeration."""

    AZURE_AD = "azure_ad"
    OKTA = "okta"
    PING_IDENTITY = "ping_identity"


class AuthEventType(str, Enum):
    """Authentication event type enumeration."""

    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    SAML_LOGIN = "saml_login"
    SAML_LOGIN_FAILED = "saml_login_failed"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"


class User(Base):
    """User model for local and SAML-provisioned users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.VIEWER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    saml_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    sessions: Mapped[list["AuthSession"]] = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_locked(self) -> bool:
        """Check if user account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.now(self.locked_until.tzinfo) < self.locked_until

    @property
    def role_enum(self) -> UserRole:
        """Get role as enum."""
        return UserRole(self.role)

    def has_role(self, roles: list[UserRole]) -> bool:
        """Check if user has any of the specified roles."""
        return self.role_enum in roles

    def to_dict(self, include_sensitive: bool = False) -> dict[str, Any]:
        """Convert to dictionary representation."""
        data = {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "is_active": self.is_active,
            "is_local": self.is_local,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["failed_login_attempts"] = self.failed_login_attempts
            data["locked_until"] = self.locked_until.isoformat() if self.locked_until else None
            data["saml_subject_id"] = self.saml_subject_id
        return data


class SAMLProvider(Base):
    """SAML Identity Provider configuration."""

    __tablename__ = "saml_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(500), nullable=False)
    sso_url: Mapped[str] = mapped_column(String(500), nullable=False)
    slo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate: Mapped[str] = mapped_column(Text, nullable=False)
    sp_entity_id: Mapped[str] = mapped_column(String(500), nullable=False)
    role_attribute: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_mapping: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    default_role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.VIEWER.value)
    auto_provision_users: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def provider_type_enum(self) -> SAMLProviderType:
        """Get provider type as enum."""
        return SAMLProviderType(self.provider_type)

    def get_role_for_groups(self, groups: list[str]) -> str:
        """Map SAML groups to a role using role_mapping.

        Args:
            groups: List of group names from SAML response.

        Returns:
            The mapped role, or default_role if no mapping found.
        """
        if not self.role_mapping:
            return self.default_role

        # Check each group against the mapping
        # Return the highest privilege role found
        role_priority = {UserRole.ADMIN.value: 3, UserRole.ANALYST.value: 2, UserRole.VIEWER.value: 1}
        best_role = self.default_role
        best_priority = role_priority.get(best_role, 0)

        for group in groups:
            if group in self.role_mapping:
                mapped_role = self.role_mapping[group]
                priority = role_priority.get(mapped_role, 0)
                if priority > best_priority:
                    best_role = mapped_role
                    best_priority = priority

        return best_role

    def to_dict(self, include_certificate: bool = False) -> dict[str, Any]:
        """Convert to dictionary representation."""
        data = {
            "id": str(self.id),
            "name": self.name,
            "provider_type": self.provider_type,
            "entity_id": self.entity_id,
            "sso_url": self.sso_url,
            "slo_url": self.slo_url,
            "sp_entity_id": self.sp_entity_id,
            "role_attribute": self.role_attribute,
            "role_mapping": self.role_mapping,
            "default_role": self.default_role,
            "auto_provision_users": self.auto_provision_users,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_certificate:
            data["certificate"] = self.certificate
        return data


class AuthSession(Base):
    """Authentication session for refresh token tracking."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")

    @property
    def is_valid(self) -> bool:
        """Check if session is valid (not expired or revoked)."""
        if self.revoked_at is not None:
            return False
        return datetime.now(self.expires_at.tzinfo) < self.expires_at

    def revoke(self) -> None:
        """Revoke this session."""
        from datetime import timezone

        self.revoked_at = datetime.now(timezone.utc)


class AuthAuditLog(Base):
    """Authentication audit log for tracking auth events."""

    __tablename__ = "auth_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    @classmethod
    def create_event(
        cls,
        event_type: AuthEventType,
        *,
        user_id: uuid.UUID | None = None,
        email: str | None = None,
        event_details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success: bool = True,
    ) -> "AuthAuditLog":
        """Create a new audit log event."""
        return cls(
            user_id=user_id,
            email=email,
            event_type=event_type.value,
            event_details=event_details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
        )
