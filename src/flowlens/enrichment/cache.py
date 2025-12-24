"""Caching utilities for enrichment service.

Provides memory-based caching with TTL support, with optional
Redis backend for distributed deployments.
"""

import asyncio
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import DNS_CACHE_HITS, DNS_CACHE_SIZE

logger = get_logger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Cache entry with TTL tracking."""

    value: V
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.utcnow() > self.expires_at


class BaseCache(ABC, Generic[K, V]):
    """Abstract base class for caches."""

    @abstractmethod
    async def get(self, key: K) -> V | None:
        """Get value from cache."""
        ...

    @abstractmethod
    async def set(self, key: K, value: V, ttl: int | None = None) -> None:
        """Set value in cache with optional TTL."""
        ...

    @abstractmethod
    async def delete(self, key: K) -> None:
        """Delete value from cache."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from cache."""
        ...

    @abstractmethod
    def size(self) -> int:
        """Get current cache size."""
        ...


class MemoryCache(BaseCache[K, V]):
    """In-memory LRU cache with TTL support.

    Thread-safe implementation using asyncio locks.
    Suitable for single-instance deployments.
    """

    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: int = 3600,
        name: str = "cache",
    ) -> None:
        """Initialize memory cache.

        Args:
            max_size: Maximum number of entries.
            default_ttl: Default TTL in seconds.
            name: Cache name for metrics.
        """
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._name = name
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: K) -> V | None:
        """Get value from cache.

        Moves accessed entry to end (LRU behavior).
        Returns None if not found or expired.
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end for LRU
            self._cache.move_to_end(key)
            self._hits += 1
            DNS_CACHE_HITS.inc()

            return entry.value

    async def set(self, key: K, value: V, ttl: int | None = None) -> None:
        """Set value in cache.

        Evicts oldest entries if cache is full.
        """
        ttl = ttl or self._default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        async with self._lock:
            # Remove if exists to update position
            if key in self._cache:
                del self._cache[key]

            # Evict oldest entries if full
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            DNS_CACHE_SIZE.set(len(self._cache))

    async def delete(self, key: K) -> None:
        """Delete entry from cache."""
        async with self._lock:
            self._cache.pop(key, None)
            DNS_CACHE_SIZE.set(len(self._cache))

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()
            DNS_CACHE_SIZE.set(0)

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "name": self._name,
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
        }

    async def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns number of entries removed.
        """
        removed = 0
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1

            if removed > 0:
                DNS_CACHE_SIZE.set(len(self._cache))
                logger.debug(
                    "Cleaned up expired cache entries",
                    cache=self._name,
                    removed=removed,
                )

        return removed


class RedisCache(BaseCache[str, str]):
    """Redis-backed cache for distributed deployments.

    Requires redis[hiredis] package.
    """

    def __init__(
        self,
        default_ttl: int = 3600,
        key_prefix: str = "flowlens:",
        name: str = "redis_cache",
    ) -> None:
        """Initialize Redis cache.

        Args:
            default_ttl: Default TTL in seconds.
            key_prefix: Prefix for all keys.
            name: Cache name for metrics.
        """
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
        self._name = name
        self._client: Any = None

    async def _get_client(self) -> Any:
        """Get or create Redis client."""
        if self._client is None:
            settings = get_settings()
            if not settings.redis.enabled:
                raise RuntimeError("Redis is not enabled")

            import redis.asyncio as redis

            self._client = redis.from_url(
                settings.redis.url,
                encoding="utf-8",
                decode_responses=True,
            )

        return self._client

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> str | None:
        """Get value from Redis."""
        try:
            client = await self._get_client()
            value = await client.get(self._make_key(key))
            return value
        except Exception as e:
            logger.warning("Redis get failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set value in Redis with TTL."""
        ttl = ttl or self._default_ttl
        try:
            client = await self._get_client()
            await client.setex(self._make_key(key), ttl, value)
        except Exception as e:
            logger.warning("Redis set failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """Delete value from Redis."""
        try:
            client = await self._get_client()
            await client.delete(self._make_key(key))
        except Exception as e:
            logger.warning("Redis delete failed", key=key, error=str(e))

    async def clear(self) -> None:
        """Clear all entries with prefix."""
        try:
            client = await self._get_client()
            keys = await client.keys(f"{self._key_prefix}*")
            if keys:
                await client.delete(*keys)
        except Exception as e:
            logger.warning("Redis clear failed", error=str(e))

    def size(self) -> int:
        """Get approximate cache size (not supported efficiently in Redis)."""
        return -1  # Unknown

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None


def get_cache(
    cache_type: str = "memory",
    **kwargs: Any,
) -> BaseCache:
    """Factory function to create appropriate cache.

    Args:
        cache_type: Type of cache ("memory" or "redis").
        **kwargs: Cache-specific arguments.

    Returns:
        Cache instance.
    """
    settings = get_settings()

    if cache_type == "redis" and settings.redis.enabled:
        return RedisCache(**kwargs)
    else:
        return MemoryCache(**kwargs)
