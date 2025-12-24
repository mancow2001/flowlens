"""FastAPI dependency injection for API endpoints."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.auth.jwt import decode_token, TokenPayload
from flowlens.common.config import get_settings
from flowlens.common.database import get_db
from flowlens.common.exceptions import AuthenticationError

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for request.

    Yields:
        Database session.
    """
    async for session in get_db():
        yield session


# Type alias for database session dependency
DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
) -> TokenPayload | None:
    """Get current authenticated user from JWT token.

    Args:
        credentials: Bearer token credentials.

    Returns:
        Token payload if authenticated, None otherwise.

    Raises:
        HTTPException: If token is invalid.
    """
    settings = get_settings()

    # Skip auth if disabled
    if not settings.auth.enabled:
        return None

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
        return payload
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
            headers={"WWW-Authenticate": "Bearer"},
        )


# Type alias for authenticated user dependency
CurrentUser = Annotated[TokenPayload | None, Depends(get_current_user)]


async def require_auth(
    user: CurrentUser,
) -> TokenPayload:
    """Require authentication for an endpoint.

    Args:
        user: Current user from token.

    Returns:
        Token payload.

    Raises:
        HTTPException: If not authenticated.
    """
    settings = get_settings()

    if not settings.auth.enabled:
        # Return dummy payload when auth disabled
        return TokenPayload(
            sub="anonymous",
            exp=0,
            iat=0,
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return user


AuthenticatedUser = Annotated[TokenPayload, Depends(require_auth)]


class PaginationParams:
    """Common pagination parameters."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="Page number")] = 1,
        page_size: Annotated[
            int,
            Query(ge=1, le=1000, alias="page_size", description="Items per page"),
        ] = 50,
    ) -> None:
        settings = get_settings()
        self.page = page
        self.page_size = min(page_size, settings.api.max_page_size)
        self.offset = (page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size for compatibility."""
        return self.page_size


Pagination = Annotated[PaginationParams, Depends()]


class SortParams:
    """Common sorting parameters."""

    def __init__(
        self,
        sort_by: Annotated[
            str | None,
            Query(alias="sortBy", description="Field to sort by"),
        ] = None,
        sort_order: Annotated[
            str,
            Query(
                alias="sortOrder",
                pattern=r"^(asc|desc)$",
                description="Sort order",
            ),
        ] = "desc",
    ) -> None:
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.ascending = sort_order == "asc"


Sorting = Annotated[SortParams, Depends()]


class TimeRangeParams:
    """Time range filter parameters."""

    def __init__(
        self,
        start_time: Annotated[
            str | None,
            Query(alias="startTime", description="Start time (ISO 8601)"),
        ] = None,
        end_time: Annotated[
            str | None,
            Query(alias="endTime", description="End time (ISO 8601)"),
        ] = None,
    ) -> None:
        from datetime import datetime

        self.start_time = (
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if start_time
            else None
        )
        self.end_time = (
            datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if end_time
            else None
        )


TimeRange = Annotated[TimeRangeParams, Depends()]
