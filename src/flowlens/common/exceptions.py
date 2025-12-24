"""Custom exceptions for FlowLens application.

Provides a hierarchy of exceptions with proper HTTP status codes
and structured error responses.
"""

from typing import Any


class FlowLensError(Exception):
    """Base exception for all FlowLens errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize exception with optional details.

        Args:
            message: Human-readable error message.
            details: Additional error details for debugging.
            cause: Original exception that caused this error.
        """
        self.message = message or self.message
        self.details = details or {}
        self.cause = cause
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        result = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


# 400 Bad Request errors
class ValidationError(FlowLensError):
    """Request validation failed."""

    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed"


class InvalidFlowDataError(ValidationError):
    """Invalid flow data received."""

    error_code = "INVALID_FLOW_DATA"
    message = "Invalid flow data format"


class InvalidQueryError(ValidationError):
    """Invalid query parameters."""

    error_code = "INVALID_QUERY"
    message = "Invalid query parameters"


# 401 Unauthorized errors
class AuthenticationError(FlowLensError):
    """Authentication failed."""

    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    message = "Authentication required"


class InvalidTokenError(AuthenticationError):
    """Invalid or expired token."""

    error_code = "INVALID_TOKEN"
    message = "Invalid or expired authentication token"


# 403 Forbidden errors
class AuthorizationError(FlowLensError):
    """Authorization failed."""

    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
    message = "Access denied"


class InsufficientPermissionsError(AuthorizationError):
    """User lacks required permissions."""

    error_code = "INSUFFICIENT_PERMISSIONS"
    message = "Insufficient permissions for this operation"


# 404 Not Found errors
class NotFoundError(FlowLensError):
    """Resource not found."""

    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class AssetNotFoundError(NotFoundError):
    """Asset not found."""

    error_code = "ASSET_NOT_FOUND"
    message = "Asset not found"


class DependencyNotFoundError(NotFoundError):
    """Dependency not found."""

    error_code = "DEPENDENCY_NOT_FOUND"
    message = "Dependency not found"


# 409 Conflict errors
class ConflictError(FlowLensError):
    """Resource conflict."""

    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


class DuplicateAssetError(ConflictError):
    """Duplicate asset."""

    error_code = "DUPLICATE_ASSET"
    message = "Asset with this identifier already exists"


# 422 Unprocessable Entity errors
class BusinessLogicError(FlowLensError):
    """Business logic validation failed."""

    status_code = 422
    error_code = "BUSINESS_LOGIC_ERROR"
    message = "Business logic validation failed"


class CircularDependencyError(BusinessLogicError):
    """Circular dependency detected."""

    error_code = "CIRCULAR_DEPENDENCY"
    message = "Circular dependency detected"


# 429 Too Many Requests errors
class RateLimitError(FlowLensError):
    """Rate limit exceeded."""

    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Rate limit exceeded"


# 500 Internal Server errors
class InternalError(FlowLensError):
    """Internal server error."""

    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "An internal error occurred"


class DatabaseError(InternalError):
    """Database operation failed."""

    error_code = "DATABASE_ERROR"
    message = "Database operation failed"


class ConfigurationError(InternalError):
    """Configuration error."""

    error_code = "CONFIGURATION_ERROR"
    message = "Service configuration error"


# 502 Bad Gateway errors
class ExternalServiceError(FlowLensError):
    """External service error."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"
    message = "External service unavailable"


class DNSResolutionError(ExternalServiceError):
    """DNS resolution failed."""

    error_code = "DNS_RESOLUTION_ERROR"
    message = "DNS resolution failed"


# 503 Service Unavailable errors
class ServiceUnavailableError(FlowLensError):
    """Service temporarily unavailable."""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class BackpressureError(ServiceUnavailableError):
    """System under backpressure."""

    error_code = "BACKPRESSURE"
    message = "System under high load, please retry later"
