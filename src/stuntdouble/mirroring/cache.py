# ABOUTME: Provides caching utilities for generated mock responses in the mirroring workflow.
# ABOUTME: Keeps repeated dynamic generations stable and avoids regenerating identical responses.
"""Response caching for dynamic mock generation.

Provides thread-safe in-memory caching of dynamically generated mock responses
to ensure consistency across multiple calls with the same inputs.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Thread-safe in-memory cache for dynamic mock responses.

    Caches responses based on tool name and input parameters,
    ensuring consistent behavior across multiple calls with
    the same inputs.

    Features:
    - Deterministic cache keys from tool name + parameters
    - TTL (time-to-live) expiration
    - LRU eviction when at capacity
    - Thread-safe for concurrent access
    - Cache statistics tracking

    Example:
        >>> cache = ResponseCache()
        >>> cache.set("get_customer", {"id": "123"}, {"name": "John Doe"})
        >>> response = cache.get("get_customer", {"id": "123"})
        >>> print(response)  # {"name": "John Doe"}
        >>> stats = cache.stats()
        >>> print(stats["hit_rate"])  # 1.0 (100% hit rate)
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_entries: int = 10000,
    ):
        """
        Initialize response cache.

        Args:
            ttl_seconds: Time-to-live in seconds (default: 1 hour)
            max_entries: Maximum cache entries before LRU eviction (default: 10000)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # In-memory cache: {cache_key: (response, timestamp)}
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = threading.RLock()

        # Statistics
        self._hits = 0
        self._misses = 0

        logger.info(f"ResponseCache initialized (in-memory, TTL: {ttl_seconds}s, max: {max_entries})")

    def get(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """
        Get cached response for tool call.

        Args:
            tool_name: Name of the tool
            params: Input parameters

        Returns:
            Cached response if found and not expired, None otherwise

        Example:
            >>> response = cache.get("get_customer", {"id": "123"})
            >>> if response:
            ...     print("Cache hit!")
        """
        cache_key = self._make_cache_key(tool_name, params)

        with self._lock:
            if cache_key not in self._cache:
                self._misses += 1
                logger.debug(f"Cache miss for {tool_name} (key: {cache_key[:16]}...)")
                return None

            response, timestamp = self._cache[cache_key]

            # Check TTL
            age = time.time() - timestamp
            if age > self.ttl_seconds:
                del self._cache[cache_key]
                self._misses += 1
                logger.debug(f"Cache expired for {tool_name} (age: {age:.1f}s)")
                return None

            self._hits += 1
            logger.debug(f"Cache hit for {tool_name} (age: {age:.1f}s)")
            return response.copy()  # Return copy to prevent mutation

    def set(self, tool_name: str, params: dict[str, Any], response: dict[str, Any]) -> None:
        """
        Store response in cache.

        Args:
            tool_name: Name of the tool
            params: Input parameters
            response: Response to cache

        Example:
            >>> cache.set("get_customer", {"id": "123"}, {"name": "John"})
        """
        cache_key = self._make_cache_key(tool_name, params)

        with self._lock:
            # LRU eviction if at capacity
            if len(self._cache) >= self.max_entries:
                # Find oldest entry
                oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
                del self._cache[oldest_key]
                logger.debug(f"Cache evicted (LRU): {oldest_key[:32]}...")

            self._cache[cache_key] = (response.copy(), time.time())
            logger.debug(f"Cache set for {tool_name} (key: {cache_key[:16]}...)")

    def clear(self, tool_name: str | None = None) -> int:
        """
        Clear cache entries.

        Args:
            tool_name: Clear only entries for this tool (None = clear all)

        Returns:
            Number of entries cleared

        Example:
            >>> cache.clear("get_customer")  # Clear only customer tool cache
            3
            >>> cache.clear()  # Clear entire cache
            47
        """
        with self._lock:
            if tool_name is None:
                count = len(self._cache)
                self._cache.clear()
                self._hits = 0
                self._misses = 0
                logger.info(f"Cleared all cache ({count} entries)")
                return count
            else:
                # Clear entries starting with tool_name
                prefix = f"{tool_name}:"
                to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
                for key in to_delete:
                    del self._cache[key]
                logger.info(f"Cleared {len(to_delete)} entries for {tool_name}")
                return len(to_delete)

    def stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hits, misses, size, hit_rate, and configuration

        Example:
            >>> stats = cache.stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.1%}")
            Hit rate: 87.5%
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "size": len(self._cache),
                "max_entries": self.max_entries,
                "hit_rate": round(hit_rate, 3),
                "ttl_seconds": self.ttl_seconds,
            }

    def _make_cache_key(self, tool_name: str, params: dict[str, Any]) -> str:
        """
        Create deterministic cache key from tool name and params.

        Ensures that identical tool calls (same name + params) produce
        the same cache key, regardless of parameter order.

        Args:
            tool_name: Tool name
            params: Input parameters

        Returns:
            Cache key string (format: "tool_name:hash")

        Example:
            >>> key1 = cache._make_cache_key("get_user", {"id": 1, "name": "Alice"})
            >>> key2 = cache._make_cache_key("get_user", {"name": "Alice", "id": 1})
            >>> assert key1 == key2  # Same key regardless of param order
        """
        # Sort params for deterministic key generation
        params_json = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_json.encode()).hexdigest()
        return f"{tool_name}:{params_hash}"

    def __repr__(self) -> str:
        """String representation of cache."""
        stats = self.stats()
        return (
            f"ResponseCache(size={stats['size']}/{stats['max_entries']}, "
            f"hit_rate={stats['hit_rate']:.1%}, ttl={self.ttl_seconds}s)"
        )


__all__ = ["ResponseCache"]
