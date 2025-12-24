"""Pytest configuration and fixtures for FlowLens tests."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from flowlens.api.main import app
from flowlens.common.config import Settings, get_settings
from flowlens.common.database import get_db
from flowlens.models.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Get test settings."""
    return Settings(
        environment="development",
        debug=True,
        database={"host": "localhost", "database": "flowlens_test"},
        auth={"enabled": False},
    )


@pytest_asyncio.fixture(scope="function")
async def test_db(test_settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session.

    Creates tables before test and drops them after.
    """
    # Create test engine
    engine = create_async_engine(
        test_settings.database.async_url,
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing API endpoints."""

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sync_client(test_db: AsyncSession) -> TestClient:
    """Create sync HTTP client for simpler tests."""

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_asset_data() -> dict[str, Any]:
    """Sample asset data for testing."""
    return {
        "name": f"test-server-{uuid4().hex[:8]}",
        "display_name": "Test Server",
        "asset_type": "server",
        "ip_address": "192.168.1.100",
        "hostname": "test-server.local",
        "datacenter": "dc1",
        "environment": "development",
        "is_internal": True,
        "is_critical": False,
    }


@pytest.fixture
def sample_dependency_data() -> dict[str, Any]:
    """Sample dependency data for testing."""
    return {
        "target_port": 443,
        "protocol": 6,  # TCP
        "dependency_type": "https",
        "is_critical": False,
    }


@pytest.fixture
def sample_netflow_v5_packet() -> bytes:
    """Sample NetFlow v5 packet for testing."""
    import struct
    from datetime import datetime

    # Header (24 bytes)
    version = 5
    count = 1
    sys_uptime = 1000000  # ms
    unix_secs = int(datetime.utcnow().timestamp())
    unix_nsecs = 0
    flow_sequence = 1
    engine_type = 0
    engine_id = 0
    sampling_interval = 0

    header = struct.pack(
        "!HHIIIIBBH",
        version,
        count,
        sys_uptime,
        unix_secs,
        unix_nsecs,
        flow_sequence,
        engine_type,
        engine_id,
        sampling_interval,
    )

    # Flow record (48 bytes)
    srcaddr = int.from_bytes(bytes([192, 168, 1, 100]), "big")
    dstaddr = int.from_bytes(bytes([10, 0, 0, 1]), "big")
    nexthop = 0
    input_if = 1
    output_if = 2
    packets = 100
    octets = 50000
    first = 900000  # ms before sys_uptime
    last = 999000
    srcport = 54321
    dstport = 443
    pad1 = 0
    tcp_flags = 0x18  # PSH+ACK
    prot = 6  # TCP
    tos = 0
    src_as = 0
    dst_as = 0
    src_mask = 24
    dst_mask = 24
    pad2 = 0

    record = struct.pack(
        "!IIIHHIIIIHHBBBBHHBBH",
        srcaddr,
        dstaddr,
        nexthop,
        input_if,
        output_if,
        packets,
        octets,
        first,
        last,
        srcport,
        dstport,
        pad1,
        tcp_flags,
        prot,
        tos,
        src_as,
        dst_as,
        src_mask,
        dst_mask,
        pad2,
    )

    return header + record


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
