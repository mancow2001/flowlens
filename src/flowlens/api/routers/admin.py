"""Admin API endpoints - health, metrics, system info."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from flowlens.common.config import get_settings
from flowlens.common.health import HealthChecker, HealthStatus

router = APIRouter(prefix="/admin", tags=["admin"])

# Health checker instance
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Get or create health checker singleton."""
    global _health_checker
    if _health_checker is None:
        settings = get_settings()
        _health_checker = HealthChecker(
            service_name="flowlens-api",
            version=settings.app_version,
        )
    return _health_checker


@router.get("/health")
async def health() -> dict[str, Any]:
    """Complete health check endpoint.

    Returns detailed health status of all components.
    """
    checker = get_health_checker()
    result = await checker.full_health()
    return result.to_dict()


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe.

    Returns 200 if the process is alive.
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, Any]:
    """Kubernetes readiness probe.

    Returns 200 if the service can handle requests.
    Checks database connectivity.
    """
    checker = get_health_checker()
    result = await checker.readiness()

    if result.status == HealthStatus.UNHEALTHY:
        return Response(
            content='{"status": "unhealthy"}',
            status_code=503,
            media_type="application/json",
        )

    return result.to_dict()


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def _is_ai_configured(settings) -> bool:
    """Check if AI/LLM features are properly configured."""
    llm = settings.llm
    if llm.provider == "openai_compatible":
        # OpenAI-compatible (Ollama, LM Studio) requires base_url
        return bool(llm.base_url)
    else:
        # Anthropic/OpenAI require api_key
        return bool(llm.api_key)


@router.get("/info")
async def info() -> dict[str, Any]:
    """Application info endpoint.

    Returns version and configuration info.
    """
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "kafka_enabled": settings.kafka.enabled,
            "redis_enabled": settings.redis.enabled,
            "auth_enabled": settings.auth.enabled,
            "ai_enabled": _is_ai_configured(settings),
        },
    }


@router.get("/config")
async def config() -> dict[str, Any]:
    """Configuration endpoint (non-sensitive values only).

    Returns current configuration for debugging.
    """
    settings = get_settings()
    return {
        "environment": settings.environment,
        "database": {
            "host": settings.database.host,
            "port": settings.database.port,
            "database": settings.database.database,
            "pool_size": settings.database.pool_size,
        },
        "ingestion": {
            "netflow_port": settings.ingestion.netflow_port,
            "sflow_port": settings.ingestion.sflow_port,
            "batch_size": settings.ingestion.batch_size,
            "queue_max_size": settings.ingestion.queue_max_size,
        },
        "api": {
            "host": settings.api.host,
            "port": settings.api.port,
            "workers": settings.api.workers,
            "rate_limit_requests": settings.api.rate_limit_requests,
        },
        "auth": {
            "enabled": settings.auth.enabled,
            "algorithm": settings.auth.algorithm,
            "access_token_expire_minutes": settings.auth.access_token_expire_minutes,
        },
    }
