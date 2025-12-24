"""Async SQLAlchemy database configuration and session management.

Provides async engine, session factory, and dependency injection for FastAPI.
Uses asyncpg for PostgreSQL with connection pooling.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from flowlens.common.config import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.pool import ConnectionPoolEntry

# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create async SQLAlchemy engine with connection pooling.

    Args:
        settings: Application settings. Uses global settings if not provided.

    Returns:
        Configured async engine instance.
    """
    if settings is None:
        settings = get_settings()

    db_settings = settings.database

    # Use NullPool for development (no connection pooling), QueuePool for production
    use_null_pool = settings.environment == "development"

    # Base engine arguments
    engine_kwargs: dict = {
        "echo": db_settings.echo,
        "echo_pool": db_settings.echo_pool,
        "connect_args": {
            "server_settings": {
                "application_name": "flowlens",
                "jit": "off",  # Disable JIT for more predictable latency
            },
            "command_timeout": 60,
        },
    }

    if use_null_pool:
        # NullPool doesn't accept pool configuration arguments
        engine_kwargs["poolclass"] = NullPool
    else:
        # Production: use connection pooling
        engine_kwargs["pool_size"] = db_settings.pool_size
        engine_kwargs["max_overflow"] = db_settings.max_overflow
        engine_kwargs["pool_timeout"] = db_settings.pool_timeout
        engine_kwargs["pool_recycle"] = db_settings.pool_recycle
        engine_kwargs["pool_pre_ping"] = True

    engine = create_async_engine(db_settings.async_url, **engine_kwargs)

    # Set up connection event handlers
    @event.listens_for(engine.sync_engine, "connect")
    def set_search_path(
        dbapi_connection: "ConnectionPoolEntry",
        connection_record: object,
    ) -> None:
        """Set default schema search path on new connections."""
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()

    return engine


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create async session factory for database operations.

    Args:
        engine: Async SQLAlchemy engine.

    Returns:
        Session factory for creating async sessions.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def init_database(settings: Settings | None = None) -> None:
    """Initialize database engine and session factory.

    Should be called during application startup.

    Args:
        settings: Application settings. Uses global settings if not provided.
    """
    global _engine, _session_factory

    if _engine is not None:
        return

    _engine = create_engine(settings)
    _session_factory = create_session_factory(_engine)


async def close_database() -> None:
    """Close database engine and cleanup connections.

    Should be called during application shutdown.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_engine() -> AsyncEngine:
    """Get the global database engine.

    Returns:
        The async database engine.

    Raises:
        RuntimeError: If database not initialized.
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the global session factory.

    Returns:
        The async session factory.

    Raises:
        RuntimeError: If database not initialized.
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session as context manager.

    Yields:
        Database session that auto-commits on success, rolls back on error.

    Example:
        async with get_session() as session:
            result = await session.execute(query)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session injection.

    Yields:
        Database session for the request lifetime.

    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Check if database connection is healthy.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def execute_raw_sql(sql: str, params: dict | None = None) -> list[dict]:
    """Execute raw SQL query and return results as dictionaries.

    Args:
        sql: SQL query string.
        params: Query parameters.

    Returns:
        List of result rows as dictionaries.
    """
    async with get_session() as session:
        result = await session.execute(text(sql), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]
