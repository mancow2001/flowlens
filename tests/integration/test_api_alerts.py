"""Integration tests for Alert API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAlertAPI:
    """Test cases for Alert API endpoints."""

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, async_client: AsyncClient):
        """Test listing alerts when database is empty."""
        response = await async_client.get("/api/v1/alerts")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_alerts_pagination(self, async_client: AsyncClient):
        """Test alert listing pagination parameters are accepted."""
        response = await async_client.get(
            "/api/v1/alerts",
            params={"page": 1, "pageSize": 10},
        )
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "page" in data

    @pytest.mark.asyncio
    async def test_list_alerts_filter_by_severity(self, async_client: AsyncClient):
        """Test filtering alerts by severity."""
        response = await async_client.get(
            "/api/v1/alerts",
            params={"severity": "critical"},
        )
        assert response.status_code == 200

        data = response.json()
        # All returned alerts should be critical
        for item in data.get("items", []):
            assert item.get("severity") == "critical"

    @pytest.mark.asyncio
    async def test_list_alerts_filter_by_status(self, async_client: AsyncClient):
        """Test filtering alerts by status."""
        response = await async_client.get(
            "/api/v1/alerts",
            params={"status": "active"},
        )
        assert response.status_code == 200

        data = response.json()
        # All returned alerts should be active
        for item in data.get("items", []):
            # Active alerts are neither acknowledged nor resolved
            assert item.get("acknowledged_at") is None or item.get("resolved_at") is None

    @pytest.mark.asyncio
    async def test_get_alert_not_found(self, async_client: AsyncClient):
        """Test getting non-existent alert returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/alerts/{fake_id}")
        assert response.status_code == 404


@pytest.mark.integration
class TestAlertRulesAPI:
    """Test cases for Alert Rules API endpoints."""

    @pytest.mark.asyncio
    async def test_list_alert_rules_empty(self, async_client: AsyncClient):
        """Test listing alert rules."""
        response = await async_client.get("/api/v1/alert-rules")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_alert_rule(self, async_client: AsyncClient):
        """Test creating a new alert rule."""
        rule_data = {
            "name": "Test Alert Rule",
            "description": "A test rule",
            "enabled": True,
            "change_types": ["dependency_created"],
            "severity": "warning",
            "title_template": "New dependency detected",
            "message_template": "A new dependency was created",
        }

        response = await async_client.post("/api/v1/alert-rules", json=rule_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Alert Rule"
        assert data["enabled"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_alert_rule_not_found(self, async_client: AsyncClient):
        """Test getting non-existent alert rule returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/alert-rules/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_alert_rule(self, async_client: AsyncClient):
        """Test updating an alert rule."""
        # Create rule first
        rule_data = {
            "name": "Update Test Rule",
            "enabled": True,
            "change_types": ["dependency_created"],
            "severity": "info",
            "title_template": "Test",
            "message_template": "Test message",
        }
        create_response = await async_client.post("/api/v1/alert-rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Update the rule
        update_data = {
            "enabled": False,
            "severity": "critical",
        }
        response = await async_client.put(f"/api/v1/alert-rules/{rule_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["enabled"] is False
        assert data["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_delete_alert_rule(self, async_client: AsyncClient):
        """Test deleting an alert rule."""
        # Create rule first
        rule_data = {
            "name": "Delete Test Rule",
            "enabled": True,
            "change_types": ["dependency_created"],
            "severity": "info",
            "title_template": "Test",
            "message_template": "Test message",
        }
        create_response = await async_client.post("/api/v1/alert-rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Delete the rule
        response = await async_client.delete(f"/api/v1/alert-rules/{rule_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/v1/alert-rules/{rule_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_toggle_alert_rule(self, async_client: AsyncClient):
        """Test toggling an alert rule on/off."""
        # Create enabled rule
        rule_data = {
            "name": "Toggle Test Rule",
            "enabled": True,
            "change_types": ["dependency_created"],
            "severity": "info",
            "title_template": "Test",
            "message_template": "Test message",
        }
        create_response = await async_client.post("/api/v1/alert-rules", json=rule_data)
        rule_id = create_response.json()["id"]

        # Toggle off
        response = await async_client.post(f"/api/v1/alert-rules/{rule_id}/toggle")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # Toggle back on
        response = await async_client.post(f"/api/v1/alert-rules/{rule_id}/toggle")
        assert response.status_code == 200
        assert response.json()["enabled"] is True
