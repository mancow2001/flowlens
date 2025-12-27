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
    from datetime import datetime, timezone

    # Header (24 bytes)
    version = 5
    count = 1
    sys_uptime = 1000000  # ms
    unix_secs = int(datetime.now(timezone.utc).timestamp())
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
# Classification Test Fixtures
# =============================================================================


@pytest.fixture
def sample_server_features() -> dict:
    """Features typical of a server asset."""
    from datetime import datetime, timezone
    return {
        "ip_address": "192.168.1.100/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 1000,
        "outbound_flows": 100,
        "inbound_bytes": 50_000_000,
        "outbound_bytes": 5_000_000,
        "fan_in_count": 50,
        "fan_out_count": 5,
        "fan_in_ratio": 0.9,
        "unique_dst_ports": 3,
        "unique_src_ports": 5,
        "well_known_port_ratio": 0.8,
        "ephemeral_port_ratio": 0.2,
        "persistent_listener_ports": [80, 443, 22],
        "protocol_distribution": {6: 900, 17: 100},  # TCP/UDP
        "avg_bytes_per_packet": 500,
        "total_flows": 1100,
        "active_hours_count": 22,
        "business_hours_ratio": 0.4,
        "has_db_ports": False,
        "has_storage_ports": False,
        "has_web_ports": True,
        "has_ssh_ports": True,
    }


@pytest.fixture
def sample_workstation_features() -> dict:
    """Features typical of a workstation asset."""
    from datetime import datetime, timezone
    return {
        "ip_address": "192.168.1.50/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 50,
        "outbound_flows": 500,
        "inbound_bytes": 1_000_000,
        "outbound_bytes": 500_000,
        "fan_in_count": 2,
        "fan_out_count": 80,
        "fan_in_ratio": 0.02,
        "unique_dst_ports": 50,
        "unique_src_ports": 2,
        "well_known_port_ratio": 0.0,
        "ephemeral_port_ratio": 0.9,
        "persistent_listener_ports": [],
        "protocol_distribution": {6: 500, 17: 50},
        "avg_bytes_per_packet": 200,
        "total_flows": 550,
        "active_hours_count": 10,
        "business_hours_ratio": 0.85,
        "has_db_ports": False,
        "has_storage_ports": False,
        "has_web_ports": False,
        "has_ssh_ports": False,
    }


@pytest.fixture
def sample_database_features() -> dict:
    """Features typical of a database server."""
    from datetime import datetime, timezone
    return {
        "ip_address": "192.168.1.200/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 500,
        "outbound_flows": 50,
        "inbound_bytes": 100_000_000,
        "outbound_bytes": 200_000_000,
        "fan_in_count": 10,
        "fan_out_count": 2,
        "fan_in_ratio": 0.83,
        "unique_dst_ports": 2,
        "unique_src_ports": 1,
        "well_known_port_ratio": 1.0,
        "ephemeral_port_ratio": 0.0,
        "persistent_listener_ports": [5432],
        "protocol_distribution": {6: 550},
        "avg_bytes_per_packet": 5000,
        "total_flows": 550,
        "active_hours_count": 23,
        "business_hours_ratio": 0.45,
        "has_db_ports": True,
        "has_storage_ports": False,
        "has_web_ports": False,
        "has_ssh_ports": False,
    }


@pytest.fixture
def sample_load_balancer_features() -> dict:
    """Features typical of a load balancer."""
    from datetime import datetime, timezone
    return {
        "ip_address": "192.168.1.10/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 10000,
        "outbound_flows": 10000,
        "inbound_bytes": 500_000_000,
        "outbound_bytes": 500_000_000,
        "fan_in_count": 200,
        "fan_out_count": 10,
        "fan_in_ratio": 0.95,
        "unique_dst_ports": 2,
        "unique_src_ports": 2,
        "well_known_port_ratio": 1.0,
        "ephemeral_port_ratio": 0.0,
        "persistent_listener_ports": [80, 443],
        "protocol_distribution": {6: 20000},
        "avg_bytes_per_packet": 1000,
        "total_flows": 20000,
        "active_hours_count": 24,
        "business_hours_ratio": 0.42,
        "has_db_ports": False,
        "has_storage_ports": False,
        "has_web_ports": True,
        "has_ssh_ports": False,
    }


# =============================================================================
# Gateway Test Fixtures
# =============================================================================


@pytest.fixture
def sample_gateway_observation_data() -> dict:
    """Sample gateway observation data."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return {
        "source_ip": "192.168.1.100",
        "gateway_ip": "192.168.1.1",
        "destination_ip": "10.0.0.1",
        "observation_source": "next_hop",
        "exporter_ip": "192.168.1.1",
        "window_start": now,
        "window_end": now,
        "bytes_total": 1000000,
        "flows_count": 100,
        "is_processed": False,
    }


@pytest.fixture
def sample_gateway_candidate() -> dict:
    """Sample gateway candidate data."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return {
        "source_ip": "192.168.1.100",
        "gateway_ip": "192.168.1.1",
        "bytes_total": 5_000_000,
        "flows_total": 500,
        "first_seen": now - timedelta(days=7),
        "last_seen": now,
        "observation_count": 100,
    }


# =============================================================================
# Change Detection Test Fixtures
# =============================================================================


@pytest.fixture
def sample_change_event_data() -> dict:
    """Sample change event data."""
    return {
        "change_type": "dependency_created",
        "summary": "New dependency detected",
        "description": "Asset A connected to Asset B on port 443",
        "impact_score": 30,
        "affected_assets_count": 2,
    }


@pytest.fixture
def sample_alert_data() -> dict:
    """Sample alert data."""
    return {
        "severity": "warning",
        "title": "New Dependency Discovered",
        "message": "A new dependency has been detected between assets.",
    }


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
