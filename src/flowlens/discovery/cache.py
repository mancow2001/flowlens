"""Multi-provider asset cache for discovery integration.

Maintains separate caches per provider instance and an IP registry
for resolving collisions when the same IP exists in multiple providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Union
from uuid import UUID

from flowlens.common.logging import get_logger
from flowlens.discovery.kubernetes import KubernetesAssetMetadata
from flowlens.discovery.nutanix import NutanixVMMetadata
from flowlens.discovery.vcenter import VCenterVMMetadata

logger = get_logger(__name__)

# Type alias for all provider metadata types
AssetMetadata = Union[KubernetesAssetMetadata, VCenterVMMetadata, NutanixVMMetadata]


@dataclass
class IPRegistryEntry:
    """Tracks which providers claim a specific IP address."""

    ip: str
    providers: dict[UUID, int] = field(default_factory=dict)  # provider_id -> priority

    def add_provider(self, provider_id: UUID, priority: int) -> None:
        """Register a provider for this IP."""
        self.providers[provider_id] = priority

    def remove_provider(self, provider_id: UUID) -> None:
        """Remove a provider from this IP."""
        self.providers.pop(provider_id, None)

    def get_highest_priority_provider(self) -> UUID | None:
        """Get the provider with highest priority (lowest number)."""
        if not self.providers:
            return None
        return min(self.providers, key=lambda p: self.providers[p])


class ProviderCache:
    """Cache for a single provider instance."""

    def __init__(self, provider_id: UUID, provider_type: str, priority: int) -> None:
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.priority = priority
        self._assets_by_ip: dict[str, AssetMetadata] = {}
        self._updated_at: datetime | None = None

    def update(self, assets: list[AssetMetadata]) -> set[str]:
        """Update cache with new assets, returns set of IPs."""
        self._assets_by_ip = {asset.ip: asset for asset in assets}
        self._updated_at = datetime.now(timezone.utc)
        return set(self._assets_by_ip.keys())

    def get(self, ip: str) -> AssetMetadata | None:
        """Get metadata for an IP address."""
        return self._assets_by_ip.get(ip)

    def get_all_ips(self) -> set[str]:
        """Get all IPs in this cache."""
        return set(self._assets_by_ip.keys())

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    def clear(self) -> set[str]:
        """Clear the cache, returns set of IPs that were removed."""
        ips = set(self._assets_by_ip.keys())
        self._assets_by_ip.clear()
        self._updated_at = None
        return ips


class MultiProviderAssetCache:
    """Registry of provider caches with IP collision resolution.

    Maintains separate caches per provider instance and tracks which
    IPs are claimed by which providers for priority-based resolution.
    """

    def __init__(self) -> None:
        self._provider_caches: dict[UUID, ProviderCache] = {}
        self._ip_registry: dict[str, IPRegistryEntry] = {}

    def register_provider(self, provider_id: UUID, provider_type: str, priority: int) -> ProviderCache:
        """Register a provider and return its cache."""
        if provider_id not in self._provider_caches:
            self._provider_caches[provider_id] = ProviderCache(
                provider_id=provider_id,
                provider_type=provider_type,
                priority=priority,
            )
            logger.info(
                "Registered provider cache",
                provider_id=str(provider_id),
                provider_type=provider_type,
                priority=priority,
            )
        return self._provider_caches[provider_id]

    def unregister_provider(self, provider_id: UUID) -> None:
        """Unregister a provider and clean up its IP registrations."""
        cache = self._provider_caches.pop(provider_id, None)
        if cache:
            # Remove this provider from all IP registry entries
            for ip in cache.get_all_ips():
                if ip in self._ip_registry:
                    self._ip_registry[ip].remove_provider(provider_id)
                    if not self._ip_registry[ip].providers:
                        del self._ip_registry[ip]
            logger.info(
                "Unregistered provider cache",
                provider_id=str(provider_id),
            )

    def get_provider_cache(self, provider_id: UUID) -> ProviderCache | None:
        """Get the cache for a specific provider."""
        return self._provider_caches.get(provider_id)

    def update_provider_cache(
        self,
        provider_id: UUID,
        assets: list[AssetMetadata],
    ) -> None:
        """Update a provider's cache and refresh IP registry."""
        cache = self._provider_caches.get(provider_id)
        if not cache:
            logger.warning(
                "Attempted to update unregistered provider cache",
                provider_id=str(provider_id),
            )
            return

        # Remove old IP registrations
        old_ips = cache.get_all_ips()
        for ip in old_ips:
            if ip in self._ip_registry:
                self._ip_registry[ip].remove_provider(provider_id)
                if not self._ip_registry[ip].providers:
                    del self._ip_registry[ip]

        # Update cache and register new IPs
        new_ips = cache.update(assets)
        for ip in new_ips:
            if ip not in self._ip_registry:
                self._ip_registry[ip] = IPRegistryEntry(ip=ip)
            self._ip_registry[ip].add_provider(provider_id, cache.priority)

        logger.debug(
            "Updated provider cache",
            provider_id=str(provider_id),
            old_ip_count=len(old_ips),
            new_ip_count=len(new_ips),
        )

    def get_metadata_for_ip(self, ip: str) -> tuple[AssetMetadata | None, UUID | None, str | None]:
        """Get the highest-priority metadata for an IP.

        Returns:
            Tuple of (metadata, provider_id, provider_type) or (None, None, None)
        """
        registry_entry = self._ip_registry.get(ip)
        if not registry_entry:
            return None, None, None

        provider_id = registry_entry.get_highest_priority_provider()
        if not provider_id:
            return None, None, None

        cache = self._provider_caches.get(provider_id)
        if not cache:
            return None, None, None

        metadata = cache.get(ip)
        return metadata, provider_id, cache.provider_type

    def get_all_metadata_for_ip(self, ip: str) -> list[tuple[AssetMetadata, UUID, str]]:
        """Get metadata from all providers that claim this IP.

        Returns:
            List of (metadata, provider_id, provider_type) tuples, sorted by priority
        """
        registry_entry = self._ip_registry.get(ip)
        if not registry_entry:
            return []

        results = []
        for provider_id, priority in registry_entry.providers.items():
            cache = self._provider_caches.get(provider_id)
            if cache:
                metadata = cache.get(ip)
                if metadata:
                    results.append((metadata, provider_id, cache.provider_type, priority))

        # Sort by priority (lowest number = highest priority)
        results.sort(key=lambda x: x[3])
        return [(m, p, t) for m, p, t, _ in results]

    def get_providers_for_ip(self, ip: str) -> list[tuple[UUID, str, int]]:
        """Get all providers that claim this IP.

        Returns:
            List of (provider_id, provider_type, priority) tuples, sorted by priority
        """
        registry_entry = self._ip_registry.get(ip)
        if not registry_entry:
            return []

        results = []
        for provider_id, priority in registry_entry.providers.items():
            cache = self._provider_caches.get(provider_id)
            if cache:
                results.append((provider_id, cache.provider_type, priority))

        # Sort by priority
        results.sort(key=lambda x: x[2])
        return results

    def update_provider_priority(self, provider_id: UUID, new_priority: int) -> None:
        """Update a provider's priority and refresh IP registry."""
        cache = self._provider_caches.get(provider_id)
        if not cache:
            return

        old_priority = cache.priority
        cache.priority = new_priority

        # Update all IP registry entries for this provider
        for ip in cache.get_all_ips():
            if ip in self._ip_registry:
                self._ip_registry[ip].providers[provider_id] = new_priority

        logger.info(
            "Updated provider priority",
            provider_id=str(provider_id),
            old_priority=old_priority,
            new_priority=new_priority,
        )

    @property
    def registered_providers(self) -> list[UUID]:
        """Get list of all registered provider IDs."""
        return list(self._provider_caches.keys())

    @property
    def total_ips(self) -> int:
        """Get total number of unique IPs in the registry."""
        return len(self._ip_registry)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the cache."""
        return {
            "registered_providers": len(self._provider_caches),
            "total_unique_ips": len(self._ip_registry),
            "ips_with_collisions": sum(
                1 for entry in self._ip_registry.values()
                if len(entry.providers) > 1
            ),
            "providers": {
                str(pid): {
                    "type": cache.provider_type,
                    "priority": cache.priority,
                    "ip_count": len(cache.get_all_ips()),
                    "updated_at": cache.updated_at.isoformat() if cache.updated_at else None,
                }
                for pid, cache in self._provider_caches.items()
            },
        }


# Singleton instance
_multi_provider_cache = MultiProviderAssetCache()


def get_multi_provider_cache() -> MultiProviderAssetCache:
    """Get the singleton multi-provider asset cache."""
    return _multi_provider_cache
