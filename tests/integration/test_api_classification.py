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

    @pytest.mark.asyncio
    async def test_export_classification_rules_csv_is_internal_formats(self, async_client: AsyncClient):
        """Test that CSV export formats is_internal correctly (empty for None)."""
        # Create rules with different is_internal values
        rules_data = [
            {"name": "Export Test Internal", "cidr": "10.1.0.0/16", "is_internal": True, "priority": 1},
            {"name": "Export Test External", "cidr": "10.2.0.0/16", "is_internal": False, "priority": 2},
            {"name": "Export Test NotSpecified", "cidr": "10.3.0.0/16", "is_internal": None, "priority": 3},
        ]

        for rule_data in rules_data:
            await async_client.post("/api/v1/classification-rules", json=rule_data)

        # Export as CSV
        response = await async_client.get("/api/v1/classification-rules/export?format=csv")
        assert response.status_code == 200

        csv_content = response.text
        lines = csv_content.strip().split("\n")

        # Find the exported rules and verify is_internal format
        header = lines[0].split(",")
        is_internal_idx = header.index("is_internal")

        found_internal = False
        found_external = False
        found_not_specified = False

        for line in lines[1:]:
            if "Export Test Internal" in line:
                values = line.split(",")
                assert values[is_internal_idx] == "true", f"Expected 'true' for internal, got {values[is_internal_idx]}"
                found_internal = True
            elif "Export Test External" in line:
                values = line.split(",")
                assert values[is_internal_idx] == "false", f"Expected 'false' for external, got {values[is_internal_idx]}"
                found_external = True
            elif "Export Test NotSpecified" in line:
                values = line.split(",")
                assert values[is_internal_idx] == "", f"Expected empty string for not specified, got {values[is_internal_idx]}"
                found_not_specified = True

        assert found_internal, "Internal rule not found in export"
        assert found_external, "External rule not found in export"
        assert found_not_specified, "NotSpecified rule not found in export"

    @pytest.mark.asyncio
    async def test_import_classification_rules_is_internal_values(self, async_client: AsyncClient):
        """Test that import properly handles all is_internal value formats."""
        import io

        # Test CSV with various is_internal values
        csv_content = """name,cidr,is_internal,priority
Import Test True,10.100.0.0/16,true,1
Import Test Yes,10.101.0.0/16,yes,2
Import Test 1,10.102.0.0/16,1,3
Import Test Internal,10.103.0.0/16,internal,4
Import Test False,10.104.0.0/16,false,5
Import Test No,10.105.0.0/16,no,6
Import Test 0,10.106.0.0/16,0,7
Import Test External,10.107.0.0/16,external,8
Import Test Empty,10.108.0.0/16,,9
Import Test None,10.109.0.0/16,none,10
Import Test Null,10.110.0.0/16,null,11
"""

        # First preview the import
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        preview_response = await async_client.post(
            "/api/v1/classification-rules/import/preview",
            files=files,
        )
        assert preview_response.status_code == 200

        preview_data = preview_response.json()
        assert preview_data["to_create"] == 11
        assert preview_data["errors"] == 0

        # Now actually import (without auto-apply to avoid timing issues in tests)
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        import_response = await async_client.post(
            "/api/v1/classification-rules/import?autoApply=false",
            files=files,
        )
        assert import_response.status_code == 200

        import_data = import_response.json()
        assert import_data["created"] == 11
        assert import_data["errors"] == 0

        # Verify the rules were created with correct is_internal values
        # True cases
        for name in ["Import Test True", "Import Test Yes", "Import Test 1", "Import Test Internal"]:
            response = await async_client.get(f"/api/v1/classification-rules?search={name}")
            data = response.json()
            assert len(data["items"]) >= 1
            rule = next((r for r in data["items"] if r["name"] == name), None)
            assert rule is not None, f"Rule {name} not found"
            # Note: Summary doesn't include is_internal, so we need to fetch the full rule
            rule_response = await async_client.get(f"/api/v1/classification-rules/{rule['id']}")
            full_rule = rule_response.json()
            assert full_rule["is_internal"] is True, f"Expected True for {name}, got {full_rule['is_internal']}"

        # False cases
        for name in ["Import Test False", "Import Test No", "Import Test 0", "Import Test External"]:
            response = await async_client.get(f"/api/v1/classification-rules?search={name}")
            data = response.json()
            rule = next((r for r in data["items"] if r["name"] == name), None)
            assert rule is not None, f"Rule {name} not found"
            rule_response = await async_client.get(f"/api/v1/classification-rules/{rule['id']}")
            full_rule = rule_response.json()
            assert full_rule["is_internal"] is False, f"Expected False for {name}, got {full_rule['is_internal']}"

        # None cases
        for name in ["Import Test Empty", "Import Test None", "Import Test Null"]:
            response = await async_client.get(f"/api/v1/classification-rules?search={name}")
            data = response.json()
            rule = next((r for r in data["items"] if r["name"] == name), None)
            assert rule is not None, f"Rule {name} not found"
            rule_response = await async_client.get(f"/api/v1/classification-rules/{rule['id']}")
            full_rule = rule_response.json()
            assert full_rule["is_internal"] is None, f"Expected None for {name}, got {full_rule['is_internal']}"
