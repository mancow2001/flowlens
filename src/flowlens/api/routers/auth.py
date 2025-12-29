"""Authentication API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from flowlens.api.dependencies import AuthenticatedUser, DbSession
from flowlens.common.config import get_settings
from flowlens.common.exceptions import AuthenticationError, NotFoundError, ValidationError
from flowlens.schemas.auth import (
    AuthSessionList,
    AuthSessionResponse,
    AuthStatusResponse,
    CurrentUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from flowlens.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract client IP and user agent from request.

    Args:
        request: FastAPI request.

    Returns:
        Tuple of (ip_address, user_agent).
    """
    # Try to get real IP from forwarded headers
    ip_address = request.headers.get("X-Forwarded-For")
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    user_agent = request.headers.get("User-Agent")

    return ip_address, user_agent


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(db: DbSession) -> AuthStatusResponse:
    """Get authentication system status.

    Returns information about whether auth is enabled and SAML configuration.
    """
    settings = get_settings()

    # Get active SAML provider if any
    active_provider = None
    if settings.saml.enabled:
        from sqlalchemy import select
        from flowlens.models.auth import SAMLProvider

        result = await db.execute(
            select(SAMLProvider).where(SAMLProvider.is_active == True)  # noqa: E712
        )
        provider = result.scalar_one_or_none()
        if provider:
            from flowlens.schemas.auth import SAMLProviderResponse
            active_provider = SAMLProviderResponse.model_validate(provider)

    return AuthStatusResponse(
        auth_enabled=settings.auth.enabled,
        saml_enabled=settings.saml.enabled,
        active_provider=active_provider,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: DbSession,
) -> TokenResponse:
    """Authenticate with email and password.

    Returns access and refresh tokens on successful authentication.
    """
    settings = get_settings()

    if not settings.auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled",
        )

    ip_address, user_agent = get_client_info(request)

    auth_service = AuthService(db)

    try:
        user, token_pair = await auth_service.authenticate_local(
            email=body.email,
            password=body.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return TokenResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    body: RefreshTokenRequest,
    db: DbSession,
) -> TokenResponse:
    """Refresh access token using refresh token.

    Returns new access and refresh tokens.
    """
    settings = get_settings()

    if not settings.auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled",
        )

    ip_address, user_agent = get_client_info(request)

    auth_service = AuthService(db)

    try:
        token_pair = await auth_service.refresh_tokens(
            refresh_token=body.refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return TokenResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    user: AuthenticatedUser,
    db: DbSession,
    body: RefreshTokenRequest | None = None,
) -> None:
    """Log out the current user.

    If refresh_token is provided, only that session is revoked.
    Otherwise, all sessions for the user are revoked.
    """
    import uuid

    settings = get_settings()

    if not settings.auth.enabled:
        return

    ip_address, user_agent = get_client_info(request)

    auth_service = AuthService(db)

    await auth_service.logout(
        user_id=uuid.UUID(user.sub),
        refresh_token=body.refresh_token if body else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user(
    user: AuthenticatedUser,
    db: DbSession,
) -> CurrentUserResponse:
    """Get current authenticated user's information."""
    import uuid

    settings = get_settings()

    if not settings.auth.enabled:
        # Return anonymous user when auth is disabled
        return CurrentUserResponse(
            id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            email="anonymous@local",
            name="Anonymous",
            role="admin",
            is_active=True,
            is_local=True,
            last_login_at=None,
            created_at=None,
            updated_at=None,
        )

    auth_service = AuthService(db)

    try:
        db_user = await auth_service.get_user_by_id(uuid.UUID(user.sub))

        return CurrentUserResponse(
            id=db_user.id,
            email=db_user.email,
            name=db_user.name,
            role=db_user.role,
            is_active=db_user.is_active,
            is_local=db_user.is_local,
            last_login_at=db_user.last_login_at,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
        )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    user: AuthenticatedUser,
    body: PasswordChangeRequest,
    db: DbSession,
) -> None:
    """Change the current user's password.

    Requires the current password for verification.
    All existing sessions will be invalidated.
    """
    import uuid

    settings = get_settings()

    if not settings.auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled",
        )

    ip_address, user_agent = get_client_info(request)

    auth_service = AuthService(db)

    try:
        await auth_service.change_password(
            user_id=uuid.UUID(user.sub),
            current_password=body.current_password,
            new_password=body.new_password,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.get("/sessions", response_model=AuthSessionList)
async def get_sessions(
    user: AuthenticatedUser,
    db: DbSession,
) -> AuthSessionList:
    """Get all active sessions for the current user."""
    import uuid

    settings = get_settings()

    if not settings.auth.enabled:
        return AuthSessionList(items=[], total=0)

    auth_service = AuthService(db)

    sessions = await auth_service.get_user_sessions(uuid.UUID(user.sub))

    return AuthSessionList(
        items=[
            AuthSessionResponse(
                id=s.id,
                ip_address=s.ip_address,
                user_agent=s.user_agent,
                expires_at=s.expires_at,
                revoked_at=s.revoked_at,
                created_at=s.created_at,
                is_current=False,  # We don't track current session in this implementation
            )
            for s in sessions
        ],
        total=len(sessions),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    user: AuthenticatedUser,
    db: DbSession,
) -> None:
    """Revoke a specific session."""
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import select, update

    from flowlens.models.auth import AuthSession

    settings = get_settings()

    if not settings.auth.enabled:
        return

    # Verify session belongs to user
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.id == uuid.UUID(session_id),
            AuthSession.user_id == uuid.UUID(user.sub),
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Revoke the session
    await db.execute(
        update(AuthSession)
        .where(AuthSession.id == uuid.UUID(session_id))
        .values(revoked_at=datetime.now(timezone.utc))
    )

    await db.commit()
