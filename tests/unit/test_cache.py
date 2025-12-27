"""Unit tests for API cache."""

import time
from unittest.mock import patch

import pytest

from flowlens.api.cache import (
    CacheEntry,
    SimpleCache,
    get_topology_cache,
    invalidate_topology_cache,
)


@pytest.mark.unit
class TestCacheEntry:
    """Test cases for CacheEntry."""

    def test_not_expired(self):
        """Test entry is not expired when within TTL."""
        now = time.time()
        entry = CacheEntry(
            value="test",
            expires_at=now + 60,
            created_at=now,
        )

        assert entry.is_expired(now) is False

    def test_expired(self):
        """Test entry is expired after TTL."""
        now = time.time()
        entry = CacheEntry(
            value="test",
            expires_at=now - 1,
            created_at=now - 61,
        )

        assert entry.is_expired(now) is True

    def test_default_created_at(self):
        """Test default created_at is set."""
        entry = CacheEntry(value="test", expires_at=time.time() + 60)
        assert entry.created_at > 0


@pytest.mark.unit
class TestSimpleCache:
    """Test cases for SimpleCache."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance for testing."""
        return SimpleCache(default_ttl=60, max_entries=100)

    def test_make_key_dict(self, cache):
        """Test key generation from dict."""
        key = cache.make_key("test", {"a": 1, "b": 2})
        assert key.startswith("test:")
        assert len(key) > 10

    def test_make_key_consistent(self, cache):
        """Test key generation is consistent."""
        data = {"z": 3, "a": 1}
        key1 = cache.make_key("test", data)
        key2 = cache.make_key("test", data)

        assert key1 == key2

    def test_make_key_different_data(self, cache):
        """Test different data produces different keys."""
        key1 = cache.make_key("test", {"a": 1})
        key2 = cache.make_key("test", {"a": 2})

        assert key1 != key2

    def test_make_key_string(self, cache):
        """Test key generation from string."""
        key = cache.make_key("test", "some-string")
        assert key.startswith("test:")

    def test_get_miss(self, cache):
        """Test get returns None on cache miss."""
        result = cache.get("nonexistent")
        assert result is None

    def test_set_and_get(self, cache):
        """Test set and get operations."""
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"

    def test_get_expired(self):
        """Test get returns None for expired entry."""
        cache = SimpleCache(default_ttl=60, max_entries=100)

        # Manually add an expired entry
        now = time.time()
        cache._cache["key1"] = CacheEntry(
            value="value1",
            expires_at=now - 1,  # Already expired
            created_at=now - 61,
        )

        result = cache.get("key1")
        assert result is None

    def test_set_with_custom_ttl(self, cache):
        """Test set with custom TTL."""
        cache.set("key1", "value1", ttl=1)

        # Should exist immediately
        assert cache.get("key1") == "value1"

        # Wait for expiry
        time.sleep(1.1)

        # Should be gone
        assert cache.get("key1") is None

    def test_delete_existing(self, cache):
        """Test deleting existing key."""
        cache.set("key1", "value1")
        result = cache.delete("key1")

        assert result is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        """Test deleting nonexistent key."""
        result = cache.delete("nonexistent")
        assert result is False

    def test_clear(self, cache):
        """Test clearing all entries."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        count = cache.clear()

        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_invalidate_prefix(self, cache):
        """Test invalidating by prefix."""
        cache.set("topology:graph:abc", "value1")
        cache.set("topology:graph:def", "value2")
        cache.set("other:key", "value3")

        count = cache.invalidate_prefix("topology")

        assert count == 2
        assert cache.get("topology:graph:abc") is None
        assert cache.get("topology:graph:def") is None
        assert cache.get("other:key") == "value3"

    def test_stats(self, cache):
        """Test statistics tracking."""
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats

        assert stats["entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == pytest.approx(66.67, rel=0.01)

    def test_eviction(self):
        """Test eviction when at capacity."""
        cache = SimpleCache(default_ttl=60, max_entries=5)

        # Fill cache
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")

        assert len(cache._cache) == 5

        # Add one more (should trigger eviction)
        cache.set("key_new", "value_new")

        # Should have evicted at least 1
        assert len(cache._cache) <= 5

    def test_disabled_cache(self):
        """Test cache doesn't store when TTL is 0."""
        cache = SimpleCache(default_ttl=0, max_entries=100)

        # When default TTL is 0, set() without explicit TTL shouldn't store
        cache.set("key1", "value1")  # Uses default TTL of 0

        # Entry should not be stored
        assert len(cache._cache) == 0

    def test_explicit_ttl_overrides_default(self):
        """Test explicit TTL overrides default of 0."""
        cache = SimpleCache(default_ttl=0, max_entries=100)

        # Explicit TTL should work even with default_ttl=0
        cache.set("key1", "value1", ttl=60)

        assert cache.get("key1") == "value1"

    def test_cleanup_expired(self, cache):
        """Test cleanup of expired entries."""
        now = time.time()

        # Add some entries
        cache._cache["fresh"] = CacheEntry(
            value="fresh",
            expires_at=now + 60,
            created_at=now,
        )
        cache._cache["stale"] = CacheEntry(
            value="stale",
            expires_at=now - 1,
            created_at=now - 61,
        )

        removed = cache._cleanup_expired(now)

        assert removed == 1
        assert "fresh" in cache._cache
        assert "stale" not in cache._cache


@pytest.mark.unit
class TestTopologyCacheHelpers:
    """Test cases for topology cache helper functions."""

    def test_get_topology_cache(self):
        """Test getting topology cache instance."""
        cache = get_topology_cache()

        assert isinstance(cache, SimpleCache)

    def test_get_topology_cache_singleton(self):
        """Test topology cache is singleton."""
        cache1 = get_topology_cache()
        cache2 = get_topology_cache()

        assert cache1 is cache2

    def test_invalidate_topology_cache(self):
        """Test invalidating topology cache."""
        cache = get_topology_cache()

        # Add some entries
        cache.set("topology:abc", "value1")
        cache.set("topology:def", "value2")

        count = invalidate_topology_cache()

        assert count >= 2  # May have entries from other tests
        assert cache.get("topology:abc") is None
