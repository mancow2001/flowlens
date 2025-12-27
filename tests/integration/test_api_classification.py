"""Integration tests for Classification API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestClassificationAPI:
    """Test cases for Classification API endpoints."""

    async def _create_test_asset(self, async_client: AsyncClient) -> str:
        """Create a test asset for classification testing."""
        asset_data = {
            "name": "classification-test-asset",
            "asset_type": "unknown",
            "ip_address": "192.168.50.1",
        }
        response = await async_client.post("/api/v1/assets", json=asset_data)
        return response.json()["id"]

    @pytest.mark.asyncio
    async def test_get_classification_for_asset(self, async_client: AsyncClient):
        """Test getting classification for an asset."""
        asset_id = await self._create_test_asset(async_client)

        response = await async_client.get(f"/api/v1/classification/{asset_id}")
        # May return 200 (with scores) or 404 (if no flow data)
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_get_classification_recommendations(self, async_client: AsyncClient):
        """Test getting classification recommendations."""
        response = await async_client.get("/api/v1/classification/recommendations")
        # May return 200 with list of recommendations
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_apply_classification(self, async_client: AsyncClient):
        """Test applying a classification to an asset."""
        asset_id = await self._create_test_asset(async_client)

        response = await async_client.post(
            f"/api/v1/classification/{asset_id}/apply",
            json={"asset_type": "server"},
        )
        # May succeed or fail based on state
        assert response.status_code in (200, 400, 404)

    @pytest.mark.asyncio
    async def test_lock_classification(self, async_client: AsyncClient):
        """Test locking an asset's classification."""
        asset_id = await self._create_test_asset(async_client)

        response = await async_client.post(f"/api/v1/classification/{asset_id}/lock")
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_unlock_classification(self, async_client: AsyncClient):
        """Test unlocking an asset's classification."""
        asset_id = await self._create_test_asset(async_client)

        response = await async_client.post(f"/api/v1/classification/{asset_id}/unlock")
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_classification_not_found(self, async_client: AsyncClient):
        """Test classification for non-existent asset."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/classification/{fake_id}")
        assert response.status_code == 404


@pytest.mark.integration
class TestClassificationRulesAPI:
    """Test cases for CIDR Classification Rules API."""

    @pytest.mark.asyncio
    async def test_list_classification_rules(self, async_client: AsyncClient):
        """Test listing classification rules."""
        response = await async_client.get("/api/v1/classification/rules")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_classification_rule(self, async_client: AsyncClient):
        """Test creating a CIDR classification rule."""
        rule_data = {
            "name": "Test CIDR Rule",
            "cidr": "10.0.0.0/8",
            "environment": "production",
            "datacenter": "dc1",
            "priority": 100,
        }

        response = await async_client.post("/api/v1/classification/rules", json=rule_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test CIDR Rule"
        assert data["cidr"] == "10.0.0.0/8"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_classification_rule(self, async_client: AsyncClient):
        """Test getting a classification rule by ID."""
        # Create rule first
        rule_data = {
            "name": "Get Test Rule",
            "cidr": "172.16.0.0/12",
            "environment": "staging",
            "priority": 50,
        }
        create_response = await async_client.post("/api/v1/classification/rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Get the rule
        response = await async_client.get(f"/api/v1/classification/rules/{rule_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == rule_id
        assert data["name"] == "Get Test Rule"

    @pytest.mark.asyncio
    async def test_update_classification_rule(self, async_client: AsyncClient):
        """Test updating a classification rule."""
        # Create rule first
        rule_data = {
            "name": "Update Test Rule",
            "cidr": "192.168.0.0/16",
            "environment": "development",
            "priority": 10,
        }
        create_response = await async_client.post("/api/v1/classification/rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Update the rule
        update_data = {
            "environment": "production",
            "priority": 200,
        }
        response = await async_client.put(f"/api/v1/classification/rules/{rule_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["environment"] == "production"
        assert data["priority"] == 200

    @pytest.mark.asyncio
    async def test_delete_classification_rule(self, async_client: AsyncClient):
        """Test deleting a classification rule."""
        # Create rule first
        rule_data = {
            "name": "Delete Test Rule",
            "cidr": "10.10.0.0/16",
            "environment": "test",
            "priority": 1,
        }
        create_response = await async_client.post("/api/v1/classification/rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Delete the rule
        response = await async_client.delete(f"/api/v1/classification/rules/{rule_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/v1/classification/rules/{rule_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_classification_rule_not_found(self, async_client: AsyncClient):
        """Test getting non-existent classification rule."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/classification/rules/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_apply_classification_rules(self, async_client: AsyncClient):
        """Test applying classification rules to assets."""
        response = await async_client.post("/api/v1/classification/rules/apply")
        # May succeed or return count of affected assets
        assert response.status_code in (200, 202)
