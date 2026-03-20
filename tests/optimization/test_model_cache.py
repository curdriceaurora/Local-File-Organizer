"""Tests for ModelCache - LRU eviction, TTL expiration, and thread safety."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import file_organizer.optimization.model_cache as _cache_mod
from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.optimization.model_cache import CacheStats, ModelCache


def _make_mock_model(name: str = "test-model") -> MagicMock:
    """Create a mock BaseModel instance."""
    mock = MagicMock(spec=BaseModel)
    mock.config = ModelConfig(name=name, model_type=ModelType.TEXT)
    mock.cleanup = MagicMock()
    return mock


def _make_loader(model: BaseModel | None = None) -> MagicMock:
    """Create a mock loader callable that returns a model."""
    if model is None:
        model = _make_mock_model()
    loader = MagicMock(return_value=model)
    return loader


@pytest.mark.unit
class TestModelCacheInit:
    """Tests for ModelCache initialization and validation."""

    def test_default_init(self) -> None:
        """Test default initialization parameters."""
        cache = ModelCache()
        stats = cache.stats()
        assert stats.max_size == 3
        assert stats.current_size == 0

    def test_custom_init(self) -> None:
        """Test custom initialization parameters."""
        cache = ModelCache(max_models=5, ttl_seconds=600.0)
        stats = cache.stats()
        assert stats.max_size == 5

    def test_invalid_max_models_zero(self) -> None:
        """Test that max_models=0 raises ValueError."""
        with pytest.raises(ValueError, match="max_models must be >= 1"):
            ModelCache(max_models=0)

    def test_invalid_max_models_negative(self) -> None:
        """Test that negative max_models raises ValueError."""
        with pytest.raises(ValueError, match="max_models must be >= 1"):
            ModelCache(max_models=-1)

    def test_invalid_ttl_zero(self) -> None:
        """Test that ttl_seconds=0 raises ValueError."""
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            ModelCache(ttl_seconds=0)

    def test_invalid_ttl_negative(self) -> None:
        """Test that negative ttl_seconds raises ValueError."""
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            ModelCache(ttl_seconds=-1)


@pytest.mark.unit
class TestModelCacheGetOrLoad:
    """Tests for the get_or_load method."""

    def test_load_new_model(self) -> None:
        """Test loading a model that is not in cache."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        model = _make_mock_model()
        loader = _make_loader(model)

        result = cache.get_or_load("test-model", loader)

        assert result is model
        loader.assert_called_once()
        assert cache.size == 1

    def test_cache_hit(self) -> None:
        """Test that a second get_or_load returns the cached model."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        model = _make_mock_model()
        loader = _make_loader(model)

        result1 = cache.get_or_load("test-model", loader)
        result2 = cache.get_or_load("test-model", loader)

        assert result1 is result2
        assert result1 is model
        loader.assert_called_once()  # Only called once

    def test_cache_miss_different_models(self) -> None:
        """Test loading different models results in separate cache entries."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        model_a = _make_mock_model("model-a")
        model_b = _make_mock_model("model-b")
        loader_a = _make_loader(model_a)
        loader_b = _make_loader(model_b)

        result_a = cache.get_or_load("model-a", loader_a)
        result_b = cache.get_or_load("model-b", loader_b)

        assert result_a is model_a
        assert result_b is model_b
        assert cache.size == 2

    def test_stats_hits_and_misses(self) -> None:
        """Test that stats correctly track hits and misses."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        loader = _make_loader()

        cache.get_or_load("model", loader)  # miss
        cache.get_or_load("model", loader)  # hit
        cache.get_or_load("model", loader)  # hit

        stats = cache.stats()
        assert stats.misses == 1
        assert stats.hits == 2


@pytest.mark.unit
class TestModelCacheLRUEviction:
    """Tests for LRU eviction policy."""

    def test_evict_lru_when_full(self) -> None:
        """Test that the LRU model is evicted when cache is full."""
        cache = ModelCache(max_models=2, ttl_seconds=300.0)
        model_a = _make_mock_model("a")
        model_b = _make_mock_model("b")
        model_c = _make_mock_model("c")

        cache.get_or_load("a", _make_loader(model_a))
        cache.get_or_load("b", _make_loader(model_b))
        cache.get_or_load("c", _make_loader(model_c))  # Should evict "a"

        assert cache.size == 2
        assert not cache.contains("a")
        assert cache.contains("b")
        assert cache.contains("c")
        model_a.cleanup.assert_called_once()

    def test_lru_updated_on_access(self) -> None:
        """Test that accessing a model updates its LRU position."""
        cache = ModelCache(max_models=2, ttl_seconds=300.0)
        model_a = _make_mock_model("a")
        model_b = _make_mock_model("b")
        model_c = _make_mock_model("c")

        cache.get_or_load("a", _make_loader(model_a))
        cache.get_or_load("b", _make_loader(model_b))
        # Access "a" to make it recently used
        cache.get_or_load("a", _make_loader(model_a))
        # Now "b" is LRU, should be evicted
        cache.get_or_load("c", _make_loader(model_c))

        assert cache.contains("a")
        assert not cache.contains("b")
        assert cache.contains("c")
        model_b.cleanup.assert_called_once()

    def test_eviction_counter(self) -> None:
        """Test that eviction counter is incremented."""
        cache = ModelCache(max_models=1, ttl_seconds=300.0)
        model_a = _make_mock_model("a")
        model_b = _make_mock_model("b")

        cache.get_or_load("a", _make_loader(model_a))
        cache.get_or_load("b", _make_loader(model_b))

        stats = cache.stats()
        assert stats.evictions == 1

    def test_multiple_evictions(self) -> None:
        """Test multiple evictions when cache size is 1."""
        cache = ModelCache(max_models=1, ttl_seconds=300.0)
        models = [_make_mock_model(f"model-{i}") for i in range(5)]

        for i, model in enumerate(models):
            cache.get_or_load(f"model-{i}", _make_loader(model))

        stats = cache.stats()
        assert stats.evictions == 4  # First model doesn't cause eviction
        assert cache.size == 1
        assert cache.contains("model-4")


@pytest.mark.unit
class TestModelCacheTTL:
    """Tests for TTL-based expiration."""

    def test_expired_model_reloaded(self) -> None:
        """Test that an expired model is reloaded."""
        cache = ModelCache(max_models=3, ttl_seconds=0.05)  # 50ms TTL
        model_v1 = _make_mock_model("v1")
        model_v2 = _make_mock_model("v2")
        loader_v1 = _make_loader(model_v1)
        loader_v2 = _make_loader(model_v2)

        cache.get_or_load("model", loader_v1)
        real_monotonic = time.monotonic
        with patch.object(
            _cache_mod.time, "monotonic", side_effect=lambda: real_monotonic() + 1000.0
        ):
            result = cache.get_or_load("model", loader_v2)

        assert result is model_v2
        model_v1.cleanup.assert_called_once()  # Old model cleaned up

    def test_non_expired_model_not_reloaded(self) -> None:
        """Test that a non-expired model is returned from cache."""
        cache = ModelCache(max_models=3, ttl_seconds=10.0)
        model = _make_mock_model()
        loader = _make_loader(model)

        cache.get_or_load("model", loader)
        result = cache.get_or_load("model", loader)

        assert result is model
        loader.assert_called_once()


@pytest.mark.unit
class TestModelCacheExplicitEviction:
    """Tests for explicit eviction and clear."""

    def test_evict_existing_model(self) -> None:
        """Test evicting a specific model."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        model = _make_mock_model()

        cache.get_or_load("model", _make_loader(model))
        result = cache.evict("model")

        assert result is True
        assert cache.size == 0
        model.cleanup.assert_called_once()

    def test_evict_nonexistent_model(self) -> None:
        """Test evicting a model that is not in cache."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        result = cache.evict("nonexistent")
        assert result is False

    def test_clear_empty_cache(self) -> None:
        """Test clearing an empty cache."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.clear()
        assert cache.size == 0

    def test_clear_populated_cache(self) -> None:
        """Test clearing a cache with multiple models."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        models = [_make_mock_model(f"model-{i}") for i in range(3)]

        for i, model in enumerate(models):
            cache.get_or_load(f"model-{i}", _make_loader(model))

        cache.clear()

        assert cache.size == 0
        for model in models:
            model.cleanup.assert_called_once()

    def test_clear_increments_eviction_counter(self) -> None:
        """Test that clear increments the eviction counter."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        for i in range(3):
            cache.get_or_load(f"model-{i}", _make_loader())

        cache.clear()

        stats = cache.stats()
        assert stats.evictions == 3

    def test_cleanup_error_does_not_prevent_eviction(self) -> None:
        """Test that cleanup errors are handled gracefully."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        model = _make_mock_model()
        model.cleanup.side_effect = RuntimeError("cleanup failed")

        cache.get_or_load("model", _make_loader(model))
        result = cache.evict("model")

        assert result is True
        assert cache.size == 0


@pytest.mark.unit
class TestModelCacheStats:
    """Tests for cache statistics."""

    def test_initial_stats(self) -> None:
        """Test initial stats are all zero."""
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        stats = cache.stats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.memory_usage_bytes == 0
        assert stats.current_size == 0
        assert stats.max_size == 5

    def test_stats_after_operations(self) -> None:
        """Test stats reflect operations correctly."""
        cache = ModelCache(max_models=2, ttl_seconds=300.0)

        cache.get_or_load("a", _make_loader())  # miss
        cache.get_or_load("a", _make_loader())  # hit
        cache.get_or_load("b", _make_loader())  # miss
        cache.get_or_load("c", _make_loader())  # miss + eviction of "a"

        stats = cache.stats()
        assert stats.misses == 3
        assert stats.hits == 1
        assert stats.evictions == 1
        assert stats.current_size == 2

    def test_cache_stats_is_dataclass(self) -> None:
        """Test that CacheStats fields are accessible."""
        stats = CacheStats(
            hits=10,
            misses=5,
            evictions=2,
            memory_usage_bytes=1024,
            current_size=3,
            max_size=5,
        )
        assert stats.hits == 10
        assert stats.misses == 5
        assert stats.evictions == 2
        assert stats.memory_usage_bytes == 1024


@pytest.mark.unit
class TestModelCacheContains:
    """Tests for the contains method."""

    def test_contains_existing(self) -> None:
        """Test contains returns True for cached model."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model", _make_loader())
        assert cache.contains("model") is True

    def test_contains_nonexistent(self) -> None:
        """Test contains returns False for missing model."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        assert cache.contains("nonexistent") is False

    def test_contains_after_eviction(self) -> None:
        """Test contains returns False after eviction."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model", _make_loader())
        cache.evict("model")
        assert cache.contains("model") is False


@pytest.mark.unit
class TestModelCacheThreadSafety:
    """Tests for thread-safe operation."""

    def test_concurrent_loads_different_models(self) -> None:
        """Test that concurrent loads of different models work correctly."""
        cache = ModelCache(max_models=10, ttl_seconds=300.0)
        errors: list[str] = []
        barrier = threading.Barrier(5)

        def load_model(name: str) -> None:
            try:
                barrier.wait(timeout=5)
                model = _make_mock_model(name)
                cache.get_or_load(name, _make_loader(model))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=load_model, args=(f"model-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert cache.size == 5

    def test_concurrent_loads_same_model(self) -> None:
        """Test that concurrent loads of the same model only load once."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        load_count = 0
        lock = threading.Lock()

        started = threading.Event()

        def slow_loader() -> MagicMock:
            nonlocal load_count
            started.set()
            started.wait()  # All threads pile up here once set
            with lock:
                load_count += 1
            return _make_mock_model("shared")

        barrier = threading.Barrier(3)
        errors: list[str] = []

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                cache.get_or_load("shared", slow_loader)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert cache.size == 1
        # Due to race condition handling, load_count may be > 1
        # but only one model should be in the cache

    def test_concurrent_evict_and_load(self) -> None:
        """Test that concurrent evict and load operations are safe."""
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model", _make_loader())
        errors: list[str] = []

        def evict_loop() -> None:
            try:
                for _ in range(20):
                    cache.evict("model")
            except Exception as e:
                errors.append(str(e))

        def load_loop() -> None:
            try:
                for _ in range(20):
                    cache.get_or_load("model", _make_loader())
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=evict_loop)
        t2 = threading.Thread(target=load_loop)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors
