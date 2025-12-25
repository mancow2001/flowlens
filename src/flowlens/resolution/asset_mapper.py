"""Asset mapping for dependency resolution.

Maps IP addresses to assets from flow aggregates,
creating or updating assets as needed.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.common.metrics import ASSETS_DISCOVERED, ASSETS_UPDATED
from flowlens.enrichment.resolvers.geoip import GeoIPResolver, PrivateIPClassifier
from flowlens.models.asset import Asset, AssetType
from flowlens.models.flow import FlowAggregate

logger = get_logger(__name__)


class AssetMapper:
    """Maps IP addresses to assets.

    Responsible for:
    - Looking up existing assets by IP
    - Creating new assets for unknown IPs
    - Updating asset statistics from flow data
    """

    def __init__(
        self,
        geoip_resolver: GeoIPResolver | None = None,
    ) -> None:
        """Initialize asset mapper.

        Args:
            geoip_resolver: Optional GeoIP resolver for location data.
        """
        self._geoip = geoip_resolver
        self._classifier = PrivateIPClassifier()

        # Cache of IP -> Asset ID for efficiency
        self._ip_cache: dict[str, UUID] = {}

    async def get_or_create_asset(
        self,
        db: AsyncSession,
        ip_str: str,
        hostname: str | None = None,
    ) -> UUID:
        """Get existing asset or create new one for IP.

        Args:
            db: Database session.
            ip_str: IP address string.
            hostname: Optional hostname.

        Returns:
            Asset ID.
        """
        # Check cache first
        if ip_str in self._ip_cache:
            return self._ip_cache[ip_str]

        # Query database
        result = await db.execute(
            select(Asset.id).where(
                Asset.ip_address == ip_str,
                Asset.deleted_at.is_(None),
            )
        )
        asset_id = result.scalar_one_or_none()

        if asset_id:
            self._ip_cache[ip_str] = asset_id
            return asset_id

        # Create new asset
        asset = await self._create_asset(db, ip_str, hostname)
        self._ip_cache[ip_str] = asset.id

        return asset.id

    async def _create_asset(
        self,
        db: AsyncSession,
        ip_str: str,
        hostname: str | None,
    ) -> Asset:
        """Create a new asset for an IP address.

        Args:
            db: Database session.
            ip_str: IP address string.
            hostname: Optional hostname.

        Returns:
            Created asset.
        """
        # Determine if internal or external
        is_internal = self._classifier.is_private(ip_str)

        # Generate name
        if hostname:
            name = hostname.split(".")[0]
        else:
            name = ip_str.replace(".", "-").replace(":", "-")

        # Default asset type - use UNKNOWN for all auto-discovered assets
        # The is_internal field tracks internal vs external location
        asset_type = AssetType.UNKNOWN

        # Get GeoIP info for external IPs
        country_code = None
        city = None

        if not is_internal and self._geoip and self._geoip.is_enabled:
            geo_result = self._geoip.lookup(ip_str)
            if geo_result:
                country_code = geo_result.country_code
                city = geo_result.city

        # Create asset
        asset = Asset(
            name=name,
            ip_address=ip_str,
            hostname=hostname,
            fqdn=hostname if hostname and "." in hostname else None,
            asset_type=asset_type,
            is_internal=is_internal,
            is_critical=False,
            country_code=country_code,
            city=city,
        )

        db.add(asset)
        await db.flush()

        logger.info(
            "Created new asset",
            asset_id=str(asset.id),
            ip=ip_str,
            hostname=hostname,
            is_internal=is_internal,
        )

        ASSETS_DISCOVERED.labels(
            asset_type="internal" if is_internal else "external"
        ).inc()

        return asset

    async def map_aggregate_to_assets(
        self,
        db: AsyncSession,
        aggregate: FlowAggregate,
    ) -> tuple[UUID, UUID]:
        """Map a flow aggregate to source and destination assets.

        Creates assets if they don't exist, updates if they do.

        Args:
            db: Database session.
            aggregate: Flow aggregate to map.

        Returns:
            Tuple of (source_asset_id, destination_asset_id).
        """
        src_ip = str(aggregate.src_ip)
        dst_ip = str(aggregate.dst_ip)

        # Get hostnames from extended fields if available
        src_hostname = None
        dst_hostname = None

        # Get or create assets
        src_asset_id = aggregate.src_asset_id
        dst_asset_id = aggregate.dst_asset_id

        if not src_asset_id:
            src_asset_id = await self.get_or_create_asset(db, src_ip, src_hostname)

        if not dst_asset_id:
            dst_asset_id = await self.get_or_create_asset(db, dst_ip, dst_hostname)

        return src_asset_id, dst_asset_id

    async def update_asset_traffic_stats(
        self,
        db: AsyncSession,
        asset_id: UUID,
        bytes_in: int = 0,
        bytes_out: int = 0,
        connections_in: int = 0,
        connections_out: int = 0,
        last_seen: datetime | None = None,
    ) -> None:
        """Update asset traffic statistics.

        Args:
            db: Database session.
            asset_id: Asset to update.
            bytes_in: Bytes received.
            bytes_out: Bytes sent.
            connections_in: Inbound connection count.
            connections_out: Outbound connection count.
            last_seen: Last activity timestamp.
        """
        values = {}

        if bytes_in or bytes_out or connections_in or connections_out:
            values["bytes_in_total"] = Asset.bytes_in_total + bytes_in
            values["bytes_out_total"] = Asset.bytes_out_total + bytes_out
            values["connections_in"] = Asset.connections_in + connections_in
            values["connections_out"] = Asset.connections_out + connections_out

        if last_seen:
            values["last_seen"] = last_seen

        if values:
            await db.execute(
                update(Asset)
                .where(Asset.id == asset_id)
                .values(**values)
            )
            ASSETS_UPDATED.inc()

    async def bulk_get_or_create_assets(
        self,
        db: AsyncSession,
        ip_addresses: list[str],
    ) -> dict[str, UUID]:
        """Get or create assets for multiple IP addresses.

        Args:
            db: Database session.
            ip_addresses: List of IP addresses.

        Returns:
            Dictionary mapping IP addresses to asset IDs.
        """
        results: dict[str, UUID] = {}
        uncached_ips: list[str] = []

        # Check cache first
        for ip in ip_addresses:
            if ip in self._ip_cache:
                results[ip] = self._ip_cache[ip]
            else:
                uncached_ips.append(ip)

        if not uncached_ips:
            return results

        # Query database for existing assets
        result = await db.execute(
            select(Asset.ip_address, Asset.id)
            .where(
                Asset.ip_address.in_(uncached_ips),
                Asset.deleted_at.is_(None),
            )
        )

        for ip, asset_id in result.fetchall():
            results[ip] = asset_id
            self._ip_cache[ip] = asset_id
            uncached_ips.remove(ip)

        # Create assets for remaining IPs
        for ip in uncached_ips:
            asset_id = await self.get_or_create_asset(db, ip)
            results[ip] = asset_id

        return results

    def clear_cache(self) -> None:
        """Clear the IP cache."""
        self._ip_cache.clear()

    @property
    def cache_size(self) -> int:
        """Get cache size."""
        return len(self._ip_cache)
