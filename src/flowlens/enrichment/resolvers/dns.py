"""DNS resolver for reverse hostname lookup.

Provides async DNS resolution with caching and rate limiting.
"""

import asyncio
from ipaddress import IPv4Address, IPv6Address
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.reversename

from flowlens.common.config import EnrichmentSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import DNS_LOOKUPS
from flowlens.enrichment.cache import MemoryCache, get_cache

logger = get_logger(__name__)


class DNSResolver:
    """Async DNS resolver with caching.

    Performs reverse DNS lookups to get hostnames from IP addresses.
    Uses TTL-based caching to minimize DNS queries.
    """

    def __init__(self, settings: EnrichmentSettings | None = None) -> None:
        """Initialize DNS resolver.

        Args:
            settings: Enrichment settings. Uses global settings if not provided.
        """
        if settings is None:
            settings = get_settings().enrichment

        self._timeout = settings.dns_timeout
        self._cache = get_cache(
            cache_type="memory",
            max_size=settings.dns_cache_size,
            default_ttl=settings.dns_cache_ttl,
            name="dns",
        )

        # Create resolver
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.timeout = self._timeout
        self._resolver.lifetime = self._timeout * 2

        # Configure custom DNS servers if provided
        if settings.dns_servers:
            self._resolver.nameservers = settings.dns_servers

        # Semaphore to limit concurrent lookups
        self._semaphore = asyncio.Semaphore(100)

        # Track in-flight lookups to prevent duplicate requests
        self._in_flight: dict[str, asyncio.Future[str | None]] = {}
        self._lock = asyncio.Lock()

    async def resolve(
        self,
        ip_address: IPv4Address | IPv6Address | str,
    ) -> str | None:
        """Resolve IP address to hostname.

        Args:
            ip_address: IP address to resolve.

        Returns:
            Hostname if found, None otherwise.
        """
        ip_str = str(ip_address)

        # Check cache first
        cached = await self._cache.get(ip_str)
        if cached is not None:
            return cached if cached != "" else None

        # Check for in-flight request
        async with self._lock:
            if ip_str in self._in_flight:
                # Wait for existing request
                return await self._in_flight[ip_str]

            # Create new future for this lookup
            future: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
            self._in_flight[ip_str] = future

        try:
            # Perform lookup with semaphore
            async with self._semaphore:
                hostname = await self._do_lookup(ip_str)

            # Cache result (empty string for negative cache)
            await self._cache.set(ip_str, hostname or "")

            # Complete the future
            future.set_result(hostname)
            return hostname

        except Exception as e:
            # Cache negative result
            await self._cache.set(ip_str, "")
            future.set_result(None)
            logger.debug("DNS lookup failed", ip=ip_str, error=str(e))
            return None

        finally:
            # Remove from in-flight
            async with self._lock:
                self._in_flight.pop(ip_str, None)

    async def _do_lookup(self, ip_str: str) -> str | None:
        """Perform actual DNS lookup.

        Args:
            ip_str: IP address string.

        Returns:
            Hostname if found.
        """
        try:
            # Create reverse name
            rev_name = dns.reversename.from_address(ip_str)

            # Query PTR record
            answers = await self._resolver.resolve(rev_name, "PTR")

            if answers:
                # Get first answer, strip trailing dot
                hostname = str(answers[0]).rstrip(".")
                DNS_LOOKUPS.labels(status="success").inc()
                return hostname

            DNS_LOOKUPS.labels(status="nxdomain").inc()
            return None

        except dns.asyncresolver.NXDOMAIN:
            DNS_LOOKUPS.labels(status="nxdomain").inc()
            return None

        except dns.asyncresolver.NoAnswer:
            DNS_LOOKUPS.labels(status="noanswer").inc()
            return None

        except dns.exception.Timeout:
            DNS_LOOKUPS.labels(status="timeout").inc()
            return None

        except Exception as e:
            DNS_LOOKUPS.labels(status="error").inc()
            logger.debug("DNS error", ip=ip_str, error=str(e))
            return None

    async def resolve_batch(
        self,
        ip_addresses: list[IPv4Address | IPv6Address | str],
    ) -> dict[str, str | None]:
        """Resolve multiple IP addresses concurrently.

        Args:
            ip_addresses: List of IP addresses to resolve.

        Returns:
            Dictionary mapping IP strings to hostnames.
        """
        tasks = [self.resolve(ip) for ip in ip_addresses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            str(ip): (
                result if isinstance(result, (str, type(None))) else None
            )
            for ip, result in zip(ip_addresses, results)
        }

    @property
    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if isinstance(self._cache, MemoryCache):
            return self._cache.stats
        return {"size": self._cache.size()}

    async def cleanup(self) -> None:
        """Cleanup expired cache entries."""
        if isinstance(self._cache, MemoryCache):
            await self._cache.cleanup_expired()
