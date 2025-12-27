"""Unit tests for rate limiting middleware."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flowlens.api.middleware.rate_limit import (
    EndpointRateLimiter,
    RateLimitMiddleware,
    RateLimitState,
)


class TestRateLimitState:
    """Test cases for RateLimitState."""

    def test_initial_state(self):
        """Test initial state is empty."""
        state = RateLimitState()
        assert state.count() == 0
        assert state.requests == []

    def test_add_request(self):
        """Test adding a request."""
        state = RateLimitState()
        now = time.time()
        state.add(now)
        assert state.count() == 1

    def test_clean_old_requests(self):
        """Test cleaning old requests."""
        state = RateLimitState()
        now = time.time()

        # Add old request
        state.add(now - 120)  # 2 minutes ago
        # Add recent request
        state.add(now - 30)  # 30 seconds ago

        # Clean with 60 second window
        state.clean_old_requests(60, now)

        assert state.count() == 1  # Only recent request remains

    def test_clean_all_old_requests(self):
        """Test cleaning when all requests are old."""
        state = RateLimitState()
        now = time.time()

        state.add(now - 120)
        state.add(now - 100)

        state.clean_old_requests(60, now)

        assert state.count() == 0


@pytest.mark.unit
class TestRateLimitMiddleware:
    """Test cases for RateLimitMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def middleware(self, mock_app):
        """Create middleware instance for testing."""
        return RateLimitMiddleware(
            app=mock_app,
            requests_per_window=5,
            window_seconds=60,
        )

    def test_init_with_defaults(self, mock_app):
        """Test initialization with default settings."""
        with patch("flowlens.api.middleware.rate_limit.get_settings") as mock_settings:
            mock_settings.return_value.api.rate_limit_requests = 100
            mock_settings.return_value.api.rate_limit_window_seconds = 60

            middleware = RateLimitMiddleware(app=mock_app)

            assert middleware.requests_per_window == 100
            assert middleware.window_seconds == 60

    def test_init_with_custom_values(self, mock_app):
        """Test initialization with custom values."""
        middleware = RateLimitMiddleware(
            app=mock_app,
            requests_per_window=50,
            window_seconds=30,
        )

        assert middleware.requests_per_window == 50
        assert middleware.window_seconds == 30

    def test_get_client_id_direct(self, middleware):
        """Test client ID extraction from direct connection."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "192.168.1.100"

        client_id = middleware._get_client_id(request)

        assert client_id == "192.168.1.100"

    def test_get_client_id_forwarded(self, middleware):
        """Test client ID extraction from X-Forwarded-For."""
        request = MagicMock()
        request.headers.get.return_value = "10.0.0.1, 192.168.1.1"

        client_id = middleware._get_client_id(request)

        assert client_id == "10.0.0.1"

    def test_get_client_id_no_client(self, middleware):
        """Test client ID when no client info available."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        client_id = middleware._get_client_id(request)

        assert client_id == "unknown"

    def test_should_skip_health(self, middleware):
        """Test health endpoint is skipped."""
        assert middleware._should_skip("/health") is True

    def test_should_skip_metrics(self, middleware):
        """Test metrics endpoint is skipped."""
        assert middleware._should_skip("/metrics") is True

    def test_should_skip_docs(self, middleware):
        """Test docs endpoint is skipped."""
        assert middleware._should_skip("/docs") is True

    def test_should_not_skip_api(self, middleware):
        """Test API endpoints are not skipped."""
        assert middleware._should_skip("/api/v1/assets") is False

    def test_add_rate_limit_headers(self, middleware):
        """Test rate limit headers are added to response."""
        response = MagicMock()
        response.headers = {}

        middleware._add_rate_limit_headers(response, remaining=3, reset_seconds=45.5)

        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "3"
        assert response.headers["X-RateLimit-Reset"] == "45"

    def test_add_rate_limit_headers_negative_remaining(self, middleware):
        """Test remaining is clamped to 0."""
        response = MagicMock()
        response.headers = {}

        middleware._add_rate_limit_headers(response, remaining=-5, reset_seconds=30)

        assert response.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    async def test_dispatch_skipped_path(self, middleware):
        """Test dispatch skips excluded paths."""
        request = MagicMock()
        request.url.path = "/health"

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await middleware.dispatch(request, call_next)

        assert response == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_success(self, middleware):
        """Test successful request within limit."""
        request = MagicMock()
        request.url.path = "/api/v1/assets"
        request.method = "GET"
        request.headers.get.return_value = None
        request.client.host = "192.168.1.100"

        expected_response = MagicMock()
        expected_response.headers = {}
        call_next = AsyncMock(return_value=expected_response)

        response = await middleware.dispatch(request, call_next)

        assert response == expected_response
        assert "X-RateLimit-Limit" in response.headers
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_rate_limited(self, middleware):
        """Test request blocked when rate limit exceeded."""
        request = MagicMock()
        request.url.path = "/api/v1/assets"
        request.method = "GET"
        request.headers.get.return_value = None
        request.client.host = "192.168.1.100"

        call_next = AsyncMock()

        # Make requests up to the limit
        for _ in range(5):
            response = MagicMock()
            response.headers = {}
            call_next.return_value = response
            await middleware.dispatch(request, call_next)

        # Next request should be rate limited
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_dispatch_different_clients(self, middleware):
        """Test different clients have separate limits."""
        call_next = AsyncMock()

        for i in range(3):
            # Client 1
            request1 = MagicMock()
            request1.url.path = "/api/v1/assets"
            request1.method = "GET"
            request1.headers.get.return_value = None
            request1.client.host = "192.168.1.100"

            response = MagicMock()
            response.headers = {}
            call_next.return_value = response
            await middleware.dispatch(request1, call_next)

            # Client 2
            request2 = MagicMock()
            request2.url.path = "/api/v1/assets"
            request2.method = "GET"
            request2.headers.get.return_value = None
            request2.client.host = "192.168.1.101"

            await middleware.dispatch(request2, call_next)

        # Both clients should still have remaining quota
        # Client 1 has made 3 requests out of 5
        state1 = middleware._client_states["192.168.1.100"]
        assert state1.count() == 3

        # Client 2 has made 3 requests out of 5
        state2 = middleware._client_states["192.168.1.101"]
        assert state2.count() == 3


@pytest.mark.unit
class TestEndpointRateLimiter:
    """Test cases for EndpointRateLimiter."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        limiter = EndpointRateLimiter()

        assert limiter.requests_per_minute == 10
        assert limiter.window_seconds == 60

    def test_init_custom(self):
        """Test initialization with custom values."""
        limiter = EndpointRateLimiter(requests_per_minute=5)

        assert limiter.requests_per_minute == 5

    def test_default_key(self):
        """Test default key extraction."""
        limiter = EndpointRateLimiter()

        request = MagicMock()
        request.client.host = "192.168.1.100"
        request.url.path = "/api/v1/bulk"

        key = limiter._default_key(request)

        assert key == "192.168.1.100:/api/v1/bulk"

    @pytest.mark.asyncio
    async def test_call_success(self):
        """Test successful call within limit."""
        limiter = EndpointRateLimiter(requests_per_minute=5)

        request = MagicMock()
        request.client.host = "192.168.1.100"
        request.url.path = "/api/v1/bulk"

        # Should not raise
        await limiter(request)

    @pytest.mark.asyncio
    async def test_call_rate_limited(self):
        """Test call blocked when limit exceeded."""
        from fastapi import HTTPException

        limiter = EndpointRateLimiter(requests_per_minute=3)

        request = MagicMock()
        request.client.host = "192.168.1.100"
        request.url.path = "/api/v1/bulk"

        # Use up the limit
        for _ in range(3):
            await limiter(request)

        # Next call should raise
        with pytest.raises(HTTPException) as exc_info:
            await limiter(request)

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_custom_key_func(self):
        """Test custom key function."""
        def custom_key(request):
            return f"custom:{request.headers.get('X-API-Key', 'anonymous')}"

        limiter = EndpointRateLimiter(
            requests_per_minute=5,
            key_func=custom_key,
        )

        request = MagicMock()
        request.headers.get.return_value = "api-key-123"

        await limiter(request)

        assert "custom:api-key-123" in limiter._client_states
