"""Asset correlation for enrichment service.

Matches IP addresses to existing assets and creates
new assets when necessary.
"""

import hashlib
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.common.metrics import ASSETS_DISCOVERED
from flowlens.enrichment.resolvers.geoip import GeoIPResolver, PrivateIPClassifier
from flowlens.models.asset import Asset, AssetType

logger = get_logger(__name__)


def _ip_to_advisory_lock_id(ip_str: str) -> int:
    """Convert IP address to a consistent advisory lock ID.

    Uses a hash to generate a 32-bit integer for PostgreSQL advisory locks.
    """
    # Use MD5 hash and take first 8 hex chars (32 bits)
    hash_bytes = hashlib.md5(ip_str.encode()).hexdigest()[:8]
    return int(hash_bytes, 16) & 0x7FFFFFFF  # Ensure positive 32-bit int


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

        Creates new asset if not found using INSERT ... ON CONFLICT DO NOTHING
        to handle race conditions cleanly.

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

        # Query database for existing asset
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

        # Asset doesn't exist - create it using INSERT ... ON CONFLICT DO NOTHING
        # This handles race conditions without generating errors
        asset_id = await self._upsert_asset(db, ip_str, hostname)
        self._ip_cache[ip_str] = asset_id
        return asset_id

    async def _upsert_asset(
        self,
        db: AsyncSession,
        ip_str: str,
        hostname: str | None,
    ) -> UUID:
        """Create a new asset or return existing one using advisory locks.

        Uses PostgreSQL advisory locks to prevent deadlocks when multiple
        workers try to create the same asset simultaneously.

        Args:
            db: Database session.
            ip_str: IP address string.
            hostname: Optional hostname.

        Returns:
            Asset ID (either newly created or existing).
        """
        import uuid

        # Acquire advisory lock for this IP to prevent deadlocks
        lock_id = _ip_to_advisory_lock_id(ip_str)
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

        # Now we have exclusive access for this IP - check if it exists
        query_result = await db.execute(
            select(Asset.id).where(
                Asset.ip_address == ip_str,
                Asset.deleted_at.is_(None),
            )
        )
        existing_id = query_result.scalar_one_or_none()
        if existing_id:
            return existing_id

        # Asset doesn't exist - create it
        # Determine if internal or external
        is_internal = self._classifier.is_private(ip_str)

        # Generate name
        if hostname:
            name = hostname.split(".")[0]  # Use first part of hostname
        else:
            name = ip_str.replace(".", "-").replace(":", "-")

        # Default asset type - use UNKNOWN for all auto-discovered assets
        asset_type = AssetType.UNKNOWN.value

        # Get GeoIP info for external IPs
        country_code = None
        city = None

        if not is_internal and self._geoip and self._geoip.is_enabled:
            geo_result = self._geoip.lookup(ip_str)
            if geo_result:
                country_code = geo_result.country_code
                city = geo_result.city

        # Generate a new UUID for the insert
        new_id = uuid.uuid4()

        # Insert the new asset
        stmt = pg_insert(Asset).values(
            id=new_id,
            name=name,
            ip_address=ip_str,
            hostname=hostname,
            fqdn=hostname if hostname and "." in hostname else None,
            asset_type=asset_type,
            is_internal=is_internal,
            is_critical=False,
            country_code=country_code,
            city=city,
        ).on_conflict_do_nothing(index_elements=['ip_address'])

        result = await db.execute(stmt)

        # Check if we inserted a new row
        if result.rowcount > 0:
            await db.flush()
            logger.info(
                "Discovered new asset",
                asset_id=str(new_id),
                ip=ip_str,
                hostname=hostname,
                is_internal=is_internal,
            )
            ASSETS_DISCOVERED.labels(
                asset_type="internal" if is_internal else "external"
            ).inc()
            return new_id

        # Conflict occurred (another transaction committed while we had the lock)
        # This shouldn't happen with advisory locks, but handle it anyway
        query_result = await db.execute(
            select(Asset.id).where(
                Asset.ip_address == ip_str,
                Asset.deleted_at.is_(None),
            )
        )
        existing_id = query_result.scalar_one_or_none()
        if existing_id:
            return existing_id

        raise RuntimeError(f"Failed to get or create asset for IP {ip_str}")

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
