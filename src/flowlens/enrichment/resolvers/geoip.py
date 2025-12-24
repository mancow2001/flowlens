"""GeoIP resolver using MaxMind database.

Provides geographic location lookup for IP addresses.
Requires MaxMind GeoLite2 or GeoIP2 database file.
"""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Any

from flowlens.common.config import EnrichmentSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import GEOIP_LOOKUPS

logger = get_logger(__name__)


@dataclass
class GeoIPResult:
    """Result of a GeoIP lookup."""

    country_code: str | None = None
    country_name: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    asn: int | None = None
    org: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city,
            "region": self.region,
            "postal_code": self.postal_code,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "asn": self.asn,
            "org": self.org,
        }


class GeoIPResolver:
    """GeoIP resolver using MaxMind mmdb files.

    Supports GeoLite2-City or GeoIP2-City databases.
    Database file must be provided via configuration.
    """

    def __init__(self, settings: EnrichmentSettings | None = None) -> None:
        """Initialize GeoIP resolver.

        Args:
            settings: Enrichment settings with database path.
        """
        if settings is None:
            settings = get_settings().enrichment

        self._db_path = settings.geoip_database_path
        self._reader = None
        self._enabled = False

        if self._db_path and Path(self._db_path).exists():
            self._load_database()

    def _load_database(self) -> None:
        """Load the MaxMind database."""
        try:
            import maxminddb

            self._reader = maxminddb.open_database(str(self._db_path))
            self._enabled = True
            logger.info("GeoIP database loaded", path=str(self._db_path))

        except ImportError:
            logger.warning("maxminddb package not installed, GeoIP disabled")

        except Exception as e:
            logger.error("Failed to load GeoIP database", error=str(e))

    def lookup(
        self,
        ip_address: IPv4Address | IPv6Address | str,
    ) -> GeoIPResult | None:
        """Look up geographic info for an IP address.

        Args:
            ip_address: IP address to look up.

        Returns:
            GeoIPResult if found, None otherwise.
        """
        if not self._enabled or self._reader is None:
            return None

        ip_str = str(ip_address)

        try:
            data = self._reader.get(ip_str)

            if data is None:
                GEOIP_LOOKUPS.labels(status="not_found").inc()
                return None

            result = GeoIPResult()

            # Extract country info
            if "country" in data:
                result.country_code = data["country"].get("iso_code")
                names = data["country"].get("names", {})
                result.country_name = names.get("en")

            # Extract city info
            if "city" in data:
                names = data["city"].get("names", {})
                result.city = names.get("en")

            # Extract region/subdivision
            if "subdivisions" in data and data["subdivisions"]:
                names = data["subdivisions"][0].get("names", {})
                result.region = names.get("en")

            # Extract postal code
            if "postal" in data:
                result.postal_code = data["postal"].get("code")

            # Extract coordinates
            if "location" in data:
                result.latitude = data["location"].get("latitude")
                result.longitude = data["location"].get("longitude")
                result.timezone = data["location"].get("time_zone")

            # Extract ASN info (if ASN database is linked)
            if "autonomous_system_number" in data:
                result.asn = data["autonomous_system_number"]
            if "autonomous_system_organization" in data:
                result.org = data["autonomous_system_organization"]

            GEOIP_LOOKUPS.labels(status="success").inc()
            return result

        except Exception as e:
            GEOIP_LOOKUPS.labels(status="error").inc()
            logger.debug("GeoIP lookup failed", ip=ip_str, error=str(e))
            return None

    def lookup_batch(
        self,
        ip_addresses: list[IPv4Address | IPv6Address | str],
    ) -> dict[str, GeoIPResult | None]:
        """Look up multiple IP addresses.

        Args:
            ip_addresses: List of IP addresses.

        Returns:
            Dictionary mapping IP strings to results.
        """
        return {str(ip): self.lookup(ip) for ip in ip_addresses}

    @property
    def is_enabled(self) -> bool:
        """Check if GeoIP is enabled."""
        return self._enabled

    def close(self) -> None:
        """Close the database reader."""
        if self._reader:
            self._reader.close()
            self._reader = None
            self._enabled = False


class PrivateIPClassifier:
    """Classify IP addresses as internal/external.

    Uses RFC 1918 and other private/reserved ranges.
    """

    # Private IPv4 ranges
    PRIVATE_RANGES_V4 = [
        ("10.0.0.0", "10.255.255.255"),      # Class A
        ("172.16.0.0", "172.31.255.255"),    # Class B
        ("192.168.0.0", "192.168.255.255"),  # Class C
        ("127.0.0.0", "127.255.255.255"),    # Loopback
        ("169.254.0.0", "169.254.255.255"),  # Link-local
    ]

    # Special use ranges
    SPECIAL_RANGES_V4 = [
        ("0.0.0.0", "0.255.255.255"),        # "This" network
        ("100.64.0.0", "100.127.255.255"),   # Shared address space (CGNAT)
        ("192.0.0.0", "192.0.0.255"),        # IETF protocol assignments
        ("192.0.2.0", "192.0.2.255"),        # Documentation (TEST-NET-1)
        ("198.51.100.0", "198.51.100.255"),  # Documentation (TEST-NET-2)
        ("203.0.113.0", "203.0.113.255"),    # Documentation (TEST-NET-3)
        ("224.0.0.0", "239.255.255.255"),    # Multicast
        ("240.0.0.0", "255.255.255.255"),    # Reserved/Broadcast
    ]

    def __init__(self) -> None:
        """Initialize classifier with compiled ranges."""
        self._private_ranges = self._compile_ranges(self.PRIVATE_RANGES_V4)
        self._special_ranges = self._compile_ranges(self.SPECIAL_RANGES_V4)

    def _compile_ranges(
        self,
        ranges: list[tuple[str, str]],
    ) -> list[tuple[int, int]]:
        """Compile IP ranges to integer tuples for fast comparison."""
        compiled = []
        for start, end in ranges:
            start_int = int(IPv4Address(start))
            end_int = int(IPv4Address(end))
            compiled.append((start_int, end_int))
        return compiled

    def is_private(self, ip_address: IPv4Address | IPv6Address | str) -> bool:
        """Check if IP address is in a private range.

        Args:
            ip_address: IP address to check.

        Returns:
            True if private/internal.
        """
        try:
            if isinstance(ip_address, str):
                ip_address = IPv4Address(ip_address)

            if isinstance(ip_address, IPv6Address):
                # Check IPv6 private ranges
                return (
                    ip_address.is_private
                    or ip_address.is_loopback
                    or ip_address.is_link_local
                )

            ip_int = int(ip_address)

            for start, end in self._private_ranges:
                if start <= ip_int <= end:
                    return True

            return False

        except Exception:
            return False

    def is_special(self, ip_address: IPv4Address | IPv6Address | str) -> bool:
        """Check if IP is in a special/reserved range.

        Args:
            ip_address: IP address to check.

        Returns:
            True if special use address.
        """
        try:
            if isinstance(ip_address, str):
                ip_address = IPv4Address(ip_address)

            if isinstance(ip_address, IPv6Address):
                return ip_address.is_reserved or ip_address.is_multicast

            ip_int = int(ip_address)

            for start, end in self._special_ranges:
                if start <= ip_int <= end:
                    return True

            return False

        except Exception:
            return False

    def classify(
        self,
        ip_address: IPv4Address | IPv6Address | str,
    ) -> str:
        """Classify IP address type.

        Args:
            ip_address: IP address to classify.

        Returns:
            Classification string: "private", "special", or "public".
        """
        if self.is_private(ip_address):
            return "private"
        if self.is_special(ip_address):
            return "special"
        return "public"
