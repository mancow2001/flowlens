"""vCenter discovery integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import VCenterSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset, AssetType
from flowlens.models.discovery import DiscoveryProvider, DiscoveryStatus
from flowlens.resolution.asset_mapper import AssetMapper

if TYPE_CHECKING:
    from flowlens.discovery.cache import MultiProviderAssetCache

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
    hostname: str | None = None
    fqdn: str | None = None
    mac_addresses: list[str] = field(default_factory=list)
    os_family: str | None = None
    os_name: str | None = None


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
                        hostname=vm.get("hostname"),
                        fqdn=vm.get("fqdn"),
                        mac_addresses=vm.get("mac_addresses", []),
                        os_family=vm.get("os_family"),
                        os_name=vm.get("os_name"),
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


class VCenterProviderClient:
    """vCenter API client that uses DiscoveryProvider configuration."""

    def __init__(self, provider: DiscoveryProvider) -> None:
        self._provider = provider
        self._vcenter_config = provider.vcenter_config or {}

    def _base_url(self) -> str:
        return self._provider.api_url.rstrip("/")

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._provider.timeout_seconds)

    @property
    def include_tags(self) -> bool:
        return self._vcenter_config.get("include_tags", True)

    async def get_session(self) -> str:
        """Get a session ID from vCenter."""
        auth = None
        if self._provider.username and self._provider.password_encrypted:
            auth = (self._provider.username, self._provider.password_encrypted)  # TODO: decrypt
        async with httpx.AsyncClient(verify=self._provider.verify_ssl, timeout=self._timeout()) as client:
            response = await client.post(
                f"{self._base_url()}/rest/com/vmware/cis/session",
                auth=auth,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("value", "")

    async def _get(self, path: str, session_id: str) -> dict[str, Any]:
        headers = {"vmware-api-session-id": session_id}
        async with httpx.AsyncClient(verify=self._provider.verify_ssl, timeout=self._timeout()) as client:
            response = await client.get(f"{self._base_url()}{path}", headers=headers)
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"vmware-api-session-id": session_id}
        async with httpx.AsyncClient(verify=self._provider.verify_ssl, timeout=self._timeout()) as client:
            response = await client.post(f"{self._base_url()}{path}", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def list_vms(self, session_id: str) -> list[dict[str, Any]]:
        """List all VMs with basic info."""
        data = await self._get("/rest/vcenter/vm", session_id)
        return data.get("value", [])

    async def get_vm_guest_identity(self, session_id: str, vm_id: str) -> dict[str, Any]:
        """Get guest identity info for a VM including IP addresses, hostname, OS."""
        try:
            data = await self._get(f"/rest/vcenter/vm/{vm_id}/guest/identity", session_id)
            return data.get("value", {})
        except httpx.HTTPStatusError:
            # VM might be powered off or tools not installed
            return {}

    async def get_vm_guest_networking(self, session_id: str, vm_id: str) -> dict[str, Any]:
        """Get guest networking info for a VM including MAC addresses."""
        try:
            data = await self._get(f"/rest/vcenter/vm/{vm_id}/guest/networking", session_id)
            result = data.get("value", {})
            nics = result.get("network_interfaces", []) if result else []
            logger.info("VM networking API response", vm_id=vm_id, has_result=bool(result), nic_count=len(nics))
            return result
        except httpx.HTTPStatusError as e:
            logger.info("Failed to get networking info for VM", vm_id=vm_id, status=e.response.status_code)
            return {}
        except Exception as e:
            logger.info("Error getting networking info for VM", vm_id=vm_id, error=str(e))
            return {}

    async def get_vm_hardware_nics(self, session_id: str, vm_id: str) -> list[str]:
        """Get MAC addresses from VM hardware configuration.

        This fetches MAC addresses from the VM's virtual NIC hardware config,
        which is more reliable than guest networking info (doesn't require
        VMware Tools to report it).
        """
        logger.info("Fetching VM hardware config for MACs", vm_id=vm_id)
        try:
            data = await self._get(f"/rest/vcenter/vm/{vm_id}", session_id)
            vm_info = data.get("value", {})
            nics = vm_info.get("nics", [])
            mac_addresses = []

            # Handle both list and dict formats from vCenter API
            if isinstance(nics, dict):
                nic_items = nics.values()
            else:
                nic_items = nics

            for nic_info in nic_items:
                # NIC info might be nested under 'value' key
                if isinstance(nic_info, dict):
                    nic_data = nic_info.get("value", nic_info)
                    mac = nic_data.get("mac_address")
                    if mac:
                        mac_addresses.append(mac)
                        logger.info("Found MAC in hardware", vm_id=vm_id, mac=mac)

            logger.info("VM hardware NICs result", vm_id=vm_id, nic_count=len(nics), mac_count=len(mac_addresses), macs=mac_addresses)
            return mac_addresses
        except httpx.HTTPStatusError as e:
            logger.error("Failed to get VM hardware info", vm_id=vm_id, status=e.response.status_code, error=str(e))
            return []
        except Exception as e:
            logger.error("Error getting VM hardware info", vm_id=vm_id, error=str(e), error_type=type(e).__name__)
            return []

    async def list_vms_with_guest_info(self, session_id: str) -> list[dict[str, Any]]:
        """List all VMs and enrich with guest info (IP, hostname, MAC, OS).

        This fetches the basic VM list, then for each VM fetches guest identity
        and networking info. VMs without tools or powered off won't have guest data.
        """
        vms = await self.list_vms(session_id)
        enriched_vms = []

        logger.info("Fetching guest info for VMs", total_vms=len(vms))

        for vm in vms:
            vm_id = vm.get("vm")
            if not vm_id:
                enriched_vms.append(vm)
                continue

            enriched_vm = dict(vm)

            # Get guest identity for IP, hostname, OS
            guest_identity = await self.get_vm_guest_identity(session_id, vm_id)
            if guest_identity:
                ip_address = guest_identity.get("ip_address")
                if ip_address:
                    enriched_vm["guest_IP"] = ip_address

                # Hostname and FQDN
                host_name = guest_identity.get("host_name")
                if host_name:
                    enriched_vm["hostname"] = host_name
                    # Check if it looks like FQDN (has dots)
                    if "." in host_name:
                        enriched_vm["fqdn"] = host_name

                # OS info
                enriched_vm["os_family"] = guest_identity.get("family")
                enriched_vm["os_name"] = guest_identity.get("full_name", {}).get("default_message") if isinstance(guest_identity.get("full_name"), dict) else guest_identity.get("full_name")

            # Get MAC addresses - try guest networking first, then fall back to hardware
            mac_addresses = []
            guest_networking = await self.get_vm_guest_networking(session_id, vm_id)
            if guest_networking:
                nics = guest_networking.get("network_interfaces", [])
                for nic in nics:
                    mac = nic.get("mac_address")
                    if mac:
                        mac_addresses.append(mac)

            # If guest networking didn't return MACs, get from VM hardware config
            if not mac_addresses:
                mac_addresses = await self.get_vm_hardware_nics(session_id, vm_id)

            if mac_addresses:
                enriched_vm["mac_addresses"] = mac_addresses

            if enriched_vm.get("guest_IP"):
                logger.info(
                    "Found guest info for VM",
                    vm_name=vm.get("name"),
                    ip=enriched_vm.get("guest_IP"),
                    hostname=enriched_vm.get("hostname"),
                    mac_addresses=enriched_vm.get("mac_addresses", []),
                )

            enriched_vms.append(enriched_vm)

        return enriched_vms

    # Keep old method for backwards compatibility
    async def list_vms_with_ips(self, session_id: str) -> list[dict[str, Any]]:
        """Alias for list_vms_with_guest_info."""
        return await self.list_vms_with_guest_info(session_id)

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


class VCenterProviderDiscoveryService:
    """Discovery service that uses DiscoveryProvider configuration.

    This service works with the MultiProviderAssetCache instead of
    the singleton VCenterAssetCache.
    """

    def __init__(
        self,
        provider: DiscoveryProvider,
        multi_cache: "MultiProviderAssetCache | None" = None,
        asset_mapper: AssetMapper | None = None,
    ) -> None:
        self._provider = provider
        self._client = VCenterProviderClient(provider)
        self._asset_mapper = asset_mapper or AssetMapper()

        # Use multi-provider cache
        if multi_cache is None:
            from flowlens.discovery.cache import get_multi_provider_cache
            multi_cache = get_multi_provider_cache()
        self._multi_cache = multi_cache

        # Register this provider with the cache
        self._multi_cache.register_provider(
            provider_id=provider.id,
            provider_type="vcenter",
            priority=provider.priority,
        )

    async def fetch_snapshot(self) -> VCenterSnapshot:
        """Fetch current state from vCenter API."""
        session_id = await self._client.get_session()
        # Use list_vms_with_ips to get guest IP addresses for each VM
        vms = await self._client.list_vms_with_ips(session_id)
        clusters = await self._client.list_clusters(session_id)
        networks = await self._client.list_networks(session_id)
        tags: dict[str, list[str]] = {}
        if self._client.include_tags:
            vm_ids = [vm.get("vm") for vm in vms if vm.get("vm")]
            tags = await self._client.list_tags(session_id, vm_ids)
        return VCenterSnapshot(vms=vms, clusters=clusters, networks=networks, tags=tags)

    async def sync(self, db: AsyncSession) -> VCenterSnapshot:
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

            # Debug logging to understand what vCenter returned
            vms_with_ip = sum(1 for vm in snapshot.vms if vm.get("guest_IP") or vm.get("guest_IPs"))
            logger.info(
                "vCenter snapshot fetched",
                provider_name=self._provider.name,
                total_vms=len(snapshot.vms),
                vms_with_ip=vms_with_ip,
                clusters=len(snapshot.clusters),
                networks=len(snapshot.networks),
            )

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
                "vCenter provider sync completed",
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
                "vCenter provider sync failed",
                provider_id=str(self._provider.id),
                provider_name=self._provider.name,
                error=str(exc),
            )
            raise

    async def _sync_assets(
        self,
        db: AsyncSession,
        assets: list[VCenterVMMetadata],
    ) -> None:
        """Sync assets to database."""
        for metadata in assets:
            logger.info(
                "Processing asset metadata",
                ip=metadata.ip,
                name=metadata.name,
                hostname=metadata.hostname,
                mac_addresses=metadata.mac_addresses,
            )
            asset_id = await self._asset_mapper.get_or_create_asset(db, metadata.ip)
            result = await db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            # Store provider-specific metadata
            extra_data = dict(asset.extra_data or {})
            if "vcenter" not in extra_data:
                extra_data["vcenter"] = {}

            cluster_key = f"cluster_{metadata.cluster}" if metadata.cluster else str(self._provider.id)[:8]
            extra_data["vcenter"][cluster_key] = {
                "provider_id": str(self._provider.id),
                "vm_id": metadata.vm_id,
                "cluster": metadata.cluster,
                "networks": metadata.networks,
                "tags": metadata.tags,
                "power_state": metadata.power_state,
                "hostname": metadata.hostname,
                "fqdn": metadata.fqdn,
                "mac_addresses": metadata.mac_addresses,
                "os_family": metadata.os_family,
                "os_name": metadata.os_name,
            }
            asset.extra_data = extra_data

            # Update core asset fields from vCenter data
            if metadata.hostname and not asset.hostname:
                asset.hostname = metadata.hostname
            if metadata.fqdn and not asset.hostname:
                # Use FQDN as hostname if no hostname set
                asset.hostname = metadata.fqdn
            if metadata.mac_addresses and not asset.mac_address:
                # Use first MAC address
                asset.mac_address = metadata.mac_addresses[0]

            # Update tags
            tags = dict(asset.tags or {})
            if metadata.cluster:
                tags["vcenter_cluster"] = metadata.cluster
            if metadata.networks:
                # Store as comma-separated string (tags must be strings)
                tags["vcenter_networks"] = ", ".join(metadata.networks)
            if metadata.tags:
                # Store as comma-separated string (tags must be strings)
                tags["vcenter_tags"] = ", ".join(metadata.tags)
            if metadata.os_family:
                tags["os_family"] = metadata.os_family
            if metadata.os_name:
                tags["os_name"] = metadata.os_name
            if metadata.mac_addresses:
                tags["mac_addresses"] = ", ".join(metadata.mac_addresses)

            # Track discovery sources (as comma-separated string)
            source = f"vcenter:{metadata.cluster or self._provider.name}"
            existing_sources = tags.get("discovered_by", "")
            if existing_sources:
                sources_list = [s.strip() for s in existing_sources.split(",")]
                if source not in sources_list:
                    sources_list.append(source)
                tags["discovered_by"] = ", ".join(sources_list)
            else:
                tags["discovered_by"] = source
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
        apps: list[VCenterApplicationMapping],
    ) -> None:
        """Sync applications to database."""
        for app in apps:
            # Include provider name in application name to avoid conflicts
            app_name = f"{self._provider.name}:{app.cluster}"

            insert_stmt = pg_insert(Application).values(
                name=app_name,
                display_name=app.display_name,
                description=f"vCenter cluster {app.cluster} (from {self._provider.name})",
                tags={},
                extra_data={
                    "vcenter": {
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
                    role="vcenter",
                ).on_conflict_do_nothing(index_elements=["application_id", "asset_id"])
                await db.execute(member_stmt)

        await db.flush()
