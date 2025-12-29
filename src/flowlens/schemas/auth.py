"""Pydantic schemas for authentication API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from flowlens.models.auth import SAMLProviderType, UserRole


# ============================================================================
# Token Schemas
# ============================================================================


class TokenResponse(BaseModel):
    """Response containing access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""

    refresh_token: str


# ============================================================================
# Login Schemas
# ============================================================================


class LoginRequest(BaseModel):
    """Local user login request."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class PasswordChangeRequest(BaseModel):
    """Request to change password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ============================================================================
# User Schemas
# ============================================================================


class UserBase(BaseModel):
    """Base schema for user data."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.VIEWER


class UserCreate(UserBase):
    """Schema for creating a local user."""

    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: EmailStr | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """Schema for user response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    role: str
    is_active: bool
    is_local: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserList(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CurrentUserResponse(UserResponse):
    """Response for current authenticated user with additional info."""

    pass


class PasswordResetRequest(BaseModel):
    """Request to reset a user's password (admin action)."""

    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ============================================================================
# SAML Provider Schemas
# ============================================================================


class SAMLProviderBase(BaseModel):
    """Base schema for SAML provider data."""

    name: str = Field(..., min_length=1, max_length=255)
    provider_type: SAMLProviderType
    entity_id: str = Field(..., min_length=1, max_length=500)
    sso_url: str = Field(..., min_length=1, max_length=500)
    slo_url: str | None = Field(None, max_length=500)
    sp_entity_id: str = Field(..., min_length=1, max_length=500)
    role_attribute: str | None = Field(None, max_length=255)
    role_mapping: dict[str, str] | None = None
    default_role: UserRole = UserRole.VIEWER
    auto_provision_users: bool = True


class SAMLProviderCreate(SAMLProviderBase):
    """Schema for creating a SAML provider."""

    certificate: str = Field(..., min_length=1)


class SAMLProviderUpdate(BaseModel):
    """Schema for updating a SAML provider."""

    name: str | None = Field(None, min_length=1, max_length=255)
    entity_id: str | None = Field(None, min_length=1, max_length=500)
    sso_url: str | None = Field(None, min_length=1, max_length=500)
    slo_url: str | None = Field(None, max_length=500)
    certificate: str | None = None
    sp_entity_id: str | None = Field(None, min_length=1, max_length=500)
    role_attribute: str | None = Field(None, max_length=255)
    role_mapping: dict[str, str] | None = None
    default_role: UserRole | None = None
    auto_provision_users: bool | None = None


class SAMLProviderResponse(BaseModel):
    """Schema for SAML provider response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider_type: str
    entity_id: str
    sso_url: str
    slo_url: str | None = None
    sp_entity_id: str
    role_attribute: str | None = None
    role_mapping: dict[str, str] | None = None
    default_role: str
    auto_provision_users: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SAMLProviderWithCertificate(SAMLProviderResponse):
    """SAML provider response including certificate."""

    certificate: str


class SAMLProviderList(BaseModel):
    """List of SAML providers."""

    items: list[SAMLProviderResponse]
    total: int


# ============================================================================
# Auth Audit Log Schemas
# ============================================================================


class AuthAuditLogResponse(BaseModel):
    """Schema for auth audit log response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    email: str | None = None
    event_type: str
    event_details: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool
    created_at: datetime


class AuthAuditLogList(BaseModel):
    """Paginated list of auth audit logs."""

    items: list[AuthAuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# Auth Session Schemas
# ============================================================================


class AuthSessionResponse(BaseModel):
    """Schema for auth session response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ip_address: str | None = None
    user_agent: str | None = None
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime
    is_current: bool = False  # Indicates if this is the current session


class AuthSessionList(BaseModel):
    """List of auth sessions for a user."""

    items: list[AuthSessionResponse]
    total: int


# ============================================================================
# Auth Status Schemas
# ============================================================================


class AuthStatusResponse(BaseModel):
    """Response for auth system status."""

    auth_enabled: bool
    saml_enabled: bool
    setup_required: bool = False  # True if no users exist and setup is needed
    active_provider: SAMLProviderResponse | None = None


class InitialSetupRequest(BaseModel):
    """Request to create the initial admin user during setup."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets minimum requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class InitialSetupResponse(BaseModel):
    """Response after completing initial setup."""

    success: bool
    message: str
    user: UserResponse


class SAMLLoginInitResponse(BaseModel):
    """Response when initiating SAML login."""

    redirect_url: str
