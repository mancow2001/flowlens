"""Rate limiting middleware for API endpoints.

Implements a sliding window rate limiter with configurable limits per client.
Uses in-memory storage by default, can be extended to Redis for multi-instance.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import API_REQUESTS

logger = get_logger(__name__)


@dataclass
class RateLimitState:
    """Tracks rate limit state for a single client."""

    requests: list[float] = field(default_factory=list)

    def clean_old_requests(self, window_seconds: float, now: float) -> None:
        """Remove requests older than the window."""
        cutoff = now - window_seconds
        self.requests = [t for t in self.requests if t > cutoff]

    def count(self) -> int:
        """Get current request count in window."""
        return len(self.requests)

    def add(self, timestamp: float) -> None:
        """Add a new request timestamp."""
        self.requests.append(timestamp)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiting middleware.

    Limits requests per client IP within a configurable time window.
    Returns 429 Too Many Requests when limit is exceeded.

    Headers added to responses:
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Seconds until window resets
    - Retry-After: Seconds to wait before retrying (only on 429)
    """

    def __init__(
        self,
        app,
        requests_per_window: int | None = None,
        window_seconds: int | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            app: The ASGI application.
            requests_per_window: Max requests per window. Defaults to settings.
            window_seconds: Window size in seconds. Defaults to settings.
            exclude_paths: Paths to exclude from rate limiting.
        """
        super().__init__(app)

        settings = get_settings()
        self.requests_per_window = requests_per_window or settings.api.rate_limit_requests
        self.window_seconds = window_seconds or settings.api.rate_limit_window_seconds

        # Default excluded paths (health checks, metrics, docs)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

        # In-memory storage for rate limit state per client
        # For production multi-instance deployments, replace with Redis
        self._client_states: dict[str, RateLimitState] = defaultdict(RateLimitState)

        # Cleanup old entries periodically
        self._last_cleanup = time.time()
        self._cleanup_interval = 60.0  # Clean up every minute

        logger.info(
            "Rate limiter initialized",
            requests_per_window=self.requests_per_window,
            window_seconds=self.window_seconds,
            exclude_paths=self.exclude_paths,
        )

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request.

        Uses X-Forwarded-For header if present (for proxied requests),
        otherwise falls back to client host.
        """
        # Check for forwarded header (common with load balancers/proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"

    def _should_skip(self, path: str) -> bool:
        """Check if path should be excluded from rate limiting."""
        return any(path.startswith(excluded) for excluded in self.exclude_paths)

    def _cleanup_old_clients(self, now: float) -> None:
        """Remove client entries that haven't been seen recently."""
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        cutoff = now - (self.window_seconds * 2)

        # Find clients with no recent requests
        stale_clients = [
            client_id
            for client_id, state in self._client_states.items()
            if not state.requests or max(state.requests) < cutoff
        ]

        for client_id in stale_clients:
            del self._client_states[client_id]

        if stale_clients:
            logger.debug(
                "Cleaned up stale rate limit entries",
                removed_count=len(stale_clients),
                remaining_count=len(self._client_states),
            )

    def _add_rate_limit_headers(
        self,
        response: Response,
        remaining: int,
        reset_seconds: float,
    ) -> None:
        """Add rate limit headers to response."""
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(reset_seconds))

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request with rate limiting."""
        # Skip excluded paths
        if self._should_skip(request.url.path):
            return await call_next(request)

        now = time.time()
        client_id = self._get_client_id(request)

        # Periodic cleanup
        self._cleanup_old_clients(now)

        # Get or create client state
        state = self._client_states[client_id]

        # Clean old requests from this client's window
        state.clean_old_requests(self.window_seconds, now)

        # Calculate remaining requests and reset time
        current_count = state.count()
        remaining = self.requests_per_window - current_count - 1  # -1 for this request

        # Calculate when window resets (oldest request + window)
        if state.requests:
            reset_seconds = state.requests[0] + self.window_seconds - now
        else:
            reset_seconds = self.window_seconds

        # Check if rate limit exceeded
        if current_count >= self.requests_per_window:
            logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                path=request.url.path,
                current_count=current_count,
                limit=self.requests_per_window,
            )

            # Record metric
            API_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                status=429,
            ).inc()

            # Return 429 response
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Maximum {self.requests_per_window} requests per {self.window_seconds} seconds.",
                    "retry_after": int(reset_seconds) + 1,
                },
            )
            self._add_rate_limit_headers(response, 0, reset_seconds)
            response.headers["Retry-After"] = str(int(reset_seconds) + 1)
            return response

        # Record this request
        state.add(now)

        # Process the request
        response = await call_next(request)

        # Add rate limit headers to successful response
        self._add_rate_limit_headers(response, remaining, reset_seconds)

        return response


class EndpointRateLimiter:
    """Per-endpoint rate limiting for sensitive operations.

    Use as a FastAPI dependency for endpoints that need stricter limits
    than the global rate limiter.

    Example:
        limiter = EndpointRateLimiter(requests_per_minute=10)

        @router.post("/sensitive")
        async def sensitive_endpoint(
            _: None = Depends(limiter),
        ):
            ...
    """

    def __init__(
        self,
        requests_per_minute: int = 10,
        key_func: Callable[[Request], str] | None = None,
    ) -> None:
        """Initialize endpoint rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute per client.
            key_func: Function to extract client key from request.
        """
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        self.key_func = key_func or self._default_key
        self._client_states: dict[str, RateLimitState] = defaultdict(RateLimitState)

    def _default_key(self, request: Request) -> str:
        """Default key extraction (client IP + path)."""
        if request.client:
            return f"{request.client.host}:{request.url.path}"
        return f"unknown:{request.url.path}"

    async def __call__(self, request: Request) -> None:
        """Check rate limit for this endpoint."""
        from fastapi import HTTPException

        now = time.time()
        key = self.key_func(request)
        state = self._client_states[key]

        # Clean old requests
        state.clean_old_requests(self.window_seconds, now)

        # Check limit
        if state.count() >= self.requests_per_minute:
            reset_seconds = state.requests[0] + self.window_seconds - now
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded for this endpoint. Maximum {self.requests_per_minute} requests per minute.",
                    "retry_after": int(reset_seconds) + 1,
                },
                headers={"Retry-After": str(int(reset_seconds) + 1)},
            )

        # Record request
        state.add(now)
