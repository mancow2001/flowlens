"""Query/API Service entry point.

FastAPI application factory with all routers and middleware.
"""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import NoReturn

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from flowlens.api.middleware import RateLimitMiddleware
from flowlens.api.websocket import get_connection_manager
from flowlens.common.config import get_settings
from flowlens.common.database import close_database, init_database
from flowlens.common.exceptions import FlowLensError
from flowlens.common.logging import bind_context, clear_context, get_logger, setup_logging
from flowlens.common.metrics import API_REQUESTS, API_REQUEST_DURATION, set_app_info

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Initializes and cleans up resources.
    """
    settings = get_settings()

    # Setup logging
    setup_logging(settings.logging)

    # Set app info for metrics
    set_app_info(
        version=settings.app_version,
        environment=settings.environment,
    )

    logger.info(
        "Starting FlowLens API",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize database
    await init_database(settings)
    logger.info("Database initialized")

    # Start WebSocket connection manager
    ws_manager = get_connection_manager()
    await ws_manager.start()
    logger.info("WebSocket connection manager started")

    yield

    # Cleanup
    logger.info("Shutting down FlowLens API")

    # Stop WebSocket connection manager
    ws_manager = get_connection_manager()
    await ws_manager.stop()
    logger.info("WebSocket connection manager stopped")

    await close_database()
    logger.info("Database closed")


def create_app() -> FastAPI:
    """Create FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title="FlowLens API",
        description="Application Dependency Mapping REST API",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware (optional, enabled by default)
    # Note: Middleware is executed in reverse order of addition,
    # so rate limiting runs after CORS but before request processing
    if settings.api.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_window=settings.api.rate_limit_requests,
            window_seconds=settings.api.rate_limit_window_seconds,
        )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time
        import uuid

        request_id = str(uuid.uuid4())[:8]
        bind_context(request_id=request_id)

        start = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start

            # Record metrics
            API_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
            ).inc()
            API_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)

            # Log request
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )

            return response

        except Exception as e:
            duration = time.perf_counter() - start
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration * 1000, 2),
            )
            raise
        finally:
            clear_context()

    # Exception handlers
    @app.exception_handler(FlowLensError)
    async def flowlens_exception_handler(
        request: Request,
        exc: FlowLensError,
    ) -> JSONResponse:
        logger.warning(
            "Application error",
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "Validation error",
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An internal error occurred",
            },
        )

    # Include routers
    from flowlens.api.routers import admin, alert_rules, alerts, analysis, asset_classification, assets, changes, classification, dependencies, gateways, maintenance, saved_views, settings, tasks, topology, ws

    app.include_router(admin.router)
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(assets.router, prefix="/api/v1")
    app.include_router(asset_classification.router, prefix="/api/v1")  # Behavioral classification
    app.include_router(classification.router, prefix="/api/v1")  # CIDR classification rules
    app.include_router(dependencies.router, prefix="/api/v1")
    app.include_router(gateways.router, prefix="/api/v1")
    app.include_router(topology.router, prefix="/api/v1")
    app.include_router(analysis.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(alert_rules.router, prefix="/api/v1")
    app.include_router(maintenance.router, prefix="/api/v1")
    app.include_router(changes.router, prefix="/api/v1")
    app.include_router(saved_views.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(ws.router, prefix="/api/v1")

    # Root endpoint
    @app.get("/")
    async def root() -> dict:
        return {
            "name": "FlowLens API",
            "version": settings.app_version,
            "docs": "/docs" if not settings.is_production else None,
        }

    return app


# Create app instance for uvicorn
app = create_app()


def run() -> NoReturn:
    """Run the API server."""
    import uvicorn

    settings = get_settings()

    try:
        # Use uvloop for better performance
        try:
            import uvloop
            uvloop.install()
        except ImportError:
            pass

        uvicorn.run(
            "flowlens.api.main:app",
            host=settings.api.host,
            port=settings.api.port,
            workers=settings.api.workers if not settings.api.reload else 1,
            reload=settings.api.reload,
            log_level="info",
            access_log=False,  # We use our own logging
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error("API failed to start", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    run()
