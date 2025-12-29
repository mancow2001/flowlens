"""Authentication service for local user authentication.

Provides password hashing, session management, and authentication logic.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.auth.jwt import create_token_pair, verify_refresh_token, TokenPair
from flowlens.common.config import get_settings
from flowlens.common.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from flowlens.models.auth import (
    AuthAuditLog,
    AuthEventType,
    AuthSession,
    User,
    UserRole,
)


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password.

    Returns:
        Hashed password.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify.
        hashed_password: Hashed password to compare against.

    Returns:
        True if password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """Hash a token for secure storage.

    Args:
        token: Token to hash.

    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def validate_password_policy(password: str) -> None:
    """Validate password meets policy requirements.

    Args:
        password: Password to validate.

    Raises:
        ValidationError: If password doesn't meet requirements.
    """
    settings = get_settings()

    errors = []

    if len(password) < settings.auth.password_min_length:
        errors.append(f"Password must be at least {settings.auth.password_min_length} characters")

    if settings.auth.password_require_uppercase and not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")

    if settings.auth.password_require_lowercase and not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")

    if settings.auth.password_require_digit and not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")

    if settings.auth.password_require_special:
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        if not any(c in special_chars for c in password):
            errors.append("Password must contain at least one special character")

    if errors:
        raise ValidationError(message="; ".join(errors))


class AuthService:
    """Service for handling authentication operations."""

    def __init__(self, db: AsyncSession):
        """Initialize auth service.

        Args:
            db: Database session.
        """
        self.db = db
        self.settings = get_settings()

    async def authenticate_local(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, TokenPair]:
        """Authenticate a local user with email and password.

        Args:
            email: User's email address.
            password: User's password.
            ip_address: Client IP address for audit logging.
            user_agent: Client user agent for audit logging.

        Returns:
            Tuple of (User, TokenPair).

        Raises:
            AuthenticationError: If authentication fails.
        """
        # Find user by email
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Log failed attempt even if user doesn't exist
            await self._log_auth_event(
                AuthEventType.LOGIN_FAILED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "user_not_found"},
            )
            raise AuthenticationError(message="Invalid email or password")

        # Check if account is locked
        if user.is_locked:
            await self._log_auth_event(
                AuthEventType.LOGIN_FAILED,
                user_id=user.id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "account_locked"},
            )
            raise AuthenticationError(message="Account is locked. Please try again later.")

        # Check if user is active
        if not user.is_active:
            await self._log_auth_event(
                AuthEventType.LOGIN_FAILED,
                user_id=user.id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "account_inactive"},
            )
            raise AuthenticationError(message="Account is inactive")

        # Check if user is a local user
        if not user.is_local:
            await self._log_auth_event(
                AuthEventType.LOGIN_FAILED,
                user_id=user.id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "not_local_user"},
            )
            raise AuthenticationError(message="Please use SSO to log in")

        # Verify password
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            # Increment failed login attempts
            user.failed_login_attempts += 1

            # Check if should lock account
            if user.failed_login_attempts >= self.settings.auth.max_failed_login_attempts:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=self.settings.auth.lockout_duration_minutes
                )
                await self._log_auth_event(
                    AuthEventType.ACCOUNT_LOCKED,
                    user_id=user.id,
                    email=email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True,
                    details={"lockout_minutes": self.settings.auth.lockout_duration_minutes},
                )

            await self.db.commit()

            await self._log_auth_event(
                AuthEventType.LOGIN_FAILED,
                user_id=user.id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "invalid_password"},
            )
            raise AuthenticationError(message="Invalid email or password")

        # Successful login - reset failed attempts and update last login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)

        # Create tokens
        token_pair = create_token_pair(
            subject=str(user.id),
            roles=[user.role],
        )

        # Create session record
        session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_token(token_pair.refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(
                days=self.settings.auth.refresh_token_expire_days
            ),
        )
        self.db.add(session)

        # Log successful login
        await self._log_auth_event(
            AuthEventType.LOGIN,
            user_id=user.id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )

        await self.db.commit()

        return user, token_pair

    async def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        """Refresh access token using refresh token.

        Args:
            refresh_token: Current refresh token.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            New TokenPair.

        Raises:
            AuthenticationError: If refresh token is invalid.
        """
        # Verify the refresh token JWT
        subject = verify_refresh_token(refresh_token)

        # Find the session by token hash
        token_hash = hash_token(refresh_token)
        result = await self.db.execute(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(timezone.utc),
            )
        )
        session = result.scalar_one_or_none()

        if session is None:
            raise AuthenticationError(message="Invalid or expired refresh token")

        # Get the user
        result = await self.db.execute(
            select(User).where(User.id == session.user_id)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            # Revoke the session
            session.revoke()
            await self.db.commit()
            raise AuthenticationError(message="User not found or inactive")

        # Revoke old session and create new one (token rotation)
        session.revoke()

        # Create new tokens
        new_token_pair = create_token_pair(
            subject=str(user.id),
            roles=[user.role],
        )

        # Create new session
        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_token(new_token_pair.refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(
                days=self.settings.auth.refresh_token_expire_days
            ),
        )
        self.db.add(new_session)

        # Log token refresh
        await self._log_auth_event(
            AuthEventType.TOKEN_REFRESH,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )

        await self.db.commit()

        return new_token_pair

    async def logout(
        self,
        user_id: uuid.UUID,
        refresh_token: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log out a user by revoking sessions.

        Args:
            user_id: User's ID.
            refresh_token: Specific refresh token to revoke. If None, revokes all sessions.
            ip_address: Client IP address.
            user_agent: Client user agent.
        """
        if refresh_token:
            # Revoke specific session
            token_hash = hash_token(refresh_token)
            await self.db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == user_id,
                    AuthSession.refresh_token_hash == token_hash,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
        else:
            # Revoke all sessions for user
            await self.db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )

        # Get user email for logging
        result = await self.db.execute(
            select(User.email).where(User.id == user_id)
        )
        email = result.scalar_one_or_none()

        await self._log_auth_event(
            AuthEventType.LOGOUT,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            details={"revoke_all": refresh_token is None},
        )

        await self.db.commit()

    async def change_password(
        self,
        user_id: uuid.UUID,
        current_password: str,
        new_password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Change a user's password.

        Args:
            user_id: User's ID.
            current_password: Current password.
            new_password: New password.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Raises:
            NotFoundError: If user not found.
            AuthenticationError: If current password is incorrect.
            ValidationError: If new password doesn't meet policy.
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise NotFoundError(resource="User", identifier=str(user_id))

        if not user.is_local:
            raise ValidationError(message="Cannot change password for SSO users")

        # Verify current password
        if not user.hashed_password or not verify_password(current_password, user.hashed_password):
            await self._log_auth_event(
                AuthEventType.PASSWORD_CHANGE,
                user_id=user.id,
                email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                details={"reason": "invalid_current_password"},
            )
            raise AuthenticationError(message="Current password is incorrect")

        # Validate new password
        validate_password_policy(new_password)

        # Update password
        user.hashed_password = hash_password(new_password)

        # Revoke all existing sessions (force re-login)
        await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )

        await self._log_auth_event(
            AuthEventType.PASSWORD_CHANGE,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )

        await self.db.commit()

    async def reset_password(
        self,
        user_id: uuid.UUID,
        new_password: str,
        admin_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Reset a user's password (admin action).

        Args:
            user_id: User's ID.
            new_password: New password.
            admin_id: ID of admin performing the reset.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Raises:
            NotFoundError: If user not found.
            ValidationError: If new password doesn't meet policy.
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise NotFoundError(resource="User", identifier=str(user_id))

        if not user.is_local:
            raise ValidationError(message="Cannot reset password for SSO users")

        # Validate new password
        validate_password_policy(new_password)

        # Update password
        user.hashed_password = hash_password(new_password)

        # Reset failed login attempts and unlock
        user.failed_login_attempts = 0
        user.locked_until = None

        # Revoke all existing sessions
        await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )

        await self._log_auth_event(
            AuthEventType.PASSWORD_RESET,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            details={"admin_id": str(admin_id)},
        )

        await self.db.commit()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """Get a user by ID.

        Args:
            user_id: User's ID.

        Returns:
            User model.

        Raises:
            NotFoundError: If user not found.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise NotFoundError(resource="User", identifier=str(user_id))

        return user

    async def get_user_sessions(
        self,
        user_id: uuid.UUID,
        include_revoked: bool = False,
    ) -> list[AuthSession]:
        """Get all sessions for a user.

        Args:
            user_id: User's ID.
            include_revoked: Include revoked sessions.

        Returns:
            List of AuthSession models.
        """
        query = select(AuthSession).where(AuthSession.user_id == user_id)

        if not include_revoked:
            query = query.where(
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(timezone.utc),
            )

        query = query.order_by(AuthSession.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _log_auth_event(
        self,
        event_type: AuthEventType,
        user_id: uuid.UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success: bool = True,
        details: dict | None = None,
    ) -> None:
        """Log an authentication event.

        Args:
            event_type: Type of event.
            user_id: User ID if known.
            email: Email address.
            ip_address: Client IP.
            user_agent: Client user agent.
            success: Whether event was successful.
            details: Additional event details.
        """
        log_entry = AuthAuditLog.create_event(
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            event_details=details,
        )
        self.db.add(log_entry)
