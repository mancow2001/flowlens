"""Asset mapping for dependency resolution.

Maps IP addresses to assets from flow aggregates,
creating or updating assets as needed.
"""

import hashlib
import uuid as uuid_module
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.common.metrics import ASSETS_DISCOVERED, ASSETS_UPDATED
from flowlens.enrichment.resolvers.geoip import GeoIPResolver, PrivateIPClassifier
from flowlens.models.asset import Asset, AssetType
from flowlens.models.flow import FlowAggregate

logger = get_logger(__name__)


def _ip_to_advisory_lock_id(ip_str: str) -> int:
    """Convert IP address to a consistent advisory lock ID.

    Uses a hash to generate a 32-bit integer for PostgreSQL advisory locks.
    """
    # Use MD5 hash and take first 8 hex chars (32 bits)
    hash_bytes = hashlib.md5(ip_str.encode()).hexdigest()[:8]
    return int(hash_bytes, 16) & 0x7FFFFFFF  # Ensure positive 32-bit int


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

        Uses INSERT ... ON CONFLICT DO NOTHING to handle race conditions
        cleanly without generating database errors.

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

        # Create new asset using upsert
        asset_id = await self._upsert_asset(db, ip_str, hostname)
        self._ip_cache[ip_str] = asset_id

        return asset_id

    async def _get_cidr_classification(
        self,
        db: AsyncSession,
        ip_str: str,
    ) -> dict | None:
        """Get CIDR classification for an IP address.

        Args:
            db: Database session.
            ip_str: IP address string.

        Returns:
            Classification dict or None if no matching rule.
        """
        try:
            result = await db.execute(
                text("SELECT * FROM get_ip_classification(CAST(:ip_addr AS inet))"),
                {"ip_addr": ip_str},
            )
            row = result.fetchone()

            if row and row.rule_id is not None:
                return {
                    "rule_id": row.rule_id,
                    "rule_name": row.rule_name,
                    "environment": row.environment,
                    "datacenter": row.datacenter,
                    "location": row.location,
                    "asset_type": row.asset_type,
                    "is_internal": row.is_internal,
                    "default_owner": row.default_owner,
                    "default_team": row.default_team,
                }
        except Exception as e:
            # Log but don't fail asset creation if classification fails
            logger.warning(
                "Failed to get CIDR classification",
                ip=ip_str,
                error=str(e),
            )

        return None

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
        # First check CIDR classification rules
        cidr_class = await self._get_cidr_classification(db, ip_str)

        # Determine if internal or external
        # CIDR rules take priority, then fall back to RFC 1918 check
        if cidr_class and cidr_class.get("is_internal") is not None:
            is_internal = cidr_class["is_internal"]
        else:
            is_internal = self._classifier.is_private(ip_str)

        # Generate name
        if hostname:
            name = hostname.split(".")[0]
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

        # Apply CIDR classification for location if available
        if cidr_class and cidr_class.get("location"):
            city = cidr_class["location"]

        # Get environment and datacenter from CIDR rules
        environment = cidr_class.get("environment") if cidr_class else None
        datacenter = cidr_class.get("datacenter") if cidr_class else None
        owner = cidr_class.get("default_owner") if cidr_class else None
        team = cidr_class.get("default_team") if cidr_class else None

        # Generate a new UUID for the insert
        new_id = uuid_module.uuid4()

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
            environment=environment,
            datacenter=datacenter,
            owner=owner,
            team=team,
        ).on_conflict_do_nothing(index_elements=['ip_address'])

        result = await db.execute(stmt)

        # Check if we inserted a new row
        if result.rowcount > 0:
            await db.flush()
            logger.info(
                "Created new asset",
                asset_id=str(new_id),
                ip=ip_str,
                hostname=hostname,
                is_internal=is_internal,
                cidr_rule=cidr_class.get("rule_name") if cidr_class else None,
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

        # IMPORTANT: Always acquire locks in sorted order to prevent deadlocks
        # If two workers process flows A→B and B→A simultaneously, they could
        # deadlock if locks are acquired in different orders.
        need_src = src_asset_id is None
        need_dst = dst_asset_id is None

        if need_src and need_dst:
            # Need to create both - acquire locks in sorted order
            if src_ip <= dst_ip:
                src_asset_id = await self.get_or_create_asset(db, src_ip, src_hostname)
                dst_asset_id = await self.get_or_create_asset(db, dst_ip, dst_hostname)
            else:
                dst_asset_id = await self.get_or_create_asset(db, dst_ip, dst_hostname)
                src_asset_id = await self.get_or_create_asset(db, src_ip, src_hostname)
        elif need_src:
            src_asset_id = await self.get_or_create_asset(db, src_ip, src_hostname)
        elif need_dst:
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
