"""Unit tests for multi-provider asset enricher."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from flowlens.discovery.cache import MultiProviderAssetCache
from flowlens.discovery.enricher import MultiProviderAssetEnricher
from flowlens.discovery.kubernetes import KubernetesAssetMetadata
from flowlens.discovery.nutanix import NutanixVMMetadata
from flowlens.discovery.vcenter import VCenterVMMetadata
from flowlens.models.asset import AssetType


class MockAsset:
    """Mock Asset for testing enrichment logic."""

    def __init__(
        self,
        asset_id=None,
        asset_type=AssetType.UNKNOWN.value,
        display_name=None,
        tags=None,
        extra_data=None,
        discovered_by_provider_id=None,
    ):
        self.id = asset_id or uuid4()
        self.asset_type = asset_type
        self.display_name = display_name
        self.tags = tags or {}
        self.extra_data = extra_data or {}
        self.discovered_by_provider_id = discovered_by_provider_id


class TestMultiProviderAssetEnricherKubernetes:
    """Tests for Kubernetes enrichment."""

    def test_enrich_from_kubernetes_primary(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        provider_id = uuid4()
        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="api-pod-abc123",
            namespace="production",
            kind="pod",
            cluster="prod-cluster",
            labels={"app": "api", "version": "v1"},
        )
        asset = MockAsset()

        enricher._enrich_from_kubernetes(asset, metadata, provider_id, is_primary=True)

        # Check extra_data
        assert "kubernetes" in asset.extra_data
        assert "cluster_prod-cluster" in asset.extra_data["kubernetes"]
        k8s_data = asset.extra_data["kubernetes"]["cluster_prod-cluster"]
        assert k8s_data["name"] == "api-pod-abc123"
        assert k8s_data["namespace"] == "production"
        assert k8s_data["kind"] == "pod"
        assert k8s_data["labels"] == {"app": "api", "version": "v1"}

        # Check primary fields (is_primary=True)
        assert asset.tags["kubernetes_cluster"] == "prod-cluster"
        assert asset.tags["kubernetes_namespace"] == "production"
        assert "kubernetes:prod-cluster" in asset.tags["discovered_by"]
        assert asset.asset_type == AssetType.CONTAINER.value
        assert asset.display_name == "api-pod-abc123"
        assert asset.discovered_by_provider_id == provider_id

    def test_enrich_from_kubernetes_not_primary(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        provider_id = uuid4()
        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="api-pod",
            namespace="default",
            kind="pod",
            cluster="secondary",
        )
        asset = MockAsset(
            asset_type=AssetType.VIRTUAL_MACHINE.value,
            display_name="existing-name",
            tags={"existing": "tag"},
        )

        enricher._enrich_from_kubernetes(asset, metadata, provider_id, is_primary=False)

        # Check extra_data is still populated
        assert "kubernetes" in asset.extra_data
        assert "cluster_secondary" in asset.extra_data["kubernetes"]

        # Primary fields should NOT be changed
        assert asset.asset_type == AssetType.VIRTUAL_MACHINE.value
        assert asset.display_name == "existing-name"
        assert "kubernetes_cluster" not in asset.tags
        assert asset.discovered_by_provider_id is None

    def test_enrich_from_kubernetes_service_type(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="api-service",
            namespace="default",
            kind="service",
            cluster="prod",
        )
        asset = MockAsset()

        enricher._enrich_from_kubernetes(asset, metadata, uuid4(), is_primary=True)

        # Services should be typed as load balancer
        assert asset.asset_type == AssetType.LOAD_BALANCER.value


class TestMultiProviderAssetEnricherVCenter:
    """Tests for vCenter enrichment."""

    def test_enrich_from_vcenter_primary(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        provider_id = uuid4()
        metadata = VCenterVMMetadata(
            ip="10.0.0.1",
            name="web-server-01",
            vm_id="vm-123",
            cluster="prod-cluster",
            networks=["vlan-100", "vlan-200"],
            tags=["production", "web"],
            power_state="poweredOn",
        )
        asset = MockAsset()

        enricher._enrich_from_vcenter(asset, metadata, provider_id, is_primary=True)

        # Check extra_data
        assert "vcenter" in asset.extra_data
        assert "cluster_prod-cluster" in asset.extra_data["vcenter"]
        vcenter_data = asset.extra_data["vcenter"]["cluster_prod-cluster"]
        assert vcenter_data["vm_id"] == "vm-123"
        assert vcenter_data["power_state"] == "poweredOn"
        assert vcenter_data["networks"] == ["vlan-100", "vlan-200"]

        # Check primary fields
        assert asset.tags["vcenter_cluster"] == "prod-cluster"
        assert asset.tags["vcenter_networks"] == ["vlan-100", "vlan-200"]
        assert asset.tags["vcenter_tags"] == ["production", "web"]
        assert "vcenter:prod-cluster" in asset.tags["discovered_by"]
        assert asset.asset_type == AssetType.VIRTUAL_MACHINE.value
        assert asset.display_name == "web-server-01"
        assert asset.discovered_by_provider_id == provider_id

    def test_enrich_from_vcenter_not_primary(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-456",
            cluster="cluster1",
        )
        asset = MockAsset(
            asset_type=AssetType.CONTAINER.value,
            display_name="k8s-pod",
        )

        enricher._enrich_from_vcenter(asset, metadata, uuid4(), is_primary=False)

        # Extra data should be populated
        assert "vcenter" in asset.extra_data

        # Primary fields should NOT change
        assert asset.asset_type == AssetType.CONTAINER.value
        assert asset.display_name == "k8s-pod"


class TestMultiProviderAssetEnricherNutanix:
    """Tests for Nutanix enrichment."""

    def test_enrich_from_nutanix_primary(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        provider_id = uuid4()
        metadata = NutanixVMMetadata(
            ip="10.0.0.1",
            name="db-server-01",
            vm_id="vm-456",
            cluster="nutanix-prod",
            subnets=["db-network"],
            categories={"Environment": "Production", "App": "Database"},
            power_state="on",
        )
        asset = MockAsset()

        enricher._enrich_from_nutanix(asset, metadata, provider_id, is_primary=True)

        # Check extra_data
        assert "nutanix" in asset.extra_data
        assert "cluster_nutanix-prod" in asset.extra_data["nutanix"]
        nutanix_data = asset.extra_data["nutanix"]["cluster_nutanix-prod"]
        assert nutanix_data["vm_id"] == "vm-456"
        assert nutanix_data["subnets"] == ["db-network"]
        assert nutanix_data["categories"] == {"Environment": "Production", "App": "Database"}

        # Check primary fields
        assert asset.tags["nutanix_cluster"] == "nutanix-prod"
        assert asset.tags["nutanix_subnets"] == ["db-network"]
        assert "nutanix:nutanix-prod" in asset.tags["discovered_by"]
        assert asset.asset_type == AssetType.VIRTUAL_MACHINE.value
        assert asset.display_name == "db-server-01"
        assert asset.discovered_by_provider_id == provider_id


class TestMultiProviderAssetEnricherIntegration:
    """Integration tests for multi-provider enrichment."""

    def test_apply_metadata_kubernetes(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        asset = MockAsset()

        enricher._apply_metadata(asset, metadata, uuid4(), "kubernetes", is_primary=True)

        assert "kubernetes" in asset.extra_data

    def test_apply_metadata_vcenter(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-789",
            cluster="cluster1",
        )
        asset = MockAsset()

        enricher._apply_metadata(asset, metadata, uuid4(), "vcenter", is_primary=True)

        assert "vcenter" in asset.extra_data

    def test_apply_metadata_nutanix(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = NutanixVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-999",
            cluster="cluster1",
        )
        asset = MockAsset()

        enricher._apply_metadata(asset, metadata, uuid4(), "nutanix", is_primary=True)

        assert "nutanix" in asset.extra_data

    def test_apply_metadata_unknown_provider(self) -> None:
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        asset = MockAsset()

        # Should not raise, just log warning
        enricher._apply_metadata(asset, metadata, uuid4(), "unknown_provider", is_primary=True)

        # No enrichment should happen for unknown provider
        assert asset.extra_data == {}

    def test_multiple_providers_same_ip(self) -> None:
        """Test that all providers' metadata is stored in extra_data."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        k8s_metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="k8s-cluster",
        )
        vcenter_metadata = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-111",
            cluster="vcenter-cluster",
        )

        asset = MockAsset()

        # Apply k8s first as primary
        enricher._apply_metadata(asset, k8s_metadata, uuid4(), "kubernetes", is_primary=True)
        # Then vcenter as non-primary
        enricher._apply_metadata(asset, vcenter_metadata, uuid4(), "vcenter", is_primary=False)

        # Both should be in extra_data
        assert "kubernetes" in asset.extra_data
        assert "vcenter" in asset.extra_data

        # Primary fields should be from kubernetes
        assert asset.asset_type == AssetType.CONTAINER.value
        assert asset.display_name == "pod-1"
        assert "kubernetes:k8s-cluster" in asset.tags["discovered_by"]

    def test_discovered_by_list_accumulation(self) -> None:
        """Test that discovered_by tag accumulates sources."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        k8s_metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="cluster-a",
        )
        k8s_metadata_2 = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="cluster-b",
        )

        asset = MockAsset()

        # Both are primary in this test (simulating two k8s clusters)
        enricher._apply_metadata(asset, k8s_metadata, uuid4(), "kubernetes", is_primary=True)
        enricher._apply_metadata(asset, k8s_metadata_2, uuid4(), "kubernetes", is_primary=True)

        discovered_by = asset.tags.get("discovered_by", [])
        assert "kubernetes:cluster-a" in discovered_by
        assert "kubernetes:cluster-b" in discovered_by

    def test_no_duplicate_discovered_by(self) -> None:
        """Test that discovered_by doesn't add duplicates."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        metadata = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="prod",
        )
        asset = MockAsset()

        # Apply same metadata twice
        enricher._apply_metadata(asset, metadata, uuid4(), "kubernetes", is_primary=True)
        enricher._apply_metadata(asset, metadata, uuid4(), "kubernetes", is_primary=True)

        discovered_by = asset.tags.get("discovered_by", [])
        assert discovered_by.count("kubernetes:prod") == 1


@pytest.mark.asyncio
class TestMultiProviderAssetEnricherAsync:
    """Async tests for enricher methods that interact with database."""

    async def test_enrich_asset_no_metadata(self) -> None:
        """Test enrichment when no metadata exists for IP."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        db = AsyncMock()

        await enricher.enrich_asset(db, uuid4(), "10.0.0.1")

        # No DB call should be made if no metadata in cache
        db.execute.assert_not_called()

    async def test_enrich_asset_with_metadata(self) -> None:
        """Test enrichment with metadata in cache."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        # Register provider and add metadata
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)
        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update_provider_cache(provider_id, [k8s_asset])

        # Mock database
        asset_id = uuid4()
        mock_asset = MockAsset(asset_id=asset_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_asset

        db = AsyncMock()
        db.execute.return_value = mock_result

        await enricher.enrich_asset(db, asset_id, "10.0.0.1")

        # Verify DB was called
        db.execute.assert_called_once()

        # Verify asset was enriched
        assert "kubernetes" in mock_asset.extra_data

    async def test_enrich_asset_not_found(self) -> None:
        """Test enrichment when asset not found in DB."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        # Register provider and add metadata
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)
        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update_provider_cache(provider_id, [k8s_asset])

        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        # Should not raise
        await enricher.enrich_asset(db, uuid4(), "10.0.0.1")

    async def test_enrich_assets_both(self) -> None:
        """Test enriching both source and destination assets."""
        cache = MultiProviderAssetCache()
        enricher = MultiProviderAssetEnricher(cache=cache)

        # Register provider and add metadata for both IPs
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)
        assets = [
            KubernetesAssetMetadata(
                ip="10.0.0.1",
                name="src-pod",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
            KubernetesAssetMetadata(
                ip="10.0.0.2",
                name="dst-pod",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
        ]
        cache.update_provider_cache(provider_id, assets)

        # Mock database
        src_id = uuid4()
        dst_id = uuid4()
        src_asset = MockAsset(asset_id=src_id)
        dst_asset = MockAsset(asset_id=dst_id)

        def get_asset(query):
            result = MagicMock()
            # Simple matching based on call count
            if db.execute.call_count == 1:
                result.scalar_one_or_none.return_value = src_asset
            else:
                result.scalar_one_or_none.return_value = dst_asset
            return result

        db = AsyncMock()
        db.execute.side_effect = get_asset

        await enricher.enrich_assets(db, src_id, dst_id, "10.0.0.1", "10.0.0.2")

        # Both assets should be enriched
        assert db.execute.call_count == 2
        assert "kubernetes" in src_asset.extra_data
        assert "kubernetes" in dst_asset.extra_data
