"""Integration tests for Gateway API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestGatewayAPI:
    """Test cases for Gateway API endpoints."""

    async def _create_test_assets(self, async_client: AsyncClient) -> tuple[str, str]:
        """Create test assets for gateway testing."""
        # Create source asset
        source_data = {
            "name": "gateway-source",
            "asset_type": "server",
            "ip_address": "192.168.60.100",
        }
        source_resp = await async_client.post("/api/v1/assets", json=source_data)
        source_id = source_resp.json()["id"]

        # Create gateway asset
        gateway_data = {
            "name": "gateway-router",
            "asset_type": "router",
            "ip_address": "192.168.60.1",
        }
        gateway_resp = await async_client.post("/api/v1/assets", json=gateway_data)
        gateway_id = gateway_resp.json()["id"]

        return source_id, gateway_id

    @pytest.mark.asyncio
    async def test_list_gateways_empty(self, async_client: AsyncClient):
        """Test listing gateways when database is empty."""
        response = await async_client.get("/api/v1/gateways")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_gateways_pagination(self, async_client: AsyncClient):
        """Test gateway listing with pagination."""
        response = await async_client.get(
            "/api/v1/gateways",
            params={"page": 1, "pageSize": 10},
        )
        assert response.status_code == 200

        data = response.json()
        if "total" in data:
            assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_get_gateways_for_asset(self, async_client: AsyncClient):
        """Test getting gateways for a specific asset."""
        source_id, _ = await self._create_test_assets(async_client)

        response = await async_client.get(f"/api/v1/gateways/for-asset/{source_id}")
        assert response.status_code == 200

        data = response.json()
        # May be empty if no gateway relationships exist
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_gateway_clients(self, async_client: AsyncClient):
        """Test getting clients using a gateway."""
        _, gateway_id = await self._create_test_assets(async_client)

        response = await async_client.get(f"/api/v1/gateways/clients/{gateway_id}")
        assert response.status_code == 200

        data = response.json()
        # May be empty if no clients
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_gateway_topology(self, async_client: AsyncClient):
        """Test getting gateway topology visualization data."""
        response = await async_client.get("/api/v1/gateways/topology")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data or "edges" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_gateways_for_nonexistent_asset(self, async_client: AsyncClient):
        """Test getting gateways for non-existent asset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/gateways/for-asset/{fake_id}")
        assert response.status_code in (200, 404)


@pytest.mark.integration
class TestMaintenanceWindowAPI:
    """Test cases for Maintenance Window API endpoints."""

    @pytest.mark.asyncio
    async def test_list_maintenance_windows(self, async_client: AsyncClient):
        """Test listing maintenance windows."""
        response = await async_client.get("/api/v1/maintenance")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_maintenance_window(self, async_client: AsyncClient):
        """Test creating a maintenance window."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        window_data = {
            "name": "Test Maintenance Window",
            "description": "Test maintenance",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
        }

        response = await async_client.post("/api/v1/maintenance", json=window_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Maintenance Window"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_maintenance_window(self, async_client: AsyncClient):
        """Test getting a maintenance window by ID."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        # Create window first
        window_data = {
            "name": "Get Test Window",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
        }
        create_response = await async_client.post("/api/v1/maintenance", json=window_data)
        window_id = create_response.json()["id"]

        # Get the window
        response = await async_client.get(f"/api/v1/maintenance/{window_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == window_id
        assert data["name"] == "Get Test Window"

    @pytest.mark.asyncio
    async def test_cancel_maintenance_window(self, async_client: AsyncClient):
        """Test cancelling a maintenance window."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        # Create window first
        window_data = {
            "name": "Cancel Test Window",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
        }
        create_response = await async_client.post("/api/v1/maintenance", json=window_data)
        window_id = create_response.json()["id"]

        # Cancel the window
        response = await async_client.post(f"/api/v1/maintenance/{window_id}/cancel")
        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_get_active_maintenance_windows(self, async_client: AsyncClient):
        """Test getting currently active maintenance windows."""
        response = await async_client.get("/api/v1/maintenance/active")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_check_asset_in_maintenance(self, async_client: AsyncClient):
        """Test checking if an asset is in maintenance."""
        # Create test asset
        asset_data = {
            "name": "maintenance-check-asset",
            "asset_type": "server",
            "ip_address": "192.168.70.1",
        }
        asset_resp = await async_client.post("/api/v1/assets", json=asset_data)
        asset_id = asset_resp.json()["id"]

        # Check maintenance status
        response = await async_client.get(f"/api/v1/maintenance/check/{asset_id}")
        assert response.status_code == 200

        data = response.json()
        # Should indicate whether asset is in maintenance
        assert "in_maintenance" in data or "active" in data or isinstance(data, bool)

    @pytest.mark.asyncio
    async def test_maintenance_window_not_found(self, async_client: AsyncClient):
        """Test getting non-existent maintenance window."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/maintenance/{fake_id}")
        assert response.status_code == 404
