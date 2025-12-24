"""Integration tests for Asset API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAssetAPI:
    """Test cases for Asset API endpoints."""

    @pytest.mark.asyncio
    async def test_list_assets_empty(self, async_client: AsyncClient):
        """Test listing assets when database is empty."""
        response = await async_client.get("/api/v1/assets")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_create_asset(
        self,
        async_client: AsyncClient,
        sample_asset_data: dict,
    ):
        """Test creating a new asset."""
        response = await async_client.post(
            "/api/v1/assets",
            json=sample_asset_data,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == sample_asset_data["name"]
        assert data["ip_address"] == sample_asset_data["ip_address"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_asset(
        self,
        async_client: AsyncClient,
        sample_asset_data: dict,
    ):
        """Test getting an asset by ID."""
        # Create asset first
        create_response = await async_client.post(
            "/api/v1/assets",
            json=sample_asset_data,
        )
        asset_id = create_response.json()["id"]

        # Get the asset
        response = await async_client.get(f"/api/v1/assets/{asset_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == asset_id
        assert data["name"] == sample_asset_data["name"]
        assert "services" in data  # Should include services

    @pytest.mark.asyncio
    async def test_get_asset_not_found(self, async_client: AsyncClient):
        """Test getting non-existent asset returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/assets/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_asset(
        self,
        async_client: AsyncClient,
        sample_asset_data: dict,
    ):
        """Test updating an asset."""
        # Create asset
        create_response = await async_client.post(
            "/api/v1/assets",
            json=sample_asset_data,
        )
        asset_id = create_response.json()["id"]

        # Update asset
        update_data = {"display_name": "Updated Name", "is_critical": True}
        response = await async_client.put(
            f"/api/v1/assets/{asset_id}",
            json=update_data,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["is_critical"] is True

    @pytest.mark.asyncio
    async def test_delete_asset(
        self,
        async_client: AsyncClient,
        sample_asset_data: dict,
    ):
        """Test soft deleting an asset."""
        # Create asset
        create_response = await async_client.post(
            "/api/v1/assets",
            json=sample_asset_data,
        )
        asset_id = create_response.json()["id"]

        # Delete asset
        response = await async_client.delete(f"/api/v1/assets/{asset_id}")
        assert response.status_code == 204

        # Verify it's not found
        get_response = await async_client.get(f"/api/v1/assets/{asset_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_ip(
        self,
        async_client: AsyncClient,
        sample_asset_data: dict,
    ):
        """Test creating asset with duplicate IP returns 409."""
        # Create first asset
        await async_client.post("/api/v1/assets", json=sample_asset_data)

        # Try to create with same IP
        sample_asset_data["name"] = "different-name"
        response = await async_client.post(
            "/api/v1/assets",
            json=sample_asset_data,
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_assets_pagination(self, async_client: AsyncClient):
        """Test asset listing pagination."""
        # Create multiple assets
        for i in range(5):
            await async_client.post(
                "/api/v1/assets",
                json={
                    "name": f"test-asset-{i}",
                    "asset_type": "server",
                    "ip_address": f"192.168.1.{i + 1}",
                },
            )

        # Get first page
        response = await async_client.get(
            "/api/v1/assets",
            params={"page": 1, "pageSize": 2},
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["pages"] == 3

    @pytest.mark.asyncio
    async def test_list_assets_filter_by_type(self, async_client: AsyncClient):
        """Test filtering assets by type."""
        # Create assets of different types
        for asset_type in ["server", "database", "server"]:
            await async_client.post(
                "/api/v1/assets",
                json={
                    "name": f"test-{asset_type}-{id(asset_type)}",
                    "asset_type": asset_type,
                    "ip_address": f"10.0.0.{id(asset_type) % 256}",
                },
            )

        # Filter by server type
        response = await async_client.get(
            "/api/v1/assets",
            params={"assetType": "server"},
        )
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["asset_type"] == "server"
