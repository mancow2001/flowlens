"""Asset correlation for enrichment service.

Matches IP addresses to existing assets and creates
new assets when necessary.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.common.metrics import ASSETS_DISCOVERED
from flowlens.enrichment.resolvers.geoip import GeoIPResolver, GeoIPResult, PrivateIPClassifier
from flowlens.models.asset import Asset, AssetType

logger = get_logger(__name__)


class AssetCorrelator:
    """Correlates IP addresses to assets.

    Looks up existing assets by IP and creates new ones
    for previously unseen IPs.
    """

    def __init__(
        self,
        geoip_resolver: GeoIPResolver | None = None,
    ) -> None:
        """Initialize correlator.

        Args:
            geoip_resolver: GeoIP resolver for new assets.
        """
        self._geoip = geoip_resolver
        self._classifier = PrivateIPClassifier()

        # In-memory cache of IP -> Asset ID mappings
        self._ip_cache: dict[str, UUID] = {}

    async def correlate(
        self,
        db: AsyncSession,
        ip_address: IPv4Address | IPv6Address | str,
        hostname: str | None = None,
    ) -> UUID:
        """Correlate IP address to asset.

        Creates new asset if not found.

        Args:
            db: Database session.
            ip_address: IP address to correlate.
            hostname: Optional hostname from DNS lookup.

        Returns:
            Asset ID.
        """
        ip_str = str(ip_address)

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
            name = hostname.split(".")[0]  # Use first part of hostname
        else:
            name = ip_str.replace(".", "-").replace(":", "-")

        # Default asset type based on classification
        asset_type = AssetType.UNKNOWN
        if not is_internal:
            asset_type = AssetType.EXTERNAL

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
            "Discovered new asset",
            asset_id=str(asset.id),
            ip=ip_str,
            hostname=hostname,
            is_internal=is_internal,
        )

        ASSETS_DISCOVERED.labels(
            asset_type="internal" if is_internal else "external"
        ).inc()

        return asset

    async def correlate_batch(
        self,
        db: AsyncSession,
        ip_addresses: list[tuple[str, str | None]],
    ) -> dict[str, UUID]:
        """Correlate multiple IP addresses to assets.

        Args:
            db: Database session.
            ip_addresses: List of (ip, hostname) tuples.

        Returns:
            Dictionary mapping IPs to asset IDs.
        """
        results = {}

        for ip_str, hostname in ip_addresses:
            asset_id = await self.correlate(db, ip_str, hostname)
            results[ip_str] = asset_id

        return results

    async def update_asset_last_seen(
        self,
        db: AsyncSession,
        asset_id: UUID,
        timestamp: datetime,
    ) -> None:
        """Update asset's last_seen timestamp.

        Args:
            db: Database session.
            asset_id: Asset ID.
            timestamp: New last_seen timestamp.
        """
        await db.execute(
            update(Asset)
            .where(Asset.id == asset_id)
            .values(last_seen=timestamp)
        )

    async def update_asset_traffic(
        self,
        db: AsyncSession,
        asset_id: UUID,
        bytes_in: int = 0,
        bytes_out: int = 0,
        connections_in: int = 0,
        connections_out: int = 0,
    ) -> None:
        """Update asset traffic counters.

        Args:
            db: Database session.
            asset_id: Asset ID.
            bytes_in: Bytes received.
            bytes_out: Bytes sent.
            connections_in: Inbound connections.
            connections_out: Outbound connections.
        """
        await db.execute(
            update(Asset)
            .where(Asset.id == asset_id)
            .values(
                bytes_in_total=Asset.bytes_in_total + bytes_in,
                bytes_out_total=Asset.bytes_out_total + bytes_out,
                connections_in=Asset.connections_in + connections_in,
                connections_out=Asset.connections_out + connections_out,
            )
        )

    def clear_cache(self) -> None:
        """Clear the IP cache."""
        self._ip_cache.clear()

    @property
    def cache_size(self) -> int:
        """Get cache size."""
        return len(self._ip_cache)
