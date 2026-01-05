"""vCenter discovery integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import VCenterSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset, AssetType
from flowlens.models.discovery import DiscoveryStatus
from flowlens.resolution.asset_mapper import AssetMapper

logger = get_logger(__name__)

VCENTER_PROVIDER = "vcenter"


@dataclass(frozen=True)
class VCenterVMMetadata:
    """Metadata representing a vCenter VM."""

    ip: str
    name: str
    vm_id: str
    cluster: str | None = None
    networks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    power_state: str | None = None


@dataclass
class VCenterApplicationMapping:
    """Represents an application grouping derived from vCenter clusters."""

    name: str
    display_name: str
    cluster: str
    asset_ips: list[str]


@dataclass(frozen=True)
class VCenterSnapshot:
    """Snapshot of vCenter objects relevant to discovery."""

    vms: list[dict[str, Any]]
    clusters: list[dict[str, Any]]
    networks: list[dict[str, Any]]
    tags: dict[str, list[str]]

    def build_asset_metadata(self) -> list[VCenterVMMetadata]:
        """Build asset metadata list from vCenter VMs."""
        cluster_names = {cluster.get("cluster"): cluster.get("name") for cluster in self.clusters}
        network_names = {network.get("network"): network.get("name") for network in self.networks}
        assets: list[VCenterVMMetadata] = []

        for vm in self.vms:
            ip_addresses = []
            vm_id = vm.get("vm")
            if vm.get("guest_IP"):
                ip_addresses.append(vm.get("guest_IP"))
            for ip in vm.get("guest_IPs", []) or []:
                ip_addresses.append(ip)
            ip_addresses = [ip for ip in ip_addresses if ip]
            if not ip_addresses:
                continue

            cluster_id = vm.get("cluster")
            cluster_name = cluster_names.get(cluster_id)
            networks = [
                network_names.get(net_id, net_id)
                for net_id in (vm.get("networks") or [])
            ]
            vm_tags = self.tags.get(vm_id or "", [])

            for ip in ip_addresses:
                assets.append(
                    VCenterVMMetadata(
                        ip=ip,
                        name=vm.get("name", ip),
                        vm_id=vm_id or ip,
                        cluster=cluster_name,
                        networks=networks,
                        tags=vm_tags,
                        power_state=vm.get("power_state"),
                    )
                )
        return assets

    def build_application_mappings(self) -> list[VCenterApplicationMapping]:
        """Build application groupings from clusters."""
        clusters_by_name = {cluster.get("name") for cluster in self.clusters if cluster.get("name")}
        cluster_ips: dict[str, list[str]] = {name: [] for name in clusters_by_name}
        for asset in self.build_asset_metadata():
            if asset.cluster:
                cluster_ips.setdefault(asset.cluster, []).append(asset.ip)
        mappings = []
        for cluster_name, ips in cluster_ips.items():
            if not ips:
                continue
            app_name = f"vcenter:{cluster_name}"
            mappings.append(
                VCenterApplicationMapping(
                    name=app_name,
                    display_name=cluster_name,
                    cluster=cluster_name,
                    asset_ips=list(sorted(set(ips))),
                )
            )
        return mappings


class VCenterDiscoveryClient:
    """Lightweight vCenter API client."""

    def __init__(self, settings: VCenterSettings | None = None) -> None:
        self._settings = settings or get_settings().vcenter

    def _base_url(self) -> str:
        return self._settings.api_url.rstrip("/")

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._settings.timeout_seconds)

    async def get_session(self) -> str:
        auth = None
        if self._settings.username and self._settings.password:
            auth = (self._settings.username, self._settings.password.get_secret_value())
        async with httpx.AsyncClient(verify=self._settings.verify_ssl, timeout=self._timeout()) as client:
            response = await client.post(f"{self._base_url()}/rest/com/vmware/cis/session", auth=auth)
            response.raise_for_status()
            payload = response.json()
            return payload.get("value", "")

    async def _get(self, path: str, session_id: str) -> dict[str, Any]:
        headers = {"vmware-api-session-id": session_id}
        async with httpx.AsyncClient(verify=self._settings.verify_ssl, timeout=self._timeout()) as client:
            response = await client.get(f"{self._base_url()}{path}", headers=headers)
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"vmware-api-session-id": session_id}
        async with httpx.AsyncClient(verify=self._settings.verify_ssl, timeout=self._timeout()) as client:
            response = await client.post(f"{self._base_url()}{path}", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def list_vms(self, session_id: str) -> list[dict[str, Any]]:
        data = await self._get("/rest/vcenter/vm", session_id)
        return data.get("value", [])

    async def list_clusters(self, session_id: str) -> list[dict[str, Any]]:
        data = await self._get("/rest/vcenter/cluster", session_id)
        return data.get("value", [])

    async def list_networks(self, session_id: str) -> list[dict[str, Any]]:
        data = await self._get("/rest/vcenter/network", session_id)
        return data.get("value", [])

    async def list_tags(self, session_id: str, vm_ids: list[str]) -> dict[str, list[str]]:
        if not vm_ids:
            return {}
        tag_map: dict[str, list[str]] = {vm_id: [] for vm_id in vm_ids}
        tag_list = await self._get("/rest/com/vmware/cis/tagging/tag", session_id)
        tag_ids = tag_list.get("value", [])
        tag_names: dict[str, str] = {}
        for tag_id in tag_ids:
            tag_detail = await self._get(f"/rest/com/vmware/cis/tagging/tag/id:{tag_id}", session_id)
            name = tag_detail.get("value", {}).get("name")
            if name:
                tag_names[tag_id] = name

        for vm_id in vm_ids:
            payload = {
                "object_id": {
                    "id": vm_id,
                    "type": "VirtualMachine",
                }
            }
            response = await self._post(
                "/rest/com/vmware/cis/tagging/tag-association?~action=list-attached-tags",
                session_id,
                payload,
            )
            attached_tags = response.get("value", [])
            tag_map[vm_id] = [tag_names.get(tag_id, tag_id) for tag_id in attached_tags]
        return tag_map


class VCenterAssetCache:
    """In-memory cache of vCenter VM metadata."""

    def __init__(self) -> None:
        self._assets_by_ip: dict[str, VCenterVMMetadata] = {}
        self._updated_at: datetime | None = None

    def update(self, assets: list[VCenterVMMetadata]) -> None:
        self._assets_by_ip = {asset.ip: asset for asset in assets}
        self._updated_at = datetime.now(timezone.utc)

    def get(self, ip: str) -> VCenterVMMetadata | None:
        return self._assets_by_ip.get(ip)

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at


_vcenter_asset_cache = VCenterAssetCache()


def get_vcenter_asset_cache() -> VCenterAssetCache:
    """Get the singleton vCenter asset cache."""
    return _vcenter_asset_cache


class VCenterAssetEnricher:
    """Apply cached vCenter metadata to assets."""

    def __init__(self, cache: VCenterAssetCache | None = None) -> None:
        self._cache = cache or get_vcenter_asset_cache()

    async def enrich_asset(self, db: AsyncSession, asset_id: UUID, ip_address: str) -> None:
        metadata = self._cache.get(ip_address)
        if not metadata:
            return

        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()
        if not asset:
            return

        vcenter_metadata = {
            "vm_id": metadata.vm_id,
            "cluster": metadata.cluster,
            "networks": metadata.networks,
            "tags": metadata.tags,
            "power_state": metadata.power_state,
        }
        asset.extra_data = {**(asset.extra_data or {}), "vcenter": vcenter_metadata}
        tags = dict(asset.tags or {})
        if metadata.cluster:
            tags["vcenter_cluster"] = metadata.cluster
        if metadata.networks:
            tags["vcenter_networks"] = metadata.networks
        if metadata.tags:
            tags["vcenter_tags"] = metadata.tags
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


class VCenterDiscoveryService:
    """Orchestrates vCenter discovery and persistence."""

    def __init__(
        self,
        settings: VCenterSettings | None = None,
        client: VCenterDiscoveryClient | None = None,
        asset_mapper: AssetMapper | None = None,
        cache: VCenterAssetCache | None = None,
    ) -> None:
        self._settings = settings or get_settings().vcenter
        self._client = client or VCenterDiscoveryClient(self._settings)
        self._asset_mapper = asset_mapper or AssetMapper()
        self._cache = cache or get_vcenter_asset_cache()

    async def _get_or_create_status(self, db: AsyncSession) -> DiscoveryStatus:
        result = await db.execute(
            select(DiscoveryStatus).where(DiscoveryStatus.provider == VCENTER_PROVIDER)
        )
        status = result.scalar_one_or_none()
        if status:
            return status
        status = DiscoveryStatus(provider=VCENTER_PROVIDER, status="idle")
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

    async def fetch_snapshot(self) -> VCenterSnapshot:
        session_id = await self._client.get_session()
        vms = await self._client.list_vms(session_id)
        clusters = await self._client.list_clusters(session_id)
        networks = await self._client.list_networks(session_id)
        tags: dict[str, list[str]] = {}
        if self._settings.include_tags:
            vm_ids = [vm.get("vm") for vm in vms if vm.get("vm")]
            tags = await self._client.list_tags(session_id, vm_ids)
        return VCenterSnapshot(vms=vms, clusters=clusters, networks=networks, tags=tags)

    async def sync(self, db: AsyncSession) -> VCenterSnapshot:
        """Run discovery and persist assets/applications."""
        if not self._settings.enabled:
            raise RuntimeError("vCenter discovery is disabled")

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
            logger.exception("vCenter discovery failed", error=str(exc))
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[VCenterVMMetadata],
    ) -> None:
        for metadata in assets:
            asset_id = await self._asset_mapper.get_or_create_asset(db, metadata.ip)
            result = await db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            asset.extra_data = {
                **(asset.extra_data or {}),
                "vcenter": {
                    "vm_id": metadata.vm_id,
                    "cluster": metadata.cluster,
                    "networks": metadata.networks,
                    "tags": metadata.tags,
                    "power_state": metadata.power_state,
                },
            }
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["vcenter_cluster"] = metadata.cluster
            if metadata.networks:
                tags["vcenter_networks"] = metadata.networks
            if metadata.tags:
                tags["vcenter_tags"] = metadata.tags
            asset.tags = tags

            if asset.asset_type == AssetType.UNKNOWN.value:
                asset.asset_type = AssetType.VIRTUAL_MACHINE.value

            if not asset.display_name:
                asset.display_name = metadata.name

        await db.flush()

    async def _sync_applications(
        self,
        db: AsyncSession,
        apps: list[VCenterApplicationMapping],
    ) -> None:
        for app in apps:
            insert_stmt = pg_insert(Application).values(
                name=app.name,
                display_name=app.display_name,
                description=f"vCenter cluster {app.cluster}",
                tags={},
                extra_data={"vcenter": {"cluster": app.cluster}},
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
                    role="vcenter",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()
