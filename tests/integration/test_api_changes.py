"""Integration tests for Changes API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestChangesAPI:
    """Test cases for Changes API endpoints."""

    @pytest.mark.asyncio
    async def test_list_changes_empty(self, async_client: AsyncClient):
        """Test listing changes when database is empty."""
        response = await async_client.get("/api/v1/changes")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_changes_pagination(self, async_client: AsyncClient):
        """Test change listing pagination."""
        response = await async_client.get(
            "/api/v1/changes",
            params={"page": 1, "pageSize": 10},
        )
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "page" in data

    @pytest.mark.asyncio
    async def test_list_changes_filter_by_type(self, async_client: AsyncClient):
        """Test filtering changes by change type."""
        response = await async_client.get(
            "/api/v1/changes",
            params={"changeType": "dependency_created"},
        )
        assert response.status_code == 200

        data = response.json()
        # All returned changes should be of the requested type
        for item in data.get("items", []):
            assert item.get("change_type") == "dependency_created"

    @pytest.mark.asyncio
    async def test_list_changes_filter_by_asset(self, async_client: AsyncClient):
        """Test filtering changes by asset ID."""
        # First create an asset
        asset_data = {
            "name": "changes-test-asset",
            "asset_type": "server",
            "ip_address": "192.168.20.1",
        }
        asset_resp = await async_client.post("/api/v1/assets", json=asset_data)
        asset_id = asset_resp.json()["id"]

        # Filter changes by asset (may be empty)
        response = await async_client.get(
            "/api/v1/changes",
            params={"assetId": asset_id},
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_get_change_not_found(self, async_client: AsyncClient):
        """Test getting non-existent change returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/changes/{fake_id}")
        assert response.status_code == 404


@pytest.mark.integration
class TestAnalysisAPI:
    """Test cases for Analysis API endpoints."""

    async def _create_test_topology(self, async_client: AsyncClient) -> str:
        """Create a simple topology and return the critical asset ID."""
        # Create critical asset
        critical_data = {
            "name": "critical-asset",
            "asset_type": "database",
            "ip_address": "192.168.30.1",
            "is_critical": True,
        }
        critical_resp = await async_client.post("/api/v1/assets", json=critical_data)
        critical_id = critical_resp.json()["id"]

        # Create dependent assets
        for i in range(3):
            dep_data = {
                "name": f"dependent-{i}",
                "asset_type": "server",
                "ip_address": f"192.168.30.{i + 10}",
            }
            dep_resp = await async_client.post("/api/v1/assets", json=dep_data)

            # Create dependency to critical asset
            await async_client.post("/api/v1/dependencies", json={
                "source_asset_id": dep_resp.json()["id"],
                "target_asset_id": critical_id,
                "target_port": 5432,
                "protocol": 6,
            })

        return critical_id

    @pytest.mark.asyncio
    async def test_blast_radius(self, async_client: AsyncClient):
        """Test blast radius analysis for an asset."""
        critical_id = await self._create_test_topology(async_client)

        response = await async_client.get(f"/api/v1/analysis/blast-radius/{critical_id}")
        assert response.status_code == 200

        data = response.json()
        # Should return affected assets
        assert "affected" in data or "nodes" in data or "assets" in data

    @pytest.mark.asyncio
    async def test_blast_radius_with_hops(self, async_client: AsyncClient):
        """Test blast radius with max hops parameter."""
        critical_id = await self._create_test_topology(async_client)

        response = await async_client.get(
            f"/api/v1/analysis/blast-radius/{critical_id}",
            params={"maxHops": 2},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_blast_radius_not_found(self, async_client: AsyncClient):
        """Test blast radius for non-existent asset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/analysis/blast-radius/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_spof_detection(self, async_client: AsyncClient):
        """Test single point of failure detection."""
        await self._create_test_topology(async_client)

        response = await async_client.get("/api/v1/analysis/spof")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_critical_paths(self, async_client: AsyncClient):
        """Test critical paths analysis."""
        critical_id = await self._create_test_topology(async_client)

        response = await async_client.get(f"/api/v1/analysis/critical-paths/{critical_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_impact_analysis(self, async_client: AsyncClient):
        """Test impact analysis endpoint."""
        critical_id = await self._create_test_topology(async_client)

        response = await async_client.post(
            "/api/v1/analysis/impact",
            json={"asset_ids": [critical_id]},
        )
        assert response.status_code == 200

        data = response.json()
        assert "impact" in data or "affected" in data or "assets" in data
