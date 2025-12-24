"""Health check contract for FlowLens services.

Provides standardized health check responses for Kubernetes probes
and monitoring systems.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from flowlens.common.database import check_database_connection


class HealthStatus(str, Enum):
    """Health check status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: HealthStatus
    message: str | None = None
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResponse:
    """Complete health check response."""

    status: HealthStatus
    timestamp: datetime
    service: str
    version: str
    components: list[ComponentHealth] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "service": self.service,
            "version": self.version,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details if c.details else None,
                }
                for c in self.components
            ],
        }


class HealthChecker:
    """Health check manager for a service."""

    def __init__(self, service_name: str, version: str) -> None:
        """Initialize health checker.

        Args:
            service_name: Name of the service.
            version: Service version.
        """
        self.service_name = service_name
        self.version = version
        self._checks: list[tuple[str, Any]] = []

    def register_check(self, name: str, check_func: Any) -> None:
        """Register a health check function.

        Args:
            name: Name of the component being checked.
            check_func: Async function that returns ComponentHealth.
        """
        self._checks.append((name, check_func))

    async def check_database(self) -> ComponentHealth:
        """Check database connectivity."""
        import time

        start = time.perf_counter()
        try:
            is_healthy = await check_database_connection()
            latency = (time.perf_counter() - start) * 1000

            if is_healthy:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection successful",
                    latency_ms=round(latency, 2),
                )
            else:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection failed",
                    latency_ms=round(latency, 2),
                )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database check error: {str(e)}",
                latency_ms=round(latency, 2),
            )

    async def liveness(self) -> HealthResponse:
        """Kubernetes liveness probe - is the process alive?

        Returns minimal response, only checks if service can respond.
        """
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.utcnow(),
            service=self.service_name,
            version=self.version,
        )

    async def readiness(self) -> HealthResponse:
        """Kubernetes readiness probe - can the service handle requests?

        Checks critical dependencies (database, etc).
        """
        components = []
        overall_status = HealthStatus.HEALTHY

        # Always check database
        db_health = await self.check_database()
        components.append(db_health)

        if db_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY

        # Run registered checks
        for name, check_func in self._checks:
            try:
                component_health = await check_func()
                components.append(component_health)

                if component_health.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif (
                    component_health.status == HealthStatus.DEGRADED
                    and overall_status == HealthStatus.HEALTHY
                ):
                    overall_status = HealthStatus.DEGRADED
            except Exception as e:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                ))
                overall_status = HealthStatus.UNHEALTHY

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            service=self.service_name,
            version=self.version,
            components=components,
        )

    async def full_health(self) -> HealthResponse:
        """Complete health check with all component details.

        Used for monitoring dashboards and detailed status pages.
        """
        return await self.readiness()
