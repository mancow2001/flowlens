"""Nutanix Prism discovery integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import NutanixSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset, AssetType
from flowlens.models.discovery import DiscoveryProvider, DiscoveryStatus
from flowlens.resolution.asset_mapper import AssetMapper

if TYPE_CHECKING:
    from flowlens.discovery.cache import MultiProviderAssetCache

logger = get_logger(__name__)

NUTANIX_PROVIDER = "nutanix"


@dataclass(frozen=True)
class NutanixVMMetadata:
    """Metadata representing a Nutanix VM."""

    ip: str
    name: str
    vm_id: str
    cluster: str | None = None
    subnets: list[str] = field(default_factory=list)
    categories: dict[str, str] = field(default_factory=dict)
    power_state: str | None = None


@dataclass
class NutanixApplicationMapping:
    """Represents an application grouping derived from clusters."""

    name: str
    display_name: str
    cluster: str
    asset_ips: list[str]


@dataclass(frozen=True)
class NutanixSnapshot:
    """Snapshot of Nutanix objects relevant to discovery."""

    vms: list[dict[str, Any]]
    clusters: list[dict[str, Any]]
    subnets: list[dict[str, Any]]

    def _cluster_names(self) -> dict[str, str]:
        return {cluster.get("metadata", {}).get("uuid"): cluster.get("spec", {}).get("name") for cluster in self.clusters}

    def _subnet_names(self) -> dict[str, str]:
        return {subnet.get("metadata", {}).get("uuid"): subnet.get("spec", {}).get("name") for subnet in self.subnets}

    def build_asset_metadata(self) -> list[NutanixVMMetadata]:
        """Build asset metadata list from Nutanix VMs."""
        cluster_names = self._cluster_names()
        subnet_names = self._subnet_names()
        assets: list[NutanixVMMetadata] = []

        for vm in self.vms:
            metadata = vm.get("metadata", {})
            spec = vm.get("spec", {})
            status = vm.get("status", {})
            vm_id = metadata.get("uuid") or metadata.get("name") or "unknown"
            name = spec.get("name") or metadata.get("name") or vm_id
            cluster_name = cluster_names.get(status.get("cluster_reference", {}).get("uuid"))
            categories = metadata.get("categories") or {}
            power_state = status.get("resources", {}).get("power_state")

            ip_addresses = []
            for nic in status.get("resources", {}).get("nic_list", []) or []:
                for endpoint in nic.get("ip_endpoint_list", []) or []:
                    ip = endpoint.get("ip")
                    if ip:
                        ip_addresses.append(ip)

            subnets = [
                subnet_names.get(nic.get("subnet_reference", {}).get("uuid"))
                for nic in status.get("resources", {}).get("nic_list", []) or []
            ]
            subnets = [subnet for subnet in subnets if subnet]

            for ip in ip_addresses:
                assets.append(
                    NutanixVMMetadata(
                        ip=ip,
                        name=name,
                        vm_id=vm_id,
                        cluster=cluster_name,
                        subnets=subnets,
                        categories=categories,
                        power_state=power_state,
                    )
                )
        return assets

    def build_application_mappings(self) -> list[NutanixApplicationMapping]:
        """Build application groupings from clusters."""
        clusters_by_name = {cluster.get("spec", {}).get("name") for cluster in self.clusters if cluster.get("spec", {}).get("name")}
        cluster_ips: dict[str, list[str]] = {name: [] for name in clusters_by_name}
        for asset in self.build_asset_metadata():
            if asset.cluster:
                cluster_ips.setdefault(asset.cluster, []).append(asset.ip)
        mappings = []
        for cluster_name, ips in cluster_ips.items():
            if not ips:
                continue
            app_name = f"nutanix:{cluster_name}"
            mappings.append(
                NutanixApplicationMapping(
                    name=app_name,
                    display_name=cluster_name,
                    cluster=cluster_name,
                    asset_ips=list(sorted(set(ips))),
                )
            )
        return mappings


class NutanixDiscoveryClient:
    """Lightweight Nutanix Prism API client."""

    def __init__(self, settings: NutanixSettings | None = None) -> None:
        self._settings = settings or get_settings().nutanix

    def _base_url(self) -> str:
        return self._settings.api_url.rstrip("/")

    def _auth(self) -> tuple[str, str] | None:
        if self._settings.username and self._settings.password:
            return (self._settings.username, self._settings.password.get_secret_value())
        return None

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._settings.timeout_seconds)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            verify=self._settings.verify_ssl,
            timeout=self._timeout(),
        ) as client:
            response = await client.post(
                f"{self._base_url()}{path}",
                auth=self._auth(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def list_vms(self) -> list[dict[str, Any]]:
        payload = {"kind": "vm", "length": 1000}
        data = await self._post("/api/nutanix/v3/vms/list", payload)
        return data.get("entities", [])

    async def list_clusters(self) -> list[dict[str, Any]]:
        payload = {"kind": "cluster", "length": 500}
        data = await self._post("/api/nutanix/v3/clusters/list", payload)
        return data.get("entities", [])

    async def list_subnets(self) -> list[dict[str, Any]]:
        payload = {"kind": "subnet", "length": 1000}
        data = await self._post("/api/nutanix/v3/subnets/list", payload)
        return data.get("entities", [])


class NutanixAssetCache:
    """In-memory cache of Nutanix VM metadata."""

    def __init__(self) -> None:
        self._assets_by_ip: dict[str, NutanixVMMetadata] = {}
        self._updated_at: datetime | None = None

    def update(self, assets: list[NutanixVMMetadata]) -> None:
        self._assets_by_ip = {asset.ip: asset for asset in assets}
        self._updated_at = datetime.now(timezone.utc)

    def get(self, ip: str) -> NutanixVMMetadata | None:
        return self._assets_by_ip.get(ip)

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at


_nutanix_asset_cache = NutanixAssetCache()


def get_nutanix_asset_cache() -> NutanixAssetCache:
    """Get the singleton Nutanix asset cache."""
    return _nutanix_asset_cache


class NutanixAssetEnricher:
    """Apply cached Nutanix metadata to assets."""

    def __init__(self, cache: NutanixAssetCache | None = None) -> None:
        self._cache = cache or get_nutanix_asset_cache()

    async def enrich_asset(self, db: AsyncSession, asset_id: UUID, ip_address: str) -> None:
        metadata = self._cache.get(ip_address)
        if not metadata:
            return

        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            return

        nutanix_metadata = {
            "vm_id": metadata.vm_id,
            "cluster": metadata.cluster,
            "subnets": metadata.subnets,
            "categories": metadata.categories,
            "power_state": metadata.power_state,
        }
        asset.extra_data = {**(asset.extra_data or {}), "nutanix": nutanix_metadata}
        tags = dict(asset.tags or {})
        if metadata.cluster:
            tags["nutanix_cluster"] = metadata.cluster
        if metadata.subnets:
            tags["nutanix_subnets"] = metadata.subnets
        if metadata.categories:
            tags["nutanix_categories"] = metadata.categories
        asset.tags = tags

        if asset.asset_type == AssetType.UNKNOWN.value:
            asset.asset_type = AssetType.VIRTUAL_MACHINE.value

        if not asset.display_name:
            asset.display_name = metadata.name

    async def enrich_assets(
        self,
        db: AsyncSession,
        src_asset_id: UUID,
        dst_asset_id: UUID,
        src_ip: str,
        dst_ip: str,
    ) -> None:
        await self.enrich_asset(db, src_asset_id, src_ip)
        await self.enrich_asset(db, dst_asset_id, dst_ip)


class NutanixDiscoveryService:
    """Orchestrates Nutanix discovery and persistence."""

    def __init__(
        self,
        settings: NutanixSettings | None = None,
        client: NutanixDiscoveryClient | None = None,
        asset_mapper: AssetMapper | None = None,
        cache: NutanixAssetCache | None = None,
    ) -> None:
        self._settings = settings or get_settings().nutanix
        self._client = client or NutanixDiscoveryClient(self._settings)
        self._asset_mapper = asset_mapper or AssetMapper()
        self._cache = cache or get_nutanix_asset_cache()

    async def _get_or_create_status(self, db: AsyncSession) -> DiscoveryStatus:
        result = await db.execute(
            select(DiscoveryStatus).where(DiscoveryStatus.provider == NUTANIX_PROVIDER)
        )
        status = result.scalar_one_or_none()
        if status:
            return status
        status = DiscoveryStatus(provider=NUTANIX_PROVIDER, status="idle")
        db.add(status)
        await db.flush()
        return status

    async def _update_status(
        self,
        db: AsyncSession,
        status_value: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        success_at: datetime | None = None,
    ) -> None:
        status = await self._get_or_create_status(db)
        status.status = status_value
        if started_at:
            status.last_started_at = started_at
        if completed_at:
            status.last_completed_at = completed_at
        if success_at:
            status.last_success_at = success_at
        if error_message is not None:
            status.last_error = error_message
        await db.flush()

    async def fetch_snapshot(self) -> NutanixSnapshot:
        vms = await self._client.list_vms()
        clusters = await self._client.list_clusters()
        subnets = await self._client.list_subnets()
        return NutanixSnapshot(vms=vms, clusters=clusters, subnets=subnets)

    async def sync(self, db: AsyncSession) -> NutanixSnapshot:
        """Run discovery and persist assets/applications."""
        if not self._settings.enabled:
            raise RuntimeError("Nutanix discovery is disabled")

        started_at = datetime.now(timezone.utc)
        await self._update_status(db, "running", started_at=started_at, error_message=None)

        try:
            snapshot = await self.fetch_snapshot()
            assets_metadata = snapshot.build_asset_metadata()
            self._cache.update(assets_metadata)
            application_mappings = snapshot.build_application_mappings()

            await self._sync_assets(db, assets_metadata)
            await self._sync_applications(db, application_mappings)

            completed_at = datetime.now(timezone.utc)
            await self._update_status(
                db,
                "success",
                completed_at=completed_at,
                success_at=completed_at,
                error_message=None,
            )
            return snapshot
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            await self._update_status(
                db,
                "failed",
                completed_at=completed_at,
                error_message=str(exc),
            )
            logger.exception("Nutanix discovery failed", error=str(exc))
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[NutanixVMMetadata],
    ) -> None:
        for metadata in assets:
            asset_id = await self._asset_mapper.get_or_create_asset(db, metadata.ip)
            result = await db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            asset.extra_data = {
                **(asset.extra_data or {}),
                "nutanix": {
                    "vm_id": metadata.vm_id,
                    "cluster": metadata.cluster,
                    "subnets": metadata.subnets,
                    "categories": metadata.categories,
                    "power_state": metadata.power_state,
                },
            }
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["nutanix_cluster"] = metadata.cluster
            if metadata.subnets:
                tags["nutanix_subnets"] = metadata.subnets
            if metadata.categories:
                tags["nutanix_categories"] = metadata.categories
            asset.tags = tags

            if asset.asset_type == AssetType.UNKNOWN.value:
                asset.asset_type = AssetType.VIRTUAL_MACHINE.value

            if not asset.display_name:
                asset.display_name = metadata.name

        await db.flush()

    async def _sync_applications(
        self,
        db: AsyncSession,
        apps: list[NutanixApplicationMapping],
    ) -> None:
        for app in apps:
            insert_stmt = pg_insert(Application).values(
                name=app.name,
                display_name=app.display_name,
                description=f"Nutanix cluster {app.cluster}",
                tags={},
                extra_data={"nutanix": {"cluster": app.cluster}},
            ).on_conflict_do_nothing(index_elements=["name"])
            await db.execute(insert_stmt)

            result = await db.execute(select(Application).where(Application.name == app.name))
            application = result.scalar_one_or_none()
            if not application:
                continue

            asset_ids: list[UUID] = []
            for ip in app.asset_ips:
                asset_id = await self._asset_mapper.get_or_create_asset(db, ip)
                asset_ids.append(asset_id)

            for asset_id in asset_ids:
                member_stmt = pg_insert(ApplicationMember).values(
                    application_id=application.id,
                    asset_id=asset_id,
                    role="nutanix",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()


class NutanixProviderClient:
    """Nutanix Prism API client that uses DiscoveryProvider configuration."""

    def __init__(self, provider: DiscoveryProvider) -> None:
        self._provider = provider
        self._nutanix_config = provider.nutanix_config or {}

    def _base_url(self) -> str:
        return self._provider.api_url.rstrip("/")

    def _auth(self) -> tuple[str, str] | None:
        if self._provider.username and self._provider.password_encrypted:
            return (self._provider.username, self._provider.password_encrypted)  # TODO: decrypt
        return None

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._provider.timeout_seconds)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            verify=self._provider.verify_ssl,
            timeout=self._timeout(),
        ) as client:
            response = await client.post(
                f"{self._base_url()}{path}",
                auth=self._auth(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def list_vms(self) -> list[dict[str, Any]]:
        payload = {"kind": "vm", "length": 1000}
        data = await self._post("/api/nutanix/v3/vms/list", payload)
        return data.get("entities", [])

    async def list_clusters(self) -> list[dict[str, Any]]:
        payload = {"kind": "cluster", "length": 500}
        data = await self._post("/api/nutanix/v3/clusters/list", payload)
        return data.get("entities", [])

    async def list_subnets(self) -> list[dict[str, Any]]:
        payload = {"kind": "subnet", "length": 1000}
        data = await self._post("/api/nutanix/v3/subnets/list", payload)
        return data.get("entities", [])


class NutanixProviderDiscoveryService:
    """Discovery service that uses DiscoveryProvider configuration.

    This service works with the MultiProviderAssetCache instead of
    the singleton NutanixAssetCache.
    """

    def __init__(
        self,
        provider: DiscoveryProvider,
        multi_cache: "MultiProviderAssetCache | None" = None,
        asset_mapper: AssetMapper | None = None,
    ) -> None:
        self._provider = provider
        self._client = NutanixProviderClient(provider)
        self._asset_mapper = asset_mapper or AssetMapper()

        # Use multi-provider cache
        if multi_cache is None:
            from flowlens.discovery.cache import get_multi_provider_cache
            multi_cache = get_multi_provider_cache()
        self._multi_cache = multi_cache

        # Register this provider with the cache
        self._multi_cache.register_provider(
            provider_id=provider.id,
            provider_type="nutanix",
            priority=provider.priority,
        )

    async def fetch_snapshot(self) -> NutanixSnapshot:
        """Fetch current state from Nutanix API."""
        vms = await self._client.list_vms()
        clusters = await self._client.list_clusters()
        subnets = await self._client.list_subnets()
        return NutanixSnapshot(vms=vms, clusters=clusters, subnets=subnets)

    async def sync(self, db: AsyncSession) -> NutanixSnapshot:
        """Run discovery and persist assets/applications."""
        if not self._provider.is_enabled:
            raise RuntimeError(f"Provider {self._provider.name} is disabled")

        started_at = datetime.now(timezone.utc)
        self._provider.status = "running"
        self._provider.last_started_at = started_at
        self._provider.last_error = None
        await db.flush()

        try:
            snapshot = await self.fetch_snapshot()
            assets_metadata = snapshot.build_asset_metadata()

            # Update multi-provider cache
            self._multi_cache.update_provider_cache(self._provider.id, assets_metadata)

            application_mappings = snapshot.build_application_mappings()

            await self._sync_assets(db, assets_metadata)
            await self._sync_applications(db, application_mappings)

            completed_at = datetime.now(timezone.utc)
            self._provider.status = "success"
            self._provider.last_completed_at = completed_at
            self._provider.last_success_at = completed_at
            self._provider.last_error = None
            self._provider.assets_discovered = len(assets_metadata)
            self._provider.applications_discovered = len(application_mappings)
            await db.flush()

            logger.info(
                "Nutanix provider sync completed",
                provider_id=str(self._provider.id),
                provider_name=self._provider.name,
                assets=len(assets_metadata),
                applications=len(application_mappings),
            )

            return snapshot
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            self._provider.status = "failed"
            self._provider.last_completed_at = completed_at
            self._provider.last_error = str(exc)[:500]
            await db.flush()

            logger.exception(
                "Nutanix provider sync failed",
                provider_id=str(self._provider.id),
                provider_name=self._provider.name,
                error=str(exc),
            )
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[NutanixVMMetadata],
    ) -> None:
        """Sync assets to database."""
        for metadata in assets:
            asset_id = await self._asset_mapper.get_or_create_asset(db, metadata.ip)
            result = await db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            # Store provider-specific metadata
            extra_data = dict(asset.extra_data or {})
            if "nutanix" not in extra_data:
                extra_data["nutanix"] = {}

            cluster_key = f"cluster_{metadata.cluster}" if metadata.cluster else str(self._provider.id)[:8]
            extra_data["nutanix"][cluster_key] = {
                "provider_id": str(self._provider.id),
                "vm_id": metadata.vm_id,
                "cluster": metadata.cluster,
                "subnets": metadata.subnets,
                "categories": metadata.categories,
                "power_state": metadata.power_state,
            }
            asset.extra_data = extra_data

            # Update tags
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["nutanix_cluster"] = metadata.cluster
            if metadata.subnets:
                tags["nutanix_subnets"] = metadata.subnets
            if metadata.categories:
                tags["nutanix_categories"] = metadata.categories

            # Track discovery sources
            discovered_by = tags.get("discovered_by", [])
            if isinstance(discovered_by, str):
                discovered_by = [discovered_by]
            source = f"nutanix:{metadata.cluster or self._provider.name}"
            if source not in discovered_by:
                discovered_by.append(source)
            tags["discovered_by"] = discovered_by
            asset.tags = tags

            # Set asset type if unknown
            if asset.asset_type == AssetType.UNKNOWN.value:
                asset.asset_type = AssetType.VIRTUAL_MACHINE.value

            if not asset.display_name:
                asset.display_name = metadata.name

            # Link to provider
            asset.discovered_by_provider_id = self._provider.id

        await db.flush()

    async def _sync_applications(
        self,
        db: AsyncSession,
        apps: list[NutanixApplicationMapping],
    ) -> None:
        """Sync applications to database."""
        for app in apps:
            # Include provider name in application name to avoid conflicts
            app_name = f"{self._provider.name}:{app.cluster}"

            insert_stmt = pg_insert(Application).values(
                name=app_name,
                display_name=app.display_name,
                description=f"Nutanix cluster {app.cluster} (from {self._provider.name})",
                tags={},
                extra_data={
                    "nutanix": {
                        "provider_id": str(self._provider.id),
                        "provider_name": self._provider.name,
                        "cluster": app.cluster,
                    }
                },
            ).on_conflict_do_nothing(index_elements=["name"])
            await db.execute(insert_stmt)

            result = await db.execute(select(Application).where(Application.name == app_name))
            application = result.scalar_one_or_none()
            if not application:
                continue

            asset_ids: list[UUID] = []
            for ip in app.asset_ips:
                asset_id = await self._asset_mapper.get_or_create_asset(db, ip)
                asset_ids.append(asset_id)

            for asset_id in asset_ids:
                member_stmt = pg_insert(ApplicationMember).values(
                    application_id=application.id,
                    asset_id=asset_id,
                    role="nutanix",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()
