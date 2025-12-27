"""Integration tests for Topology API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestTopologyAPI:
    """Test cases for Topology API endpoints."""

    async def _create_test_assets_with_dependency(self, async_client: AsyncClient) -> tuple[str, str, str]:
        """Create test assets with a dependency."""
        # Create source asset
        source_data = {
            "name": "topology-source",
            "asset_type": "server",
            "ip_address": "192.168.10.1",
            "environment": "production",
        }
        source_resp = await async_client.post("/api/v1/assets", json=source_data)
        source_id = source_resp.json()["id"]

        # Create target asset
        target_data = {
            "name": "topology-target",
            "asset_type": "database",
            "ip_address": "192.168.10.2",
            "environment": "production",
        }
        target_resp = await async_client.post("/api/v1/assets", json=target_data)
        target_id = target_resp.json()["id"]

        # Create dependency
        dep_data = {
            "source_asset_id": source_id,
            "target_asset_id": target_id,
            "target_port": 5432,
            "protocol": 6,
        }
        dep_resp = await async_client.post("/api/v1/dependencies", json=dep_data)
        dep_id = dep_resp.json()["id"]

        return source_id, target_id, dep_id

    @pytest.mark.asyncio
    async def test_get_topology_empty(self, async_client: AsyncClient):
        """Test getting topology when database is empty."""
        response = await async_client.get("/api/v1/topology")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    @pytest.mark.asyncio
    async def test_get_topology_with_data(self, async_client: AsyncClient):
        """Test getting topology with assets and dependencies."""
        source_id, target_id, _ = await self._create_test_assets_with_dependency(async_client)

        response = await async_client.get("/api/v1/topology")
        assert response.status_code == 200

        data = response.json()
        assert len(data["nodes"]) >= 2
        assert len(data["edges"]) >= 1

        # Verify nodes contain our assets
        node_ids = [n["id"] for n in data["nodes"]]
        assert source_id in node_ids
        assert target_id in node_ids

    @pytest.mark.asyncio
    async def test_get_topology_with_limit(self, async_client: AsyncClient):
        """Test getting topology with limit parameter."""
        await self._create_test_assets_with_dependency(async_client)

        response = await async_client.get(
            "/api/v1/topology",
            params={"limit": 1},
        )
        assert response.status_code == 200

        data = response.json()
        # Should respect the limit
        assert len(data["nodes"]) <= 1

    @pytest.mark.asyncio
    async def test_get_topology_filter_by_environment(self, async_client: AsyncClient):
        """Test filtering topology by environment."""
        await self._create_test_assets_with_dependency(async_client)

        response = await async_client.get(
            "/api/v1/topology",
            params={"environment": "production"},
        )
        assert response.status_code == 200

        data = response.json()
        # All nodes should be from production environment
        for node in data["nodes"]:
            # Group nodes may not have environment
            if node.get("environment"):
                assert node["environment"] == "production"


@pytest.mark.integration
class TestPathFinderAPI:
    """Test cases for Path Finder API."""

    async def _create_connected_assets(self, async_client: AsyncClient) -> tuple[str, str, str]:
        """Create three connected assets: A → B → C."""
        # Create assets
        assets = []
        for i, name in enumerate(["path-start", "path-middle", "path-end"]):
            data = {
                "name": name,
                "asset_type": "server",
                "ip_address": f"10.0.0.{i + 1}",
            }
            resp = await async_client.post("/api/v1/assets", json=data)
            assets.append(resp.json()["id"])

        # Create A → B dependency
        await async_client.post("/api/v1/dependencies", json={
            "source_asset_id": assets[0],
            "target_asset_id": assets[1],
            "target_port": 80,
            "protocol": 6,
        })

        # Create B → C dependency
        await async_client.post("/api/v1/dependencies", json={
            "source_asset_id": assets[1],
            "target_asset_id": assets[2],
            "target_port": 443,
            "protocol": 6,
        })

        return tuple(assets)

    @pytest.mark.asyncio
    async def test_find_path_between_assets(self, async_client: AsyncClient):
        """Test finding path between two connected assets."""
        a_id, b_id, c_id = await self._create_connected_assets(async_client)

        # Find path from A to C
        response = await async_client.get(
            "/api/v1/topology/path",
            params={"source": a_id, "target": c_id},
        )
        assert response.status_code == 200

        data = response.json()
        assert "path" in data or "nodes" in data

    @pytest.mark.asyncio
    async def test_find_path_no_route(self, async_client: AsyncClient):
        """Test finding path between disconnected assets."""
        # Create two unconnected assets
        asset1_data = {
            "name": "isolated-1",
            "asset_type": "server",
            "ip_address": "172.16.0.1",
        }
        asset2_data = {
            "name": "isolated-2",
            "asset_type": "server",
            "ip_address": "172.16.0.2",
        }

        resp1 = await async_client.post("/api/v1/assets", json=asset1_data)
        resp2 = await async_client.post("/api/v1/assets", json=asset2_data)

        # Find path (should be empty or not found)
        response = await async_client.get(
            "/api/v1/topology/path",
            params={"source": resp1.json()["id"], "target": resp2.json()["id"]},
        )
        # Either 200 with empty path or 404
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_find_path_invalid_asset(self, async_client: AsyncClient):
        """Test finding path with invalid asset ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await async_client.get(
            "/api/v1/topology/path",
            params={"source": fake_id, "target": fake_id},
        )
        # Should return 404 or empty result
        assert response.status_code in (200, 404)


@pytest.mark.integration
class TestSubgraphAPI:
    """Test cases for Subgraph extraction API."""

    @pytest.mark.asyncio
    async def test_extract_subgraph(self, async_client: AsyncClient):
        """Test extracting subgraph for specific assets."""
        # Create assets
        assets = []
        for i in range(3):
            data = {
                "name": f"subgraph-asset-{i}",
                "asset_type": "server",
                "ip_address": f"10.10.0.{i + 1}",
            }
            resp = await async_client.post("/api/v1/assets", json=data)
            assets.append(resp.json()["id"])

        # Create dependencies
        await async_client.post("/api/v1/dependencies", json={
            "source_asset_id": assets[0],
            "target_asset_id": assets[1],
            "target_port": 80,
            "protocol": 6,
        })

        # Extract subgraph for first two assets
        response = await async_client.post(
            "/api/v1/topology/subgraph",
            json={"asset_ids": assets[:2]},
        )
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data
        assert "edges" in data

    @pytest.mark.asyncio
    async def test_extract_subgraph_empty(self, async_client: AsyncClient):
        """Test extracting subgraph with no assets."""
        response = await async_client.post(
            "/api/v1/topology/subgraph",
            json={"asset_ids": []},
        )
        # Should handle empty list gracefully
        assert response.status_code in (200, 400, 422)
