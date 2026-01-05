"""Kubernetes discovery integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import KubernetesSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset, AssetType
from flowlens.models.discovery import DiscoveryProvider, DiscoveryStatus
from flowlens.resolution.asset_mapper import AssetMapper

if TYPE_CHECKING:
    from flowlens.discovery.cache import MultiProviderAssetCache

logger = get_logger(__name__)

KUBERNETES_PROVIDER = "kubernetes"


@dataclass(frozen=True)
class KubernetesAssetMetadata:
    """Metadata representing a Kubernetes-addressable entity."""

    ip: str
    name: str
    namespace: str
    cluster: str
    kind: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class KubernetesApplicationMapping:
    """Represents an application grouping derived from Kubernetes labels."""

    name: str
    display_name: str
    namespace: str
    cluster: str
    labels: dict[str, str]
    asset_ips: list[str]


@dataclass(frozen=True)
class KubernetesSnapshot:
    """Snapshot of Kubernetes objects relevant to discovery."""

    namespaces: list[dict[str, Any]]
    pods: list[dict[str, Any]]
    services: list[dict[str, Any]]

    def build_asset_metadata(self, cluster: str) -> list[KubernetesAssetMetadata]:
        """Build asset metadata list from pods and services."""
        assets: list[KubernetesAssetMetadata] = []
        for pod in self.pods:
            ip = pod.get("status", {}).get("podIP")
            metadata = pod.get("metadata", {})
            if not ip:
                continue
            assets.append(
                KubernetesAssetMetadata(
                    ip=ip,
                    name=metadata.get("name", ip),
                    namespace=metadata.get("namespace", "default"),
                    cluster=cluster,
                    kind="pod",
                    labels=metadata.get("labels") or {},
                )
            )
        for service in self.services:
            ip = service.get("spec", {}).get("clusterIP")
            metadata = service.get("metadata", {})
            if not ip or ip == "None":
                continue
            assets.append(
                KubernetesAssetMetadata(
                    ip=ip,
                    name=metadata.get("name", ip),
                    namespace=metadata.get("namespace", "default"),
                    cluster=cluster,
                    kind="service",
                    labels=metadata.get("labels") or {},
                )
            )
        return assets

    def build_application_mappings(self, cluster: str) -> list[KubernetesApplicationMapping]:
        """Build application groupings from pods and services."""
        apps: dict[tuple[str, str], KubernetesApplicationMapping] = {}
        for item in self.pods + self.services:
            metadata = item.get("metadata", {})
            labels = metadata.get("labels") or {}
            namespace = metadata.get("namespace", "default")
            name = (
                labels.get("app.kubernetes.io/name")
                or labels.get("app")
                or labels.get("k8s-app")
                or metadata.get("name", "unknown")
            )
            key = (namespace, name)
            asset_ip = item.get("status", {}).get("podIP") or item.get("spec", {}).get("clusterIP")
            if not asset_ip:
                continue
            app_name = f"{cluster}:{namespace}:{name}"
            if key not in apps:
                apps[key] = KubernetesApplicationMapping(
                    name=app_name,
                    display_name=name,
                    namespace=namespace,
                    cluster=cluster,
                    labels=labels,
                    asset_ips=[asset_ip],
                )
            else:
                apps[key].asset_ips.append(asset_ip)
        return list(apps.values())


class KubernetesDiscoveryClient:
    """Lightweight Kubernetes API client."""

    def __init__(self, settings: KubernetesSettings | None = None) -> None:
        self._settings = settings or get_settings().kubernetes

    def _build_headers(self) -> dict[str, str]:
        token = self._settings.token
        if not token and self._settings.token_file:
            try:
                token = self._settings.token_file.read_text().strip()
            except OSError:
                token = None
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _build_verify(self) -> bool | str:
        if not self._settings.verify_ssl:
            return False
        if self._settings.ca_cert_path:
            return str(self._settings.ca_cert_path)
        return True

    def _base_url(self) -> str:
        return self._settings.api_server.rstrip("/")

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url()}{path}"
        timeout = httpx.Timeout(self._settings.timeout_seconds)
        async with httpx.AsyncClient(verify=self._build_verify(), timeout=timeout) as client:
            response = await client.get(url, headers=self._build_headers())
            response.raise_for_status()
            return response.json()

    async def list_namespaces(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/namespaces")
        return data.get("items", [])

    async def list_pods(self) -> list[dict[str, Any]]:
        namespace = self._settings.namespace
        if namespace:
            data = await self._get(f"/api/v1/namespaces/{namespace}/pods")
        else:
            data = await self._get("/api/v1/pods")
        return data.get("items", [])

    async def list_services(self) -> list[dict[str, Any]]:
        namespace = self._settings.namespace
        if namespace:
            data = await self._get(f"/api/v1/namespaces/{namespace}/services")
        else:
            data = await self._get("/api/v1/services")
        return data.get("items", [])


class KubernetesAssetCache:
    """In-memory cache of Kubernetes asset metadata."""

    def __init__(self) -> None:
        self._assets_by_ip: dict[str, KubernetesAssetMetadata] = {}
        self._updated_at: datetime | None = None

    def update(self, assets: list[KubernetesAssetMetadata]) -> None:
        self._assets_by_ip = {asset.ip: asset for asset in assets}
        self._updated_at = datetime.now(timezone.utc)

    def get(self, ip: str) -> KubernetesAssetMetadata | None:
        return self._assets_by_ip.get(ip)

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at


_k8s_asset_cache = KubernetesAssetCache()


def get_kubernetes_asset_cache() -> KubernetesAssetCache:
    """Get the singleton Kubernetes asset cache."""
    return _k8s_asset_cache


class KubernetesAssetEnricher:
    """Apply cached Kubernetes metadata to assets."""

    def __init__(self, cache: KubernetesAssetCache | None = None) -> None:
        self._cache = cache or get_kubernetes_asset_cache()

    async def enrich_asset(self, db: AsyncSession, asset_id: UUID, ip_address: str) -> None:
        metadata = self._cache.get(ip_address)
        if not metadata:
            return

        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            return

        k8s_metadata = {
            "cluster": metadata.cluster,
            "namespace": metadata.namespace,
            "name": metadata.name,
            "kind": metadata.kind,
            "labels": metadata.labels,
        }
        asset.extra_data = {**(asset.extra_data or {}), "kubernetes": k8s_metadata}
        tags = dict(asset.tags or {})
        tags.update({
            "kubernetes_cluster": metadata.cluster,
            "kubernetes_namespace": metadata.namespace,
        })
        asset.tags = tags

        if asset.asset_type == AssetType.UNKNOWN.value:
            if metadata.kind == "service":
                asset.asset_type = AssetType.LOAD_BALANCER.value
            else:
                asset.asset_type = AssetType.CONTAINER.value

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


class KubernetesDiscoveryService:
    """Orchestrates Kubernetes discovery and persistence."""

    def __init__(
        self,
        settings: KubernetesSettings | None = None,
        client: KubernetesDiscoveryClient | None = None,
        asset_mapper: AssetMapper | None = None,
        cache: KubernetesAssetCache | None = None,
    ) -> None:
        self._settings = settings or get_settings().kubernetes
        self._client = client or KubernetesDiscoveryClient(self._settings)
        self._asset_mapper = asset_mapper or AssetMapper()
        self._cache = cache or get_kubernetes_asset_cache()

    async def _get_or_create_status(self, db: AsyncSession) -> DiscoveryStatus:
        result = await db.execute(
            select(DiscoveryStatus).where(DiscoveryStatus.provider == KUBERNETES_PROVIDER)
        )
        status = result.scalar_one_or_none()
        if status:
            return status
        status = DiscoveryStatus(provider=KUBERNETES_PROVIDER, status="idle")
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

    async def fetch_snapshot(self) -> KubernetesSnapshot:
        namespaces, pods, services = await asyncio.gather(
            self._client.list_namespaces(),
            self._client.list_pods(),
            self._client.list_services(),
        )
        return KubernetesSnapshot(namespaces=namespaces, pods=pods, services=services)

    async def sync(self, db: AsyncSession) -> KubernetesSnapshot:
        """Run discovery and persist assets/applications."""
        if not self._settings.enabled:
            raise RuntimeError("Kubernetes discovery is disabled")

        started_at = datetime.now(timezone.utc)
        await self._update_status(db, "running", started_at=started_at, error_message=None)

        try:
            snapshot = await self.fetch_snapshot()
            cluster_name = self._settings.cluster_name
            assets_metadata = snapshot.build_asset_metadata(cluster_name)
            self._cache.update(assets_metadata)

            application_mappings = snapshot.build_application_mappings(cluster_name)

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
            logger.exception("Kubernetes discovery failed", error=str(exc))
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[KubernetesAssetMetadata],
    ) -> None:
        for metadata in assets:
            asset_id = await self._asset_mapper.get_or_create_asset(db, metadata.ip)
            result = await db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            asset.extra_data = {
                **(asset.extra_data or {}),
                "kubernetes": {
                    "cluster": metadata.cluster,
                    "namespace": metadata.namespace,
                    "name": metadata.name,
                    "kind": metadata.kind,
                    "labels": metadata.labels,
                },
            }
            tags = dict(asset.tags or {})
            tags.update({
                "kubernetes_cluster": metadata.cluster,
                "kubernetes_namespace": metadata.namespace,
            })
            asset.tags = tags

            if asset.asset_type == AssetType.UNKNOWN.value:
                if metadata.kind == "service":
                    asset.asset_type = AssetType.LOAD_BALANCER.value
                else:
                    asset.asset_type = AssetType.CONTAINER.value

            if not asset.display_name:
                asset.display_name = metadata.name

        await db.flush()

    async def _sync_applications(
        self,
        db: AsyncSession,
        apps: list[KubernetesApplicationMapping],
    ) -> None:
        for app in apps:
            insert_stmt = pg_insert(Application).values(
                name=app.name,
                display_name=app.display_name,
                description=f"Kubernetes application in namespace {app.namespace}",
                tags={},
                extra_data={
                    "kubernetes": {
                        "cluster": app.cluster,
                        "namespace": app.namespace,
                        "labels": app.labels,
                    }
                },
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
                    role="kubernetes",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()


class KubernetesProviderClient:
    """Kubernetes API client that uses DiscoveryProvider configuration."""

    def __init__(self, provider: DiscoveryProvider) -> None:
        self._provider = provider
        self._k8s_config = provider.k8s_config or {}

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {"Accept": "application/json"}
        token = self._k8s_config.get("token_encrypted")  # TODO: decrypt
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _build_verify(self) -> bool | str:
        """Build SSL verification setting."""
        if not self._provider.verify_ssl:
            return False
        ca_cert = self._k8s_config.get("ca_cert")
        if ca_cert:
            # Would need to write to temp file for httpx
            # For now, just return True if we have a cert
            return True
        return True

    def _base_url(self) -> str:
        return self._provider.api_url.rstrip("/")

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._provider.timeout_seconds)

    @property
    def namespace(self) -> str | None:
        return self._k8s_config.get("namespace")

    @property
    def cluster_name(self) -> str:
        return self._k8s_config.get("cluster_name", "default-cluster")

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url()}{path}"
        async with httpx.AsyncClient(verify=self._build_verify(), timeout=self._timeout()) as client:
            response = await client.get(url, headers=self._build_headers())
            response.raise_for_status()
            return response.json()

    async def list_namespaces(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/namespaces")
        return data.get("items", [])

    async def list_pods(self) -> list[dict[str, Any]]:
        namespace = self.namespace
        if namespace:
            data = await self._get(f"/api/v1/namespaces/{namespace}/pods")
        else:
            data = await self._get("/api/v1/pods")
        return data.get("items", [])

    async def list_services(self) -> list[dict[str, Any]]:
        namespace = self.namespace
        if namespace:
            data = await self._get(f"/api/v1/namespaces/{namespace}/services")
        else:
            data = await self._get("/api/v1/services")
        return data.get("items", [])


class KubernetesProviderDiscoveryService:
    """Discovery service that uses DiscoveryProvider configuration.

    This service works with the MultiProviderAssetCache instead of
    the singleton KubernetesAssetCache.
    """

    def __init__(
        self,
        provider: DiscoveryProvider,
        multi_cache: "MultiProviderAssetCache | None" = None,
        asset_mapper: AssetMapper | None = None,
    ) -> None:
        self._provider = provider
        self._client = KubernetesProviderClient(provider)
        self._asset_mapper = asset_mapper or AssetMapper()

        # Use multi-provider cache
        if multi_cache is None:
            from flowlens.discovery.cache import get_multi_provider_cache
            multi_cache = get_multi_provider_cache()
        self._multi_cache = multi_cache

        # Register this provider with the cache
        self._multi_cache.register_provider(
            provider_id=provider.id,
            provider_type="kubernetes",
            priority=provider.priority,
        )

    async def fetch_snapshot(self) -> KubernetesSnapshot:
        """Fetch current state from Kubernetes API."""
        namespaces, pods, services = await asyncio.gather(
            self._client.list_namespaces(),
            self._client.list_pods(),
            self._client.list_services(),
        )
        return KubernetesSnapshot(namespaces=namespaces, pods=pods, services=services)

    async def sync(self, db: AsyncSession) -> KubernetesSnapshot:
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
            cluster_name = self._client.cluster_name
            assets_metadata = snapshot.build_asset_metadata(cluster_name)

            # Update multi-provider cache
            self._multi_cache.update_provider_cache(self._provider.id, assets_metadata)

            application_mappings = snapshot.build_application_mappings(cluster_name)

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
                "Kubernetes provider sync completed",
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
                "Kubernetes provider sync failed",
                provider_id=str(self._provider.id),
                provider_name=self._provider.name,
                error=str(exc),
            )
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[KubernetesAssetMetadata],
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
            if "kubernetes" not in extra_data:
                extra_data["kubernetes"] = {}

            cluster_key = f"cluster_{metadata.cluster}"
            extra_data["kubernetes"][cluster_key] = {
                "provider_id": str(self._provider.id),
                "cluster": metadata.cluster,
                "namespace": metadata.namespace,
                "name": metadata.name,
                "kind": metadata.kind,
                "labels": metadata.labels,
            }
            asset.extra_data = extra_data

            # Update tags
            tags = dict(asset.tags or {})
            tags["kubernetes_cluster"] = metadata.cluster
            tags["kubernetes_namespace"] = metadata.namespace

            # Track discovery sources
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

            if not asset.display_name:
                asset.display_name = metadata.name

            # Link to provider
            asset.discovered_by_provider_id = self._provider.id

        await db.flush()

    async def _sync_applications(
        self,
        db: AsyncSession,
        apps: list[KubernetesApplicationMapping],
    ) -> None:
        """Sync applications to database."""
        for app in apps:
            # Include provider name in application name to avoid conflicts
            app_name = f"{self._provider.name}:{app.namespace}:{app.display_name}"

            insert_stmt = pg_insert(Application).values(
                name=app_name,
                display_name=app.display_name,
                description=f"Kubernetes application in namespace {app.namespace} (from {self._provider.name})",
                tags={},
                extra_data={
                    "kubernetes": {
                        "provider_id": str(self._provider.id),
                        "provider_name": self._provider.name,
                        "cluster": app.cluster,
                        "namespace": app.namespace,
                        "labels": app.labels,
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
                    role="kubernetes",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()
