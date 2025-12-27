"""Simple in-memory cache for API responses.

Provides TTL-based caching for expensive queries like topology graphs.
For production multi-instance deployments, replace with Redis.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """A cached value with expiration time."""

    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self, now: float | None = None) -> bool:
        """Check if entry has expired."""
        now = now or time.time()
        return now >= self.expires_at


class SimpleCache:
    """Simple TTL-based in-memory cache.

    Thread-safe for read operations. Writes may have minor race conditions
    but this is acceptable for caching purposes (worst case: duplicate computation).

    Usage:
        cache = SimpleCache(default_ttl=30)

        # Check cache
        key = cache.make_key("topology", filters.dict())
        if cached := cache.get(key):
            return cached

        # Compute and cache
        result = expensive_operation()
        cache.set(key, result)
        return result
    """

    def __init__(
        self,
        default_ttl: int | None = None,
        max_entries: int = 1000,
        cleanup_interval: float = 60.0,
    ) -> None:
        """Initialize cache.

        Args:
            default_ttl: Default TTL in seconds. None to use settings.
            max_entries: Maximum entries before eviction.
            cleanup_interval: Seconds between cleanup runs.
        """
        settings = get_settings()
        # Use explicit default_ttl if provided (even if 0), otherwise use settings
        self.default_ttl = default_ttl if default_ttl is not None else settings.api.topology_cache_ttl_seconds
        self.max_entries = max_entries
        self.cleanup_interval = cleanup_interval

        self._cache: dict[str, CacheEntry] = {}
        self._last_cleanup = time.time()

        # Statistics
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(prefix: str, data: dict | list | str) -> str:
        """Create a cache key from prefix and data.

        Args:
            prefix: Key prefix (e.g., "topology", "blast_radius").
            data: Data to hash (dict, list, or string).

        Returns:
            Cache key string.
        """
        if isinstance(data, str):
            content = data
        else:
            # Sort keys for consistent hashing
            content = json.dumps(data, sort_keys=True, default=str)

        # Use MD5 for speed (not security-sensitive)
        hash_value = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_value}"

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            # Remove expired entry
            self._cache.pop(key, None)
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with TTL.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: TTL in seconds. Uses default if not specified.
        """
        # Check if caching is disabled
        if self.default_ttl == 0 and ttl is None:
            return

        ttl = ttl or self.default_ttl
        if ttl <= 0:
            return

        now = time.time()

        # Periodic cleanup
        self._maybe_cleanup(now)

        # Evict if at capacity
        if len(self._cache) >= self.max_entries:
            self._evict_oldest()

        self._cache[key] = CacheEntry(
            value=value,
            expires_at=now + ttl,
            created_at=now,
        )

    def delete(self, key: str) -> bool:
        """Delete a key from cache.

        Args:
            key: Cache key.

        Returns:
            True if key existed, False otherwise.
        """
        return self._cache.pop(key, None) is not None

    def clear(self) -> int:
        """Clear all entries from cache.

        Returns:
            Number of entries cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate all keys with given prefix.

        Args:
            prefix: Key prefix to match.

        Returns:
            Number of entries invalidated.
        """
        keys_to_delete = [k for k in self._cache if k.startswith(f"{prefix}:")]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
            "default_ttl": self.default_ttl,
        }

    def _maybe_cleanup(self, now: float) -> None:
        """Run cleanup if interval has passed."""
        if now - self._last_cleanup < self.cleanup_interval:
            return

        self._last_cleanup = now
        self._cleanup_expired(now)

    def _cleanup_expired(self, now: float) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired(now)
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(
                "Cache cleanup completed",
                expired_count=len(expired_keys),
                remaining_count=len(self._cache),
            )

        return len(expired_keys)

    def _evict_oldest(self) -> None:
        """Evict oldest entries when at capacity."""
        # Find oldest 10% of entries
        evict_count = max(1, self.max_entries // 10)

        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].created_at,
        )

        for key, _ in sorted_entries[:evict_count]:
            del self._cache[key]

        logger.debug(
            "Cache eviction completed",
            evicted_count=evict_count,
            remaining_count=len(self._cache),
        )


# Global cache instance
_topology_cache: SimpleCache | None = None


def get_topology_cache() -> SimpleCache:
    """Get the global topology cache instance."""
    global _topology_cache
    if _topology_cache is None:
        settings = get_settings()
        _topology_cache = SimpleCache(
            default_ttl=settings.api.topology_cache_ttl_seconds,
            max_entries=500,  # Topology responses can be large
        )
    return _topology_cache


def invalidate_topology_cache() -> int:
    """Invalidate all topology cache entries.

    Call this when assets or dependencies change.

    Returns:
        Number of entries invalidated.
    """
    cache = get_topology_cache()
    return cache.invalidate_prefix("topology")
