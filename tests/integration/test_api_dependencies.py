"""Integration tests for Dependency API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestDependencyAPI:
    """Test cases for Dependency API endpoints."""

    async def _create_test_assets(self, async_client: AsyncClient) -> tuple[str, str]:
        """Create two test assets and return their IDs."""
        asset1_data = {
            "name": "source-asset",
            "asset_type": "server",
            "ip_address": "192.168.1.100",
        }
        asset2_data = {
            "name": "target-asset",
            "asset_type": "database",
            "ip_address": "192.168.1.200",
        }

        resp1 = await async_client.post("/api/v1/assets", json=asset1_data)
        resp2 = await async_client.post("/api/v1/assets", json=asset2_data)

        return resp1.json()["id"], resp2.json()["id"]

    @pytest.mark.asyncio
    async def test_list_dependencies_empty(self, async_client: AsyncClient):
        """Test listing dependencies when database is empty."""
        response = await async_client.get("/api/v1/dependencies")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_create_dependency(self, async_client: AsyncClient):
        """Test creating a new dependency."""
        source_id, target_id = await self._create_test_assets(async_client)

        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
            "dependency_type": "postgresql",
        }

        response = await async_client.post("/api/v1/dependencies", json=dep_data)
        assert response.status_code == 201

        data = response.json()
        assert data["source_asset_id"] == source_id
        assert data["target_asset_id"] == target_id
        assert data["target_port"] == 5432
        assert data["protocol"] == 6
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_dependency(self, async_client: AsyncClient):
        """Test getting a dependency by ID."""
        source_id, target_id = await self._create_test_assets(async_client)

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
        }
        create_response = await async_client.post("/api/v1/dependencies", json=dep_data)
        dep_id = create_response.json()["id"]

        # Get the dependency
        response = await async_client.get(f"/api/v1/dependencies/{dep_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == dep_id
        assert data["source_asset_id"] == source_id
        assert data["target_asset_id"] == target_id

    @pytest.mark.asyncio
    async def test_get_dependency_not_found(self, async_client: AsyncClient):
        """Test getting non-existent dependency returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/dependencies/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_dependency(self, async_client: AsyncClient):
        """Test updating a dependency."""
        source_id, target_id = await self._create_test_assets(async_client)

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
            "is_critical": False,
        }
        create_response = await async_client.post("/api/v1/dependencies", json=dep_data)
        dep_id = create_response.json()["id"]

        # Update dependency
        update_data = {
            "is_critical": True,
            "dependency_type": "database",
        }
        response = await async_client.put(f"/api/v1/dependencies/{dep_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["is_critical"] is True
        assert data["dependency_type"] == "database"

    @pytest.mark.asyncio
    async def test_delete_dependency(self, async_client: AsyncClient):
        """Test deleting a dependency."""
        source_id, target_id = await self._create_test_assets(async_client)

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
        }
        create_response = await async_client.post("/api/v1/dependencies", json=dep_data)
        dep_id = create_response.json()["id"]

        # Delete dependency
        response = await async_client.delete(f"/api/v1/dependencies/{dep_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/v1/dependencies/{dep_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_dependencies_with_filter(self, async_client: AsyncClient):
        """Test listing dependencies with source filter."""
        source_id, target_id = await self._create_test_assets(async_client)

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
        }
        await async_client.post("/api/v1/dependencies", json=dep_data)

        # Filter by source
        response = await async_client.get(
            "/api/v1/dependencies",
            params={"sourceAssetId": source_id},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["source_asset_id"] == source_id

    @pytest.mark.asyncio
    async def test_get_dependencies_for_asset(self, async_client: AsyncClient):
        """Test getting dependencies for a specific asset."""
        source_id, target_id = await self._create_test_assets(async_client)

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
        }
        await async_client.post("/api/v1/dependencies", json=dep_data)

        # Get outbound dependencies for source asset
        response = await async_client.get(f"/api/v1/assets/{source_id}/dependencies")
        assert response.status_code == 200

        data = response.json()
        # Should find the dependency we created
        assert len(data.get("outbound", [])) >= 1 or data.get("total", 0) >= 1
