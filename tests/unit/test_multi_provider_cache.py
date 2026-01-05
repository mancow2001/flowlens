"""Unit tests for multi-provider asset cache."""

from uuid import uuid4

import pytest

from flowlens.discovery.cache import (
    IPRegistryEntry,
    MultiProviderAssetCache,
    ProviderCache,
)
from flowlens.discovery.kubernetes import KubernetesAssetMetadata
from flowlens.discovery.vcenter import VCenterVMMetadata


class TestIPRegistryEntry:
    """Tests for IPRegistryEntry."""

    def test_add_provider(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")
        provider_id = uuid4()

        entry.add_provider(provider_id, priority=100)

        assert provider_id in entry.providers
        assert entry.providers[provider_id] == 100

    def test_remove_provider(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")
        provider_id = uuid4()
        entry.add_provider(provider_id, priority=100)

        entry.remove_provider(provider_id)

        assert provider_id not in entry.providers

    def test_remove_nonexistent_provider(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")

        # Should not raise
        entry.remove_provider(uuid4())

    def test_get_highest_priority_provider_empty(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")

        assert entry.get_highest_priority_provider() is None

    def test_get_highest_priority_provider_single(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")
        provider_id = uuid4()
        entry.add_provider(provider_id, priority=100)

        assert entry.get_highest_priority_provider() == provider_id

    def test_get_highest_priority_provider_multiple(self) -> None:
        entry = IPRegistryEntry(ip="10.0.0.1")
        low_priority = uuid4()  # Higher number = lower priority
        high_priority = uuid4()  # Lower number = higher priority

        entry.add_provider(low_priority, priority=200)
        entry.add_provider(high_priority, priority=50)

        assert entry.get_highest_priority_provider() == high_priority


class TestProviderCache:
    """Tests for ProviderCache."""

    def test_init(self) -> None:
        provider_id = uuid4()
        cache = ProviderCache(
            provider_id=provider_id,
            provider_type="kubernetes",
            priority=100,
        )

        assert cache.provider_id == provider_id
        assert cache.provider_type == "kubernetes"
        assert cache.priority == 100
        assert cache.updated_at is None

    def test_update(self) -> None:
        cache = ProviderCache(uuid4(), "kubernetes", 100)
        assets = [
            KubernetesAssetMetadata(
                ip="10.0.0.1",
                name="pod-1",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
            KubernetesAssetMetadata(
                ip="10.0.0.2",
                name="pod-2",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
        ]

        ips = cache.update(assets)

        assert ips == {"10.0.0.1", "10.0.0.2"}
        assert cache.updated_at is not None

    def test_get(self) -> None:
        cache = ProviderCache(uuid4(), "kubernetes", 100)
        asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update([asset])

        result = cache.get("10.0.0.1")

        assert result is not None
        assert result.ip == "10.0.0.1"
        assert result.name == "pod-1"

    def test_get_nonexistent(self) -> None:
        cache = ProviderCache(uuid4(), "kubernetes", 100)

        assert cache.get("10.0.0.1") is None

    def test_get_all_ips(self) -> None:
        cache = ProviderCache(uuid4(), "kubernetes", 100)
        assets = [
            KubernetesAssetMetadata(
                ip="10.0.0.1",
                name="pod-1",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
            KubernetesAssetMetadata(
                ip="10.0.0.2",
                name="pod-2",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
        ]
        cache.update(assets)

        assert cache.get_all_ips() == {"10.0.0.1", "10.0.0.2"}

    def test_clear(self) -> None:
        cache = ProviderCache(uuid4(), "kubernetes", 100)
        asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update([asset])

        removed_ips = cache.clear()

        assert removed_ips == {"10.0.0.1"}
        assert cache.get_all_ips() == set()
        assert cache.updated_at is None


class TestMultiProviderAssetCache:
    """Tests for MultiProviderAssetCache."""

    def test_register_provider(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()

        provider_cache = cache.register_provider(
            provider_id=provider_id,
            provider_type="kubernetes",
            priority=100,
        )

        assert provider_cache is not None
        assert provider_cache.provider_id == provider_id
        assert provider_id in cache.registered_providers

    def test_register_provider_idempotent(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()

        cache1 = cache.register_provider(provider_id, "kubernetes", 100)
        cache2 = cache.register_provider(provider_id, "kubernetes", 100)

        assert cache1 is cache2
        assert len(cache.registered_providers) == 1

    def test_unregister_provider(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)

        cache.unregister_provider(provider_id)

        assert provider_id not in cache.registered_providers
        assert cache.get_provider_cache(provider_id) is None

    def test_unregister_cleans_ip_registry(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)

        asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update_provider_cache(provider_id, [asset])

        cache.unregister_provider(provider_id)

        # IP registry should be cleaned up
        assert cache.total_ips == 0

    def test_update_provider_cache(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)

        assets = [
            KubernetesAssetMetadata(
                ip="10.0.0.1",
                name="pod-1",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
        ]
        cache.update_provider_cache(provider_id, assets)

        assert cache.total_ips == 1
        metadata, pid, ptype = cache.get_metadata_for_ip("10.0.0.1")
        assert metadata is not None
        assert pid == provider_id
        assert ptype == "kubernetes"

    def test_update_provider_cache_unregistered(self) -> None:
        cache = MultiProviderAssetCache()

        # Should not raise, just log warning
        cache.update_provider_cache(uuid4(), [])

    def test_get_metadata_for_ip_not_found(self) -> None:
        cache = MultiProviderAssetCache()

        metadata, pid, ptype = cache.get_metadata_for_ip("10.0.0.1")

        assert metadata is None
        assert pid is None
        assert ptype is None

    def test_ip_collision_resolution(self) -> None:
        cache = MultiProviderAssetCache()

        # Register two providers with different priorities
        k8s_id = uuid4()
        vcenter_id = uuid4()
        cache.register_provider(k8s_id, "kubernetes", priority=50)  # Higher priority
        cache.register_provider(vcenter_id, "vcenter", priority=100)  # Lower priority

        # Same IP in both providers
        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        vcenter_asset = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-123",
            cluster="cluster1",
        )

        cache.update_provider_cache(k8s_id, [k8s_asset])
        cache.update_provider_cache(vcenter_id, [vcenter_asset])

        # Should return kubernetes metadata (priority 50 < 100)
        metadata, pid, ptype = cache.get_metadata_for_ip("10.0.0.1")
        assert pid == k8s_id
        assert ptype == "kubernetes"
        assert metadata.name == "pod-1"

    def test_get_all_metadata_for_ip(self) -> None:
        cache = MultiProviderAssetCache()

        k8s_id = uuid4()
        vcenter_id = uuid4()
        cache.register_provider(k8s_id, "kubernetes", priority=50)
        cache.register_provider(vcenter_id, "vcenter", priority=100)

        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        vcenter_asset = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-123",
            cluster="cluster1",
        )

        cache.update_provider_cache(k8s_id, [k8s_asset])
        cache.update_provider_cache(vcenter_id, [vcenter_asset])

        results = cache.get_all_metadata_for_ip("10.0.0.1")

        assert len(results) == 2
        # Should be sorted by priority (k8s first)
        assert results[0][1] == k8s_id
        assert results[1][1] == vcenter_id

    def test_get_all_metadata_for_ip_not_found(self) -> None:
        cache = MultiProviderAssetCache()

        results = cache.get_all_metadata_for_ip("10.0.0.1")

        assert results == []

    def test_get_providers_for_ip(self) -> None:
        cache = MultiProviderAssetCache()

        k8s_id = uuid4()
        vcenter_id = uuid4()
        cache.register_provider(k8s_id, "kubernetes", priority=50)
        cache.register_provider(vcenter_id, "vcenter", priority=100)

        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        vcenter_asset = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-123",
            cluster="cluster1",
        )

        cache.update_provider_cache(k8s_id, [k8s_asset])
        cache.update_provider_cache(vcenter_id, [vcenter_asset])

        providers = cache.get_providers_for_ip("10.0.0.1")

        assert len(providers) == 2
        assert providers[0] == (k8s_id, "kubernetes", 50)
        assert providers[1] == (vcenter_id, "vcenter", 100)

    def test_update_provider_priority(self) -> None:
        cache = MultiProviderAssetCache()

        k8s_id = uuid4()
        vcenter_id = uuid4()
        cache.register_provider(k8s_id, "kubernetes", priority=50)
        cache.register_provider(vcenter_id, "vcenter", priority=100)

        k8s_asset = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        vcenter_asset = VCenterVMMetadata(
            ip="10.0.0.1",
            name="vm-1",
            vm_id="vm-123",
            cluster="cluster1",
        )

        cache.update_provider_cache(k8s_id, [k8s_asset])
        cache.update_provider_cache(vcenter_id, [vcenter_asset])

        # Change k8s priority to be lower than vcenter
        cache.update_provider_priority(k8s_id, new_priority=200)

        # Now vcenter should be highest priority
        metadata, pid, ptype = cache.get_metadata_for_ip("10.0.0.1")
        assert pid == vcenter_id
        assert ptype == "vcenter"

    def test_cache_replacement(self) -> None:
        cache = MultiProviderAssetCache()
        provider_id = uuid4()
        cache.register_provider(provider_id, "kubernetes", 100)

        # First update
        asset1 = KubernetesAssetMetadata(
            ip="10.0.0.1",
            name="pod-1",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update_provider_cache(provider_id, [asset1])
        assert cache.total_ips == 1

        # Second update with different IP
        asset2 = KubernetesAssetMetadata(
            ip="10.0.0.2",
            name="pod-2",
            namespace="default",
            kind="pod",
            cluster="test",
        )
        cache.update_provider_cache(provider_id, [asset2])

        # Old IP should be gone, new IP should be there
        assert cache.total_ips == 1
        assert cache.get_metadata_for_ip("10.0.0.1")[0] is None
        assert cache.get_metadata_for_ip("10.0.0.2")[0] is not None

    def test_get_stats(self) -> None:
        cache = MultiProviderAssetCache()

        k8s_id = uuid4()
        vcenter_id = uuid4()
        cache.register_provider(k8s_id, "kubernetes", priority=50)
        cache.register_provider(vcenter_id, "vcenter", priority=100)

        # Add assets with one collision
        k8s_assets = [
            KubernetesAssetMetadata(
                ip="10.0.0.1",
                name="pod-1",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
            KubernetesAssetMetadata(
                ip="10.0.0.2",
                name="pod-2",
                namespace="default",
                kind="pod",
                cluster="test",
            ),
        ]
        vcenter_assets = [
            VCenterVMMetadata(
                ip="10.0.0.1",  # Collision with k8s
                name="vm-1",
                vm_id="vm-123",
                cluster="cluster1",
            ),
        ]

        cache.update_provider_cache(k8s_id, k8s_assets)
        cache.update_provider_cache(vcenter_id, vcenter_assets)

        stats = cache.get_stats()

        assert stats["registered_providers"] == 2
        assert stats["total_unique_ips"] == 2  # 10.0.0.1 and 10.0.0.2
        assert stats["ips_with_collisions"] == 1  # Only 10.0.0.1
