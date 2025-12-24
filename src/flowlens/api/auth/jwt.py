"""JWT authentication utilities."""

from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel

from flowlens.common.config import get_settings
from flowlens.common.exceptions import InvalidTokenError


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # Subject (user ID or email)
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    roles: list[str] = []
    permissions: list[str] = []


class TokenPair(BaseModel):
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until access token expires


def create_access_token(
    subject: str,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        subject: Token subject (user ID or email).
        roles: User roles.
        permissions: User permissions.
        expires_delta: Token lifetime. Uses config default if not provided.

    Returns:
        Encoded JWT token.
    """
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.auth.access_token_expire_minutes)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "access",
    }

    if roles:
        payload["roles"] = roles
    if permissions:
        payload["permissions"] = permissions

    return jwt.encode(
        payload,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def create_refresh_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token.

    Args:
        subject: Token subject.
        expires_delta: Token lifetime.

    Returns:
        Encoded JWT token.
    """
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(days=settings.auth.refresh_token_expire_days)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "refresh",
    }

    return jwt.encode(
        payload,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def create_token_pair(
    subject: str,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> TokenPair:
    """Create access and refresh token pair.

    Args:
        subject: Token subject.
        roles: User roles.
        permissions: User permissions.

    Returns:
        Token pair.
    """
    settings = get_settings()

    access_token = create_access_token(subject, roles, permissions)
    refresh_token = create_refresh_token(subject)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT token.

    Returns:
        Decoded token payload.

    Raises:
        InvalidTokenError: If token is invalid or expired.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key.get_secret_value(),
            algorithms=[settings.auth.algorithm],
        )

        return TokenPayload(
            sub=payload.get("sub", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
        )

    except JWTError as e:
        raise InvalidTokenError(
            message="Invalid or expired token",
            details={"error": str(e)},
        )


def verify_refresh_token(token: str) -> str:
    """Verify a refresh token and return the subject.

    Args:
        token: Refresh token.

    Returns:
        Token subject.

    Raises:
        InvalidTokenError: If token is invalid or not a refresh token.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key.get_secret_value(),
            algorithms=[settings.auth.algorithm],
        )

        if payload.get("type") != "refresh":
            raise InvalidTokenError(message="Not a refresh token")

        return payload.get("sub", "")

    except JWTError as e:
        raise InvalidTokenError(
            message="Invalid refresh token",
            details={"error": str(e)},
        )
