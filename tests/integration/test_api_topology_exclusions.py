"""Integration tests for Topology Exclusions API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestTopologyExclusionsAPI:
    """Test cases for Topology Exclusions API endpoints."""

    async def _create_test_folder(self, async_client: AsyncClient) -> dict:
        """Create a test folder for exclusion testing."""
        folder_data = {
            "name": "exclusion-test-folder",
            "display_name": "Exclusion Test Folder",
        }
        response = await async_client.post("/api/v1/folders", json=folder_data)
        assert response.status_code == 201
        return response.json()

    async def _create_test_application(self, async_client: AsyncClient) -> dict:
        """Create a test application for exclusion testing."""
        app_data = {
            "name": "exclusion-test-app",
            "display_name": "Exclusion Test Application",
        }
        response = await async_client.post("/api/v1/applications", json=app_data)
        assert response.status_code == 201
        return response.json()

    @pytest.mark.asyncio
    async def test_list_exclusions_empty(self, async_client: AsyncClient):
        """Test listing exclusions when none exist."""
        response = await async_client.get("/api/v1/topology/exclusions")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_create_folder_exclusion(self, async_client: AsyncClient):
        """Test creating a folder exclusion."""
        folder = await self._create_test_folder(async_client)

        exclusion_data = {
            "entity_type": "folder",
            "entity_id": folder["id"],
            "reason": "Test exclusion",
        }
        response = await async_client.post("/api/v1/topology/exclusions", json=exclusion_data)
        assert response.status_code == 201

        data = response.json()
        assert data["entity_type"] == "folder"
        assert data["entity_id"] == folder["id"]
        assert data["entity_name"] == folder["name"]
        assert data["reason"] == "Test exclusion"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_application_exclusion(self, async_client: AsyncClient):
        """Test creating an application exclusion."""
        app = await self._create_test_application(async_client)

        exclusion_data = {
            "entity_type": "application",
            "entity_id": app["id"],
        }
        response = await async_client.post("/api/v1/topology/exclusions", json=exclusion_data)
        assert response.status_code == 201

        data = response.json()
        assert data["entity_type"] == "application"
        assert data["entity_id"] == app["id"]
        assert data["entity_name"] == app["name"]

    @pytest.mark.asyncio
    async def test_create_exclusion_duplicate(self, async_client: AsyncClient):
        """Test creating a duplicate exclusion returns error."""
        folder = await self._create_test_folder(async_client)

        exclusion_data = {
            "entity_type": "folder",
            "entity_id": folder["id"],
        }
        # Create first exclusion
        response1 = await async_client.post("/api/v1/topology/exclusions", json=exclusion_data)
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = await async_client.post("/api/v1/topology/exclusions", json=exclusion_data)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_exclusion_not_found(self, async_client: AsyncClient):
        """Test creating exclusion for non-existent entity."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        exclusion_data = {
            "entity_type": "folder",
            "entity_id": fake_id,
        }
        response = await async_client.post("/api/v1/topology/exclusions", json=exclusion_data)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_exclusions(self, async_client: AsyncClient):
        """Test listing exclusions after creating some."""
        folder = await self._create_test_folder(async_client)
        app = await self._create_test_application(async_client)

        # Create folder exclusion
        await async_client.post("/api/v1/topology/exclusions", json={
            "entity_type": "folder",
            "entity_id": folder["id"],
        })

        # Create application exclusion
        await async_client.post("/api/v1/topology/exclusions", json={
            "entity_type": "application",
            "entity_id": app["id"],
        })

        # List exclusions
        response = await async_client.get("/api/v1/topology/exclusions")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 2

        # Verify items have expected fields
        for item in data["items"]:
            assert "id" in item
            assert "entity_type" in item
            assert "entity_id" in item
            assert "created_at" in item

    @pytest.mark.asyncio
    async def test_delete_exclusion(self, async_client: AsyncClient):
        """Test deleting an exclusion."""
        folder = await self._create_test_folder(async_client)

        # Create exclusion
        create_response = await async_client.post("/api/v1/topology/exclusions", json={
            "entity_type": "folder",
            "entity_id": folder["id"],
        })
        exclusion_id = create_response.json()["id"]

        # Delete exclusion
        response = await async_client.delete(f"/api/v1/topology/exclusions/{exclusion_id}")
        assert response.status_code == 204

        # Verify it's deleted by listing
        list_response = await async_client.get("/api/v1/topology/exclusions")
        exclusion_ids = [item["id"] for item in list_response.json()["items"]]
        assert exclusion_id not in exclusion_ids

    @pytest.mark.asyncio
    async def test_delete_exclusion_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent exclusion."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.delete(f"/api/v1/topology/exclusions/{fake_id}")
        assert response.status_code == 404


@pytest.mark.integration
class TestArcTopologyWithExclusions:
    """Test cases for Arc Topology API with exclusions."""

    async def _create_test_folder_with_app(self, async_client: AsyncClient, name: str) -> tuple[dict, dict]:
        """Create a folder with an application for testing."""
        folder_data = {"name": f"test-folder-{name}"}
        folder_response = await async_client.post("/api/v1/folders", json=folder_data)
        folder = folder_response.json()

        app_data = {"name": f"test-app-{name}", "folder_id": folder["id"]}
        app_response = await async_client.post("/api/v1/applications", json=app_data)
        app = app_response.json()

        return folder, app

    @pytest.mark.asyncio
    async def test_arc_topology_without_exclusions(self, async_client: AsyncClient):
        """Test arc topology returns all data when no exclusions."""
        response = await async_client.get("/api/v1/topology/arc")
        assert response.status_code == 200

        data = response.json()
        assert "hierarchy" in data
        assert "dependencies" in data
        assert "statistics" in data

    @pytest.mark.asyncio
    async def test_arc_topology_with_exclusions_applied(self, async_client: AsyncClient):
        """Test arc topology filters out excluded entities."""
        folder, app = await self._create_test_folder_with_app(async_client, "exclusion-test")

        # Get topology before exclusion
        response_before = await async_client.get("/api/v1/topology/arc")
        data_before = response_before.json()

        # Create exclusion for the folder
        await async_client.post("/api/v1/topology/exclusions", json={
            "entity_type": "folder",
            "entity_id": folder["id"],
        })

        # Get topology after exclusion
        response_after = await async_client.get("/api/v1/topology/arc?apply_exclusions=true")
        data_after = response_after.json()

        # Verify the excluded folder is not in the hierarchy
        folder_ids_after = [f["id"] for f in data_after["hierarchy"]["roots"]]
        assert folder["id"] not in folder_ids_after

    @pytest.mark.asyncio
    async def test_arc_topology_with_exclusions_disabled(self, async_client: AsyncClient):
        """Test arc topology returns all data when exclusions disabled."""
        folder, app = await self._create_test_folder_with_app(async_client, "no-excl-test")

        # Create exclusion
        await async_client.post("/api/v1/topology/exclusions", json={
            "entity_type": "folder",
            "entity_id": folder["id"],
        })

        # Get topology with exclusions disabled
        response = await async_client.get("/api/v1/topology/arc?apply_exclusions=false")
        data = response.json()

        # The folder should still be present
        folder_ids = [f["id"] for f in data["hierarchy"]["roots"]]
        assert folder["id"] in folder_ids


@pytest.mark.integration
class TestAppDependenciesAPI:
    """Test cases for Application Dependencies API endpoints."""

    async def _create_test_application(self, async_client: AsyncClient, name: str) -> dict:
        """Create a test application."""
        app_data = {"name": f"dep-test-{name}"}
        response = await async_client.post("/api/v1/applications", json=app_data)
        assert response.status_code == 201
        return response.json()

    @pytest.mark.asyncio
    async def test_get_app_dependencies(self, async_client: AsyncClient):
        """Test getting application dependencies."""
        app = await self._create_test_application(async_client, "deps")

        response = await async_client.get(f"/api/v1/topology/arc/app/{app['id']}/dependencies")
        assert response.status_code == 200

        data = response.json()
        assert data["app_id"] == app["id"]
        assert data["app_name"] == app["name"]
        assert "dependencies" in data
        assert "total_connections" in data
        assert "total_bytes" in data
        assert "total_bytes_24h" in data

    @pytest.mark.asyncio
    async def test_get_app_dependencies_direction_filter(self, async_client: AsyncClient):
        """Test getting application dependencies with direction filter."""
        app = await self._create_test_application(async_client, "dir-filter")

        for direction in ["incoming", "outgoing", "both"]:
            response = await async_client.get(
                f"/api/v1/topology/arc/app/{app['id']}/dependencies",
                params={"direction": direction}
            )
            assert response.status_code == 200

            data = response.json()
            assert data["direction_filter"] == direction

    @pytest.mark.asyncio
    async def test_get_app_dependencies_not_found(self, async_client: AsyncClient):
        """Test getting dependencies for non-existent application."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/topology/arc/app/{fake_id}/dependencies")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_app_dependencies_csv(self, async_client: AsyncClient):
        """Test exporting application dependencies as CSV."""
        app = await self._create_test_application(async_client, "export")

        response = await async_client.get(f"/api/v1/topology/arc/app/{app['id']}/dependencies/export")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

        # Verify CSV header
        content = response.text
        lines = content.strip().split("\n")
        assert len(lines) >= 1  # At least header row
        header = lines[0].lower()
        assert "counterparty" in header
        assert "direction" in header
        assert "connections" in header

    @pytest.mark.asyncio
    async def test_export_app_dependencies_not_found(self, async_client: AsyncClient):
        """Test exporting dependencies for non-existent application."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_client.get(f"/api/v1/topology/arc/app/{fake_id}/dependencies/export")
        assert response.status_code == 404
