"""Unified multi-provider asset enricher.

Handles enrichment from all discovery provider types with
priority-based IP collision resolution.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.discovery.cache import (
    AssetMetadata,
    MultiProviderAssetCache,
    get_multi_provider_cache,
)
from flowlens.discovery.kubernetes import KubernetesAssetMetadata
from flowlens.discovery.nutanix import NutanixVMMetadata
from flowlens.discovery.vcenter import VCenterVMMetadata
from flowlens.models.asset import Asset, AssetType

logger = get_logger(__name__)


class MultiProviderAssetEnricher:
    """Apply cached metadata from any discovery provider to assets.

    Uses priority-based resolution when an IP exists in multiple providers.
    All provider metadata is stored in extra_data under separate keys.
    """

    def __init__(self, cache: MultiProviderAssetCache | None = None) -> None:
        self._cache = cache or get_multi_provider_cache()

    def _enrich_from_kubernetes(
        self,
        asset: Asset,
        metadata: KubernetesAssetMetadata,
        provider_id: UUID,
        is_primary: bool,
    ) -> None:
        """Apply Kubernetes metadata to an asset."""
        k8s_metadata = {
            "provider_id": str(provider_id),
            "cluster": metadata.cluster,
            "namespace": metadata.namespace,
            "name": metadata.name,
            "kind": metadata.kind,
            "labels": metadata.labels,
        }

        # Store in extra_data under kubernetes key
        extra_data = dict(asset.extra_data or {})
        if "kubernetes" not in extra_data:
            extra_data["kubernetes"] = {}

        # Store under the provider name for multi-cluster support
        provider_key = f"cluster_{metadata.cluster}"
        extra_data["kubernetes"][provider_key] = k8s_metadata
        asset.extra_data = extra_data

        # Only update primary fields if this is the highest-priority provider
        if is_primary:
            tags = dict(asset.tags or {})
            tags["kubernetes_cluster"] = metadata.cluster
            tags["kubernetes_namespace"] = metadata.namespace
            asset.tags = tags

            # Track all discovery sources
            discovered_by = tags.get("discovered_by", [])
            if isinstance(discovered_by, str):
                discovered_by = [discovered_by]
            source = f"kubernetes:{metadata.cluster}"
            if source not in discovered_by:
                discovered_by.append(source)
            tags["discovered_by"] = discovered_by
            asset.tags = tags

            # Set asset type if unknown
            if asset.asset_type == AssetType.UNKNOWN.value:
                if metadata.kind == "service":
                    asset.asset_type = AssetType.LOAD_BALANCER.value
                else:
                    asset.asset_type = AssetType.CONTAINER.value

            # Set display name if not set
            if not asset.display_name:
                asset.display_name = metadata.name

            # Set discovered_by_provider_id
            asset.discovered_by_provider_id = provider_id

    def _enrich_from_vcenter(
        self,
        asset: Asset,
        metadata: VCenterVMMetadata,
        provider_id: UUID,
        is_primary: bool,
    ) -> None:
        """Apply vCenter metadata to an asset."""
        vcenter_metadata = {
            "provider_id": str(provider_id),
            "vm_id": metadata.vm_id,
            "cluster": metadata.cluster,
            "networks": metadata.networks,
            "tags": metadata.tags,
            "power_state": metadata.power_state,
        }

        # Store in extra_data under vcenter key
        extra_data = dict(asset.extra_data or {})
        if "vcenter" not in extra_data:
            extra_data["vcenter"] = {}

        # Store under the cluster name for multi-vcenter support
        provider_key = f"cluster_{metadata.cluster}" if metadata.cluster else str(provider_id)[:8]
        extra_data["vcenter"][provider_key] = vcenter_metadata
        asset.extra_data = extra_data

        # Only update primary fields if this is the highest-priority provider
        if is_primary:
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["vcenter_cluster"] = metadata.cluster
            if metadata.networks:
                tags["vcenter_networks"] = metadata.networks
            if metadata.tags:
                tags["vcenter_tags"] = metadata.tags

            # Track all discovery sources
            discovered_by = tags.get("discovered_by", [])
            if isinstance(discovered_by, str):
                discovered_by = [discovered_by]
            source = f"vcenter:{metadata.cluster or 'unknown'}"
            if source not in discovered_by:
                discovered_by.append(source)
            tags["discovered_by"] = discovered_by
            asset.tags = tags

            # Set asset type if unknown
            if asset.asset_type == AssetType.UNKNOWN.value:
                asset.asset_type = AssetType.VIRTUAL_MACHINE.value

            # Set display name if not set
            if not asset.display_name:
                asset.display_name = metadata.name

            # Set discovered_by_provider_id
            asset.discovered_by_provider_id = provider_id

    def _enrich_from_nutanix(
        self,
        asset: Asset,
        metadata: NutanixVMMetadata,
        provider_id: UUID,
        is_primary: bool,
    ) -> None:
        """Apply Nutanix metadata to an asset."""
        nutanix_metadata = {
            "provider_id": str(provider_id),
            "vm_id": metadata.vm_id,
            "cluster": metadata.cluster,
            "subnets": metadata.subnets,
            "categories": metadata.categories,
            "power_state": metadata.power_state,
        }

        # Store in extra_data under nutanix key
        extra_data = dict(asset.extra_data or {})
        if "nutanix" not in extra_data:
            extra_data["nutanix"] = {}

        # Store under the cluster name for multi-nutanix support
        provider_key = f"cluster_{metadata.cluster}" if metadata.cluster else str(provider_id)[:8]
        extra_data["nutanix"][provider_key] = nutanix_metadata
        asset.extra_data = extra_data

        # Only update primary fields if this is the highest-priority provider
        if is_primary:
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["nutanix_cluster"] = metadata.cluster
            if metadata.subnets:
                tags["nutanix_subnets"] = metadata.subnets
            if metadata.categories:
                tags["nutanix_categories"] = metadata.categories

            # Track all discovery sources
            discovered_by = tags.get("discovered_by", [])
            if isinstance(discovered_by, str):
                discovered_by = [discovered_by]
            source = f"nutanix:{metadata.cluster or 'unknown'}"
            if source not in discovered_by:
                discovered_by.append(source)
            tags["discovered_by"] = discovered_by
            asset.tags = tags

            # Set asset type if unknown
            if asset.asset_type == AssetType.UNKNOWN.value:
                asset.asset_type = AssetType.VIRTUAL_MACHINE.value

            # Set display name if not set
            if not asset.display_name:
                asset.display_name = metadata.name

            # Set discovered_by_provider_id
            asset.discovered_by_provider_id = provider_id

    def _apply_metadata(
        self,
        asset: Asset,
        metadata: AssetMetadata,
        provider_id: UUID,
        provider_type: str,
        is_primary: bool,
    ) -> None:
        """Apply metadata based on provider type."""
        if provider_type == "kubernetes" and isinstance(metadata, KubernetesAssetMetadata):
            self._enrich_from_kubernetes(asset, metadata, provider_id, is_primary)
        elif provider_type == "vcenter" and isinstance(metadata, VCenterVMMetadata):
            self._enrich_from_vcenter(asset, metadata, provider_id, is_primary)
        elif provider_type == "nutanix" and isinstance(metadata, NutanixVMMetadata):
            self._enrich_from_nutanix(asset, metadata, provider_id, is_primary)
        else:
            logger.warning(
                "Unknown provider type or metadata mismatch",
                provider_type=provider_type,
                metadata_type=type(metadata).__name__,
            )

    async def enrich_asset(
        self,
        db: AsyncSession,
        asset_id: UUID,
        ip_address: str,
    ) -> None:
        """Enrich an asset with metadata from all providers claiming this IP.

        The highest-priority provider's metadata is used for primary fields
        (display_name, asset_type, tags). All provider metadata is stored
        in extra_data.
        """
        # Get all metadata for this IP
        all_metadata = self._cache.get_all_metadata_for_ip(ip_address)
        if not all_metadata:
            return

        # Fetch the asset
        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            return

        # Apply metadata from all providers, marking first one as primary
        for idx, (metadata, provider_id, provider_type) in enumerate(all_metadata):
            is_primary = idx == 0  # First entry is highest priority
            self._apply_metadata(asset, metadata, provider_id, provider_type, is_primary)

    async def enrich_assets(
        self,
        db: AsyncSession,
        src_asset_id: UUID,
        dst_asset_id: UUID,
        src_ip: str,
        dst_ip: str,
    ) -> None:
        """Enrich both source and destination assets."""
        await self.enrich_asset(db, src_asset_id, src_ip)
        await self.enrich_asset(db, dst_asset_id, dst_ip)


# Singleton instance
_multi_provider_enricher: MultiProviderAssetEnricher | None = None


def get_multi_provider_enricher() -> MultiProviderAssetEnricher:
    """Get the singleton multi-provider enricher."""
    global _multi_provider_enricher
    if _multi_provider_enricher is None:
        _multi_provider_enricher = MultiProviderAssetEnricher()
    return _multi_provider_enricher
