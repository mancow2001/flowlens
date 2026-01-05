"""Integration tests for discovery providers API."""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.models.discovery import DiscoveryProvider


@pytest_asyncio.fixture
async def sample_k8s_provider(test_db: AsyncSession) -> DiscoveryProvider:
    """Create a sample Kubernetes provider for testing."""
    provider = DiscoveryProvider(
        name="test-k8s-cluster",
        display_name="Test K8s Cluster",
        provider_type="kubernetes",
        api_url="https://k8s.example.com:6443",
        verify_ssl=True,
        timeout_seconds=10.0,
        is_enabled=True,
        priority=100,
        sync_interval_minutes=15,
        k8s_config={
            "cluster_name": "test-cluster",
            "namespace": "default",
            "token_encrypted": "test-token",
        },
    )
    test_db.add(provider)
    await test_db.commit()
    await test_db.refresh(provider)
    return provider


@pytest_asyncio.fixture
async def sample_vcenter_provider(test_db: AsyncSession) -> DiscoveryProvider:
    """Create a sample vCenter provider for testing."""
    provider = DiscoveryProvider(
        name="test-vcenter",
        display_name="Test vCenter",
        provider_type="vcenter",
        api_url="https://vcenter.example.com",
        username="admin@vsphere.local",
        password_encrypted="test-password",
        verify_ssl=False,
        timeout_seconds=15.0,
        is_enabled=True,
        priority=200,
        sync_interval_minutes=30,
        vcenter_config={
            "include_tags": True,
        },
    )
    test_db.add(provider)
    await test_db.commit()
    await test_db.refresh(provider)
    return provider


@pytest.mark.asyncio
class TestListDiscoveryProviders:
    """Tests for GET /api/v1/discovery-providers."""

    async def test_list_empty(self, async_client: AsyncClient) -> None:
        """Test listing providers when none exist."""
        response = await async_client.get("/api/v1/discovery-providers")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_list_providers(
        self,
        async_client: AsyncClient,
        sample_k8s_provider: DiscoveryProvider,
        sample_vcenter_provider: DiscoveryProvider,
    ) -> None:
        """Test listing all providers."""
        response = await async_client.get("/api/v1/discovery-providers")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Should be ordered by priority
        names = [p["name"] for p in data["items"]]
        assert names[0] == "test-k8s-cluster"  # priority 100
        assert names[1] == "test-vcenter"  # priority 200

    async def test_list_filter_by_type(
        self,
        async_client: AsyncClient,
        sample_k8s_provider: DiscoveryProvider,
        sample_vcenter_provider: DiscoveryProvider,
    ) -> None:
        """Test filtering by provider type."""
        response = await async_client.get(
            "/api/v1/discovery-providers?provider_type=kubernetes"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "test-k8s-cluster"

    async def test_list_filter_by_enabled(
        self,
        async_client: AsyncClient,
        sample_k8s_provider: DiscoveryProvider,
        test_db: AsyncSession,
    ) -> None:
        """Test filtering by enabled status."""
        # Disable the provider
        sample_k8s_provider.is_enabled = False
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/discovery-providers?is_enabled=false"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["is_enabled"] is False


@pytest.mark.asyncio
class TestCreateDiscoveryProvider:
    """Tests for POST /api/v1/discovery-providers."""

    async def test_create_kubernetes_provider(self, async_client: AsyncClient) -> None:
        """Test creating a Kubernetes provider."""
        response = await async_client.post(
            "/api/v1/discovery-providers",
            json={
                "name": "new-k8s",
                "display_name": "New K8s Cluster",
                "provider_type": "kubernetes",
                "api_url": "https://k8s.new.com:6443",
                "verify_ssl": True,
                "timeout_seconds": 10.0,
                "is_enabled": True,
                "priority": 50,
                "sync_interval_minutes": 10,
                "kubernetes_config": {
                    "cluster_name": "new-cluster",
                    "namespace": "kube-system",
                    "token": "secret-token",
                    "ca_cert": "-----BEGIN CERT-----",
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-k8s"
        assert data["display_name"] == "New K8s Cluster"
        assert data["provider_type"] == "kubernetes"
        assert data["api_url"] == "https://k8s.new.com:6443"
        assert data["priority"] == 50
        # Token should be masked in response
        assert data["kubernetes_config"]["token_encrypted"] == "****"

    async def test_create_vcenter_provider(self, async_client: AsyncClient) -> None:
        """Test creating a vCenter provider."""
        response = await async_client.post(
            "/api/v1/discovery-providers",
            json={
                "name": "new-vcenter",
                "provider_type": "vcenter",
                "api_url": "https://vcenter.new.com",
                "username": "admin@vsphere.local",
                "password": "secret-pass",
                "verify_ssl": False,
                "vcenter_config": {
                    "include_tags": True,
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-vcenter"
        assert data["provider_type"] == "vcenter"
        assert data["has_password"] is True
        assert data["vcenter_config"]["include_tags"] is True

    async def test_create_nutanix_provider(self, async_client: AsyncClient) -> None:
        """Test creating a Nutanix provider."""
        response = await async_client.post(
            "/api/v1/discovery-providers",
            json={
                "name": "new-nutanix",
                "provider_type": "nutanix",
                "api_url": "https://nutanix.new.com:9440",
                "username": "admin",
                "password": "nutanix-pass",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-nutanix"
        assert data["provider_type"] == "nutanix"

    async def test_create_duplicate_name(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test creating provider with duplicate name fails."""
        response = await async_client.post(
            "/api/v1/discovery-providers",
            json={
                "name": "test-k8s-cluster",  # Same as fixture
                "provider_type": "kubernetes",
                "api_url": "https://k8s.other.com:6443",
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
class TestGetDiscoveryProvider:
    """Tests for GET /api/v1/discovery-providers/{id}."""

    async def test_get_provider(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test getting a provider by ID."""
        response = await async_client.get(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_k8s_provider.id)
        assert data["name"] == "test-k8s-cluster"
        assert data["provider_type"] == "kubernetes"

    async def test_get_provider_not_found(self, async_client: AsyncClient) -> None:
        """Test getting non-existent provider."""
        response = await async_client.get(
            f"/api/v1/discovery-providers/{uuid4()}"
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestUpdateDiscoveryProvider:
    """Tests for PATCH /api/v1/discovery-providers/{id}."""

    async def test_update_provider_name(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test updating provider name."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}",
            json={"name": "renamed-k8s"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "renamed-k8s"

    async def test_update_provider_priority(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test updating provider priority."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}",
            json={"priority": 25},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == 25

    async def test_update_provider_enabled(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test disabling provider."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}",
            json={"is_enabled": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] is False

    async def test_update_kubernetes_config(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test updating Kubernetes-specific config."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}",
            json={
                "kubernetes_config": {
                    "cluster_name": "updated-cluster",
                    "namespace": "production",
                    "token": "new-token",
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["kubernetes_config"]["cluster_name"] == "updated-cluster"
        assert data["kubernetes_config"]["token_encrypted"] == "****"

    async def test_update_duplicate_name(
        self,
        async_client: AsyncClient,
        sample_k8s_provider: DiscoveryProvider,
        sample_vcenter_provider: DiscoveryProvider,
    ) -> None:
        """Test updating to duplicate name fails."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}",
            json={"name": "test-vcenter"},  # Name of other provider
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    async def test_update_not_found(self, async_client: AsyncClient) -> None:
        """Test updating non-existent provider."""
        response = await async_client.patch(
            f"/api/v1/discovery-providers/{uuid4()}",
            json={"name": "new-name"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestDeleteDiscoveryProvider:
    """Tests for DELETE /api/v1/discovery-providers/{id}."""

    async def test_delete_provider(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test deleting a provider."""
        response = await async_client.delete(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}"
        )

        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient) -> None:
        """Test deleting non-existent provider."""
        response = await async_client.delete(
            f"/api/v1/discovery-providers/{uuid4()}"
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestEnableDisableProvider:
    """Tests for POST /api/v1/discovery-providers/{id}/enable and disable."""

    async def test_enable_provider(
        self,
        async_client: AsyncClient,
        sample_k8s_provider: DiscoveryProvider,
        test_db: AsyncSession,
    ) -> None:
        """Test enabling a disabled provider."""
        # First disable it
        sample_k8s_provider.is_enabled = False
        await test_db.commit()

        response = await async_client.post(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}/enable"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] is True

    async def test_disable_provider(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test disabling a provider."""
        response = await async_client.post(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}/disable"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] is False


@pytest.mark.asyncio
class TestProviderResponseFields:
    """Tests for response field correctness."""

    async def test_has_password_field(
        self,
        async_client: AsyncClient,
        sample_vcenter_provider: DiscoveryProvider,
    ) -> None:
        """Test that has_password field reflects actual password state."""
        response = await async_client.get(
            f"/api/v1/discovery-providers/{sample_vcenter_provider.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_password"] is True
        # Actual password should NOT be in response
        assert "password_encrypted" not in data or data.get("password_encrypted") is None

    async def test_timestamps_present(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test that timestamps are present in response."""
        response = await async_client.get(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "created_at" in data
        assert "updated_at" in data
        assert data["created_at"] is not None

    async def test_status_fields(
        self, async_client: AsyncClient, sample_k8s_provider: DiscoveryProvider
    ) -> None:
        """Test that status tracking fields are present."""
        response = await async_client.get(
            f"/api/v1/discovery-providers/{sample_k8s_provider.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "last_started_at" in data
        assert "last_completed_at" in data
        assert "last_success_at" in data
        assert "last_error" in data
        assert "assets_discovered" in data
        assert "applications_discovered" in data
