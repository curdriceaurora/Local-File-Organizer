"""LRU model cache with TTL-based expiration and thread safety.

Provides an in-memory cache for loaded AI models with automatic eviction
based on least-recently-used policy and time-to-live expiration.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from file_organizer.models.base import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics about cache usage.

    Attributes:
        hits: Number of cache hits (model found in cache).
        misses: Number of cache misses (model had to be loaded).
        evictions: Number of models evicted from cache.
        memory_usage_bytes: Approximate total memory used by cached models.
        current_size: Number of models currently in cache.
        max_size: Maximum number of models allowed in cache.
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    memory_usage_bytes: int = 0
    current_size: int = 0
    max_size: int = 0


@dataclass
class _CacheEntry:
    """Internal cache entry tracking model and metadata.

    Attributes:
        model: The cached model instance.
        loaded_at: Monotonic timestamp when the model was loaded.
        last_accessed: Monotonic timestamp of last access.
        model_name: Name identifier for the model.
        size_bytes: Approximate memory size of the model.
    """

    model: BaseModel
    loaded_at: float
    last_accessed: float
    model_name: str
    size_bytes: int = 0


class ModelCache:
    """Thread-safe LRU model cache with TTL expiration.

    Manages a fixed-size cache of loaded AI models. When the cache is full,
    the least-recently-used model is evicted. Models that exceed their TTL
    are evicted on access.

    Args:
        max_models: Maximum number of models to keep in cache.
        ttl_seconds: Time-to-live in seconds before a model expires.

    Example:
        >>> cache = ModelCache(max_models=3, ttl_seconds=300)
        >>> model = cache.get_or_load("qwen2.5:3b", loader_fn)
        >>> stats = cache.stats()
        >>> print(f"Hits: {stats.hits}, Misses: {stats.misses}")
    """

    def __init__(self, max_models: int = 3, ttl_seconds: float = 300.0) -> None:
        """Initialize the model cache.

        Args:
            max_models: Maximum number of models to keep in cache.
            ttl_seconds: Time-to-live in seconds before a model expires.

        Raises:
            ValueError: If max_models < 1 or ttl_seconds <= 0.
        """
        if max_models < 1:
            raise ValueError(f"max_models must be >= 1, got {max_models}")
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")

        self._max_models = max_models
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_or_load(
        self,
        model_name: str,
        loader: Callable[[], BaseModel],
    ) -> BaseModel:
        """Get a model from cache, or load it using the provided loader.

        If the model is in cache and not expired, returns the cached instance.
        Otherwise, loads the model, caches it, and returns it. If the cache
        is at capacity, the least-recently-used model is evicted first.

        Args:
            model_name: Unique identifier for the model.
            loader: Callable that returns a loaded BaseModel instance.

        Returns:
            The loaded model instance.
        """
        with self._lock:
            # Check for cached entry
            if model_name in self._cache:
                entry = self._cache[model_name]

                # Check TTL expiration
                now = time.monotonic()
                if (now - entry.loaded_at) > self._ttl_seconds:
                    logger.info(
                        "Model '%s' expired (age: %.1fs, ttl: %.1fs)",
                        model_name,
                        now - entry.loaded_at,
                        self._ttl_seconds,
                    )
                    self._evict_entry(model_name)
                else:
                    # Cache hit: update access time and move to end (most recent)
                    entry.last_accessed = now
                    self._cache.move_to_end(model_name)
                    self._hits += 1
                    logger.debug("Cache hit for model '%s'", model_name)
                    return entry.model

            # Cache miss: need to load
            self._misses += 1
            logger.debug("Cache miss for model '%s', loading...", model_name)

        # Load outside the lock to avoid blocking other cache operations
        model = loader()

        with self._lock:
            # Another thread may have loaded the same model while we were loading
            if model_name in self._cache:
                # Use the one that was loaded first, discard ours
                entry = self._cache[model_name]
                entry.last_accessed = time.monotonic()
                self._cache.move_to_end(model_name)
                return entry.model

            # Evict LRU entries if at capacity
            while len(self._cache) >= self._max_models:
                self._evict_lru()

            # Insert new entry
            now = time.monotonic()
            self._cache[model_name] = _CacheEntry(
                model=model,
                loaded_at=now,
                last_accessed=now,
                model_name=model_name,
                size_bytes=self._estimate_model_size(model),
            )
            logger.info(
                "Cached model '%s' (cache size: %d/%d)",
                model_name,
                len(self._cache),
                self._max_models,
            )

        return model

    def evict(self, model_name: str) -> bool:
        """Evict a specific model from the cache.

        Calls cleanup() on the model before removing it.

        Args:
            model_name: Name of the model to evict.

        Returns:
            True if the model was found and evicted, False otherwise.
        """
        with self._lock:
            if model_name not in self._cache:
                return False
            self._evict_entry(model_name)
            return True

    def clear(self) -> None:
        """Remove all models from the cache, calling cleanup() on each."""
        with self._lock:
            model_names = list(self._cache.keys())
            for name in model_names:
                self._evict_entry(name)
            logger.info("Cache cleared")

    def stats(self) -> CacheStats:
        """Get current cache statistics.

        Returns:
            CacheStats with current usage information.
        """
        with self._lock:
            total_memory = sum(entry.size_bytes for entry in self._cache.values())
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                memory_usage_bytes=total_memory,
                current_size=len(self._cache),
                max_size=self._max_models,
            )

    def contains(self, model_name: str) -> bool:
        """Check if a model is currently in the cache.

        Does not check TTL expiration; use get_or_load for that.

        Args:
            model_name: Name of the model to check.

        Returns:
            True if the model is in cache.
        """
        with self._lock:
            return model_name in self._cache

    @property
    def size(self) -> int:
        """Current number of models in cache."""
        with self._lock:
            return len(self._cache)

    def _evict_lru(self) -> None:
        """Evict the least-recently-used model. Must be called with lock held."""
        if not self._cache:
            return
        # OrderedDict: first item is the oldest (LRU)
        oldest_name = next(iter(self._cache))
        self._evict_entry(oldest_name)

    def _evict_entry(self, model_name: str) -> None:
        """Evict a specific entry and cleanup. Must be called with lock held."""
        entry = self._cache.pop(model_name, None)
        if entry is None:
            return
        self._evictions += 1
        logger.info("Evicted model '%s' from cache", model_name)
        try:
            entry.model.cleanup()
        except Exception:
            logger.warning(
                "Error during cleanup of model '%s'",
                model_name,
                exc_info=True,
            )

    @staticmethod
    def _estimate_model_size(model: BaseModel) -> int:
        """Estimate the memory size of a model in bytes.

        Uses sys.getsizeof as a rough approximation. Real model memory
        usage is typically much larger but requires framework-specific APIs.

        Args:
            model: The model to estimate size for.

        Returns:
            Estimated size in bytes.
        """
        try:
            return sys.getsizeof(model)
        except TypeError:
            return 0
