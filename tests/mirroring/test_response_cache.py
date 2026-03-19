"""Tests for response cache system (STORY-DMG-2.1)."""

import threading
import time

import pytest

from stuntdouble.mirroring.cache import ResponseCache


class TestResponseCacheBasics:
    """Basic cache operations tests."""

    @pytest.fixture
    def cache(self):
        """Create temporary cache for testing."""
        yield ResponseCache(ttl_seconds=5)

    def test_cache_initialization(self):
        """Test cache initializes with correct defaults."""
        cache = ResponseCache()

        assert cache.ttl_seconds == 3600  # 1 hour default
        assert cache.max_entries == 10000
        assert len(cache._cache) == 0

    def test_cache_set_and_get(self, cache):
        """Test basic cache set and get operations."""
        tool_name = "get_customer"
        params = {"id": "123"}
        response = {"name": "John Doe", "email": "john@example.com"}

        # Set cache
        cache.set(tool_name, params, response)

        # Get from cache
        cached = cache.get(tool_name, params)

        assert cached is not None
        assert cached == response
        assert cached["name"] == "John Doe"

    def test_cache_miss_returns_none(self, cache):
        """Test cache miss returns None."""
        result = cache.get("nonexistent_tool", {"id": "999"})

        assert result is None

    def test_cache_returns_copy_not_reference(self, cache):
        """Test cache returns copy to prevent mutation."""
        tool_name = "get_user"
        params = {"id": "1"}
        original_response = {"name": "Alice", "age": 30}

        cache.set(tool_name, params, original_response)

        # Get cached response and mutate it
        cached1 = cache.get(tool_name, params)
        cached1["name"] = "Modified"

        # Get again - should be unchanged
        cached2 = cache.get(tool_name, params)

        assert cached2["name"] == "Alice"  # Not "Modified"
        assert cached1 != cached2  # Different objects

    def test_different_params_different_keys(self, cache):
        """Test different parameters create different cache keys."""
        tool_name = "get_customer"
        params1 = {"id": "123"}
        params2 = {"id": "456"}
        response1 = {"name": "John"}
        response2 = {"name": "Jane"}

        cache.set(tool_name, params1, response1)
        cache.set(tool_name, params2, response2)

        # Should get different responses
        assert cache.get(tool_name, params1)["name"] == "John"
        assert cache.get(tool_name, params2)["name"] == "Jane"

    def test_same_params_same_key(self, cache):
        """Test same parameters (different order) create same cache key."""
        tool_name = "get_user"
        params1 = {"id": 1, "name": "Alice", "age": 30}
        params2 = {"age": 30, "name": "Alice", "id": 1}  # Different order

        # Generate cache keys
        key1 = cache._make_cache_key(tool_name, params1)
        key2 = cache._make_cache_key(tool_name, params2)

        # Should be identical
        assert key1 == key2


class TestCacheTTL:
    """Cache TTL (time-to-live) expiration tests."""

    def test_cache_ttl_expiration(self):
        """Test cache entries expire after TTL."""
        # Short TTL for testing
        cache = ResponseCache(ttl_seconds=1)

        tool_name = "get_customer"
        params = {"id": "123"}
        response = {"name": "John"}

        # Set cache
        cache.set(tool_name, params, response)

        # Should be in cache immediately
        assert cache.get(tool_name, params) is not None

        # Wait for TTL expiration
        time.sleep(1.5)

        # Should now be expired
        assert cache.get(tool_name, params) is None

    def test_cache_ttl_not_expired_within_window(self):
        """Test cache entries don't expire within TTL window."""
        cache = ResponseCache(ttl_seconds=10)

        tool_name = "get_customer"
        params = {"id": "123"}
        response = {"name": "John"}

        cache.set(tool_name, params, response)

        # Wait less than TTL
        time.sleep(0.5)

        # Should still be cached
        cached = cache.get(tool_name, params)
        assert cached is not None
        assert cached["name"] == "John"


class TestCacheClearing:
    """Cache clearing tests."""

    @pytest.fixture
    def cache(self):
        yield ResponseCache()

    def test_cache_clear_all(self, cache):
        """Test clearing entire cache."""
        # Add multiple entries
        cache.set("tool1", {"id": 1}, {"data": "a"})
        cache.set("tool2", {"id": 2}, {"data": "b"})
        cache.set("tool3", {"id": 3}, {"data": "c"})

        assert len(cache._cache) == 3

        # Clear all
        count = cache.clear()

        assert count == 3
        assert len(cache._cache) == 0

    def test_cache_clear_specific_tool(self, cache):
        """Test clearing cache for specific tool only."""
        # Add entries for different tools
        cache.set("get_customer", {"id": 1}, {"name": "John"})
        cache.set("get_customer", {"id": 2}, {"name": "Jane"})
        cache.set("get_product", {"id": 1}, {"name": "Widget"})
        cache.set("get_order", {"id": 1}, {"total": 100})

        assert len(cache._cache) == 4

        # Clear only customer tool
        count = cache.clear("get_customer")

        assert count == 2
        assert len(cache._cache) == 2

        # Verify customer cache cleared
        assert cache.get("get_customer", {"id": 1}) is None
        assert cache.get("get_customer", {"id": 2}) is None

        # Verify other tools intact
        assert cache.get("get_product", {"id": 1}) is not None
        assert cache.get("get_order", {"id": 1}) is not None


class TestCacheEviction:
    """Cache LRU eviction tests."""

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache reaches max_entries."""
        # Small cache for testing
        cache = ResponseCache(max_entries=3)

        # Fill cache to capacity
        cache.set("tool", {"id": 1}, {"data": "first"})
        time.sleep(0.01)  # Ensure different timestamps
        cache.set("tool", {"id": 2}, {"data": "second"})
        time.sleep(0.01)
        cache.set("tool", {"id": 3}, {"data": "third"})

        assert len(cache._cache) == 3

        # Add 4th entry - should evict oldest (id=1)
        time.sleep(0.01)
        cache.set("tool", {"id": 4}, {"data": "fourth"})

        assert len(cache._cache) == 3  # Still at max

        # First entry should be evicted
        assert cache.get("tool", {"id": 1}) is None

        # Others should remain
        assert cache.get("tool", {"id": 2}) is not None
        assert cache.get("tool", {"id": 3}) is not None
        assert cache.get("tool", {"id": 4}) is not None


class TestCacheStatistics:
    """Cache statistics tests."""

    @pytest.fixture
    def cache(self):
        yield ResponseCache()

    def test_cache_stats_initial(self, cache):
        """Test initial cache statistics."""
        stats = cache.stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_requests"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["max_entries"] == 10000
        assert stats["ttl_seconds"] == 3600

    def test_cache_stats_after_operations(self, cache):
        """Test cache statistics after various operations."""
        # Add entry
        cache.set("tool", {"id": 1}, {"data": "test"})

        # 2 hits
        cache.get("tool", {"id": 1})
        cache.get("tool", {"id": 1})

        # 3 misses
        cache.get("tool", {"id": 2})
        cache.get("tool", {"id": 3})
        cache.get("tool", {"id": 4})

        stats = cache.stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 3
        assert stats["total_requests"] == 5
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.4  # 2/5 = 0.4

    def test_cache_stats_hit_rate_calculation(self, cache):
        """Test hit rate calculation."""
        # Add entries
        for i in range(5):
            cache.set("tool", {"id": i}, {"data": f"item_{i}"})

        # 7 hits
        for _ in range(7):
            cache.get("tool", {"id": 0})

        # 3 misses
        for i in range(10, 13):
            cache.get("tool", {"id": i})

        stats = cache.stats()

        assert stats["hits"] == 7
        assert stats["misses"] == 3
        assert stats["hit_rate"] == 0.7  # 7/10 = 0.7


class TestCacheThreadSafety:
    """Thread safety tests."""

    def test_cache_thread_safety(self):
        """Test cache is thread-safe for concurrent access."""
        cache = ResponseCache()
        errors = []

        def writer(thread_id: int):
            """Write entries to cache."""
            try:
                for i in range(50):
                    cache.set(
                        f"tool_{thread_id}",
                        {"id": i},
                        {"data": f"thread_{thread_id}_item_{i}"},
                    )
            except Exception as e:
                errors.append(f"Writer {thread_id}: {e}")

        def reader(thread_id: int):
            """Read entries from cache."""
            try:
                for i in range(50):
                    # Try to read from various tools
                    for tool_id in range(5):
                        cache.get(f"tool_{tool_id}", {"id": i})
            except Exception as e:
                errors.append(f"Reader {thread_id}: {e}")

        # Create threads
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"

        # Cache should have entries
        assert len(cache._cache) > 0

    def test_cache_concurrent_writes_same_key(self):
        """Test concurrent writes to same key don't cause issues."""
        cache = ResponseCache()

        def write_same_key(value: int):
            """Write to same cache key."""
            cache.set("shared_tool", {"id": "shared"}, {"value": value})
            time.sleep(0.001)  # Small delay

        # Multiple threads writing to same key
        threads = [threading.Thread(target=write_same_key, args=(i,)) for i in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have exactly one entry (last write wins)
        assert len(cache._cache) == 1

        # Should be retrievable
        result = cache.get("shared_tool", {"id": "shared"})
        assert result is not None
        assert "value" in result


class TestCacheDeterminism:
    """Cache key determinism tests."""

    @pytest.fixture
    def cache(self):
        yield ResponseCache()

    def test_cache_key_deterministic(self, cache):
        """Test cache keys are deterministic."""
        params = {"name": "Alice", "age": 30, "id": 1}

        # Generate key multiple times
        key1 = cache._make_cache_key("tool", params)
        key2 = cache._make_cache_key("tool", params)
        key3 = cache._make_cache_key("tool", params)

        # All should be identical
        assert key1 == key2 == key3

    def test_cache_key_param_order_independent(self, cache):
        """Test cache key is independent of parameter order."""
        params1 = {"a": 1, "b": 2, "c": 3}
        params2 = {"c": 3, "a": 1, "b": 2}
        params3 = {"b": 2, "c": 3, "a": 1}

        key1 = cache._make_cache_key("tool", params1)
        key2 = cache._make_cache_key("tool", params2)
        key3 = cache._make_cache_key("tool", params3)

        # All should be identical
        assert key1 == key2 == key3

    def test_cache_key_different_tools_different_keys(self, cache):
        """Test different tool names create different keys."""
        params = {"id": 1}

        key1 = cache._make_cache_key("tool1", params)
        key2 = cache._make_cache_key("tool2", params)

        assert key1 != key2

    def test_cache_key_format(self, cache):
        """Test cache key has expected format."""
        key = cache._make_cache_key("get_customer", {"id": 123})

        # Should be "tool_name:hash"
        assert ":" in key
        parts = key.split(":")
        assert len(parts) == 2
        assert parts[0] == "get_customer"
        assert len(parts[1]) == 32  # MD5 hash length


class TestCacheRepr:
    """Test cache string representation."""

    def test_cache_repr(self):
        """Test cache __repr__ method."""
        cache = ResponseCache(ttl_seconds=60, max_entries=100)

        # Add some entries
        cache.set("tool", {"id": 1}, {"data": "test"})
        cache.get("tool", {"id": 1})  # Hit
        cache.get("tool", {"id": 2})  # Miss

        repr_str = repr(cache)

        assert "ResponseCache" in repr_str
        assert "size=1/100" in repr_str
        assert "hit_rate=50" in repr_str  # 50% (1 hit, 1 miss)
        assert "ttl=60s" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
