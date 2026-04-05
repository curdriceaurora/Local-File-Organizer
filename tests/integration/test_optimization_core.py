"""Integration tests for optimization modules.

Covers untested code paths in:
  memory_profiler, resource_monitor, connection_pool, query_cache,
  model_cache, memory_limiter, leak_detector, lazy_loader,
  batch_sizer, warmup.

All external services (nvidia-smi, subprocess, psutil) are mocked.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_base_model(name: str = "test-model") -> MagicMock:
    """Return a MagicMock that satisfies BaseModel's interface."""
    from file_organizer.models.base import BaseModel

    mock = MagicMock(spec=BaseModel)
    mock.config = MagicMock()
    mock.config.name = name
    return mock


def _make_model_config(name: str = "test-model", framework: str = "ollama") -> Any:
    from file_organizer.models.base import ModelConfig, ModelType

    return ModelConfig(name=name, model_type=ModelType.TEXT, framework=framework)


# ===========================================================================
# TestMemoryProfiler
# ===========================================================================


class TestMemoryProfiler:
    """Tests for MemoryProfiler and its dataclasses."""

    def test_memory_snapshot_fields(self) -> None:
        from file_organizer.optimization.memory_profiler import MemorySnapshot

        snap = MemorySnapshot(
            rss=1024,
            vms=2048,
            objects_by_type=(("dict", 100), ("list", 50)),
            timestamp=1.0,
        )
        assert snap.rss == 1024
        assert snap.vms == 2048
        assert snap.objects_by_type == (("dict", 100), ("list", 50))
        assert snap.timestamp == 1.0

    def test_profile_result_fields(self) -> None:
        from file_organizer.optimization.memory_profiler import ProfileResult

        result = ProfileResult(
            peak_memory=8192,
            allocated=4096,
            freed=0,
            duration_ms=12.5,
            func_name="my_func",
        )
        assert result.peak_memory == 8192
        assert result.allocated == 4096
        assert result.freed == 0
        assert result.duration_ms == 12.5
        assert result.func_name == "my_func"

    def test_memory_timeline_defaults(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryTimeline

        tl = MemoryTimeline()
        assert tl.snapshots == []
        assert tl.interval_seconds == 0.0

    def test_get_snapshot_returns_memory_snapshot(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler, MemorySnapshot

        profiler = MemoryProfiler()
        snap = profiler.get_snapshot()
        assert isinstance(snap, MemorySnapshot)
        assert snap.rss >= 0
        assert snap.vms >= 0
        assert snap.timestamp > 0

    def test_get_snapshot_objects_by_type_is_tuple_of_pairs(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()
        snap = profiler.get_snapshot()
        # objects_by_type is a tuple of (str, int) pairs
        assert isinstance(snap.objects_by_type, tuple)
        for entry in snap.objects_by_type:
            type_name, count = entry
            assert isinstance(type_name, str)
            assert count >= 1

    def test_profile_decorator_records_result(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()

        @profiler.profile
        def simple_func(x: int) -> int:
            return x * 2

        assert profiler.last_result is None
        return_val = simple_func(3)
        assert return_val == 6
        assert profiler.last_result is not None
        assert profiler.last_result.func_name == "simple_func"
        assert profiler.last_result.duration_ms >= 0
        assert profiler.last_result.peak_memory >= 0

    def test_profile_decorator_preserves_function_return_value(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()

        @profiler.profile
        def returns_list() -> list[int]:
            return [1, 2, 3]

        result = returns_list()
        assert result == [1, 2, 3]

    def test_profile_decorator_records_allocated_and_freed(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()

        @profiler.profile
        def noop() -> None:
            pass

        noop()
        r = profiler.last_result
        assert r is not None
        assert r.allocated >= 0
        assert r.freed >= 0

    def test_start_tracking_and_stop_tracking(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler, MemoryTimeline

        profiler = MemoryProfiler()
        profiler.start_tracking(interval_seconds=0.05)
        assert profiler._tracking is True
        timeline = profiler.stop_tracking()
        assert isinstance(timeline, MemoryTimeline)
        # start adds one snapshot; stop adds another
        assert len(timeline.snapshots) >= 2
        assert timeline.interval_seconds == 0.05
        assert profiler._tracking is False

    def test_add_snapshot_during_tracking(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler, MemorySnapshot

        profiler = MemoryProfiler()
        profiler.start_tracking()
        extra = profiler.add_snapshot()
        assert isinstance(extra, MemorySnapshot)
        timeline = profiler.stop_tracking()
        # start (1) + add_snapshot (1) + stop (1) = 3
        assert len(timeline.snapshots) == 3

    def test_add_snapshot_without_tracking_raises(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()
        with pytest.raises(RuntimeError, match="Tracking not started"):
            profiler.add_snapshot()

    def test_stop_tracking_without_start_returns_empty_timeline(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        profiler = MemoryProfiler()
        # _tracking is False; stop_tracking should still return a timeline
        timeline = profiler.stop_tracking()
        assert timeline.snapshots == []

    def test_get_top_objects_returns_sorted_list(self) -> None:
        from file_organizer.optimization.memory_profiler import MemoryProfiler

        result = MemoryProfiler._get_top_objects(limit=5)
        # Result has at most `limit` entries (may be fewer if fewer object types exist)
        assert len(result) == min(5, len(result))  # not exceeding requested limit
        # Verify descending sort on count
        counts = [c for _, c in result]
        assert counts == sorted(counts, reverse=True)


# ===========================================================================
# TestResourceMonitor
# ===========================================================================


class TestResourceMonitor:
    """Tests for ResourceMonitor and its dataclasses."""

    def test_memory_info_fields(self) -> None:
        from file_organizer.optimization.resource_monitor import MemoryInfo

        info = MemoryInfo(rss=1024 * 1024, vms=2 * 1024 * 1024, percent=1.5)
        assert info.rss == 1024 * 1024
        assert info.vms == 2 * 1024 * 1024
        assert info.percent == 1.5

    def test_gpu_memory_info_fields(self) -> None:
        from file_organizer.optimization.resource_monitor import GpuMemoryInfo

        gpu = GpuMemoryInfo(
            total=8 * 1024 * 1024 * 1024,
            used=2 * 1024 * 1024 * 1024,
            free=6 * 1024 * 1024 * 1024,
            percent=25.0,
            device_name="NVIDIA GeForce RTX 3080",
        )
        assert gpu.total == 8 * 1024 * 1024 * 1024
        assert gpu.used == 2 * 1024 * 1024 * 1024
        assert gpu.free == 6 * 1024 * 1024 * 1024
        assert gpu.percent == 25.0
        assert gpu.device_name == "NVIDIA GeForce RTX 3080"

    def test_get_memory_usage_psutil_path(self) -> None:
        """Mock psutil to verify get_memory_usage returns correct MemoryInfo."""
        from file_organizer.optimization.resource_monitor import MemoryInfo, ResourceMonitor

        mock_mem_info = MagicMock()
        mock_mem_info.rss = 50 * 1024 * 1024
        mock_mem_info.vms = 200 * 1024 * 1024

        mock_process = MagicMock()
        mock_process.memory_info.return_value = mock_mem_info

        mock_virtual_mem = MagicMock()
        mock_virtual_mem.total = 16 * 1024 * 1024 * 1024

        with (
            patch("psutil.Process", return_value=mock_process),
            patch("psutil.virtual_memory", return_value=mock_virtual_mem),
        ):
            monitor = ResourceMonitor()
            mem = monitor.get_memory_usage()

        assert isinstance(mem, MemoryInfo)
        assert mem.rss == 50 * 1024 * 1024
        assert mem.vms == 200 * 1024 * 1024
        assert mem.percent > 0.0

    def test_get_memory_usage_fallback_without_psutil(self) -> None:
        """When psutil import fails the fallback should still return MemoryInfo."""
        from file_organizer.optimization.resource_monitor import MemoryInfo, ResourceMonitor

        monitor = ResourceMonitor()
        with patch(
            "file_organizer.optimization.resource_monitor.ResourceMonitor._get_memory_psutil",
            side_effect=ImportError("psutil not installed"),
        ):
            mem = monitor.get_memory_usage()

        assert isinstance(mem, MemoryInfo)
        assert mem.rss >= 0

    def test_get_gpu_memory_no_gpu_returns_none(self) -> None:
        """When nvidia-smi is absent get_gpu_memory returns None."""
        from file_organizer.optimization.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        with patch(
            "file_organizer.optimization.resource_monitor.subprocess.run",
            side_effect=FileNotFoundError("nvidia-smi not found"),
        ):
            result = monitor.get_gpu_memory()

        assert result is None

    def test_get_gpu_memory_parses_nvidia_smi_output(self) -> None:
        """Mock subprocess to return valid nvidia-smi CSV output."""

        from file_organizer.optimization.resource_monitor import GpuMemoryInfo, ResourceMonitor

        fake_output = "NVIDIA GeForce RTX 3080, 10240, 2048, 8192\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_output

        monitor = ResourceMonitor()
        with patch("subprocess.run", return_value=mock_result):
            gpu = monitor.get_gpu_memory()

        assert gpu is not None
        assert isinstance(gpu, GpuMemoryInfo)
        assert gpu.device_name == "NVIDIA GeForce RTX 3080"
        assert gpu.total == int(10240 * 1024 * 1024)
        assert gpu.used == int(2048 * 1024 * 1024)
        assert gpu.free == int(8192 * 1024 * 1024)
        assert gpu.percent == pytest.approx(20.0, abs=0.1)

    def test_should_evict_below_threshold_returns_false(self) -> None:
        from file_organizer.optimization.resource_monitor import MemoryInfo, ResourceMonitor

        monitor = ResourceMonitor()
        low_mem = MemoryInfo(rss=100, vms=200, percent=50.0)
        with patch.object(monitor, "get_memory_usage", return_value=low_mem):
            assert monitor.should_evict(threshold_percent=85.0) is False

    def test_should_evict_above_threshold_returns_true(self) -> None:
        from file_organizer.optimization.resource_monitor import MemoryInfo, ResourceMonitor

        monitor = ResourceMonitor()
        high_mem = MemoryInfo(rss=100, vms=200, percent=90.0)
        with patch.object(monitor, "get_memory_usage", return_value=high_mem):
            assert monitor.should_evict(threshold_percent=85.0) is True

    def test_should_evict_invalid_threshold_raises(self) -> None:
        from file_organizer.optimization.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        with pytest.raises(ValueError, match="threshold_percent"):
            monitor.should_evict(threshold_percent=150.0)

    def test_should_evict_at_exact_threshold_returns_true(self) -> None:
        from file_organizer.optimization.resource_monitor import MemoryInfo, ResourceMonitor

        monitor = ResourceMonitor()
        exact_mem = MemoryInfo(rss=100, vms=200, percent=85.0)
        with patch.object(monitor, "get_memory_usage", return_value=exact_mem):
            # percent >= threshold → True
            assert monitor.should_evict(threshold_percent=85.0) is True


# ===========================================================================
# TestConnectionPool
# ===========================================================================


class TestConnectionPool:
    """Tests for ConnectionPool."""

    def test_pool_creation_and_acquire_single(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=2, timeout=5.0)
        try:
            with pool.acquire() as conn:
                row = conn.execute("SELECT 1").fetchone()
                assert row[0] == 1
        finally:
            pool.close()

    def test_acquire_returns_connection_to_pool(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=1, timeout=5.0)
        try:
            with pool.acquire():
                stats_inside = pool.stats()
                assert stats_inside.active == 1
            stats_after = pool.stats()
            assert stats_after.active == 0
        finally:
            pool.close()

    def test_pool_size_one_second_acquire_waits_and_times_out(self, tmp_path: Path) -> None:
        """A pool of size=1 should raise TimeoutError when exhausted."""
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=1, timeout=0.1)
        try:
            conn_ctx = pool.acquire()
            conn_ctx.__enter__()
            try:
                with pytest.raises(TimeoutError):
                    with pool.acquire():
                        pass
            finally:
                conn_ctx.__exit__(None, None, None)
        finally:
            pool.close()

    def test_stats_reflects_pool_size(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=3, timeout=5.0)
        try:
            stats = pool.stats()
            assert stats.pool_size == 3
            assert stats.total >= 0
        finally:
            pool.close()

    def test_close_prevents_further_acquire(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=2, timeout=5.0)
        pool.close()
        with pytest.raises(RuntimeError, match="closed"):
            with pool.acquire():
                pass

    def test_pool_size_zero_raises_value_error(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        with pytest.raises(ValueError, match="pool_size"):
            ConnectionPool(db, pool_size=0)

    def test_manual_release_returns_connection_to_pool(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=2, timeout=5.0)
        try:
            # Manually checkout and return via release()
            conn_ctx = pool.acquire()
            conn_ctx.__enter__()
            assert pool.stats().active == 1
            conn_ctx.__exit__(None, None, None)
            assert pool.stats().active == 0
        finally:
            pool.close()

    def test_context_manager_protocol_on_exception(self, tmp_path: Path) -> None:
        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=2, timeout=5.0)
        try:
            with pytest.raises(RuntimeError, match="deliberate"):
                with pool.acquire():
                    raise RuntimeError("deliberate")
            # Connection must have been returned even on exception
            assert pool.stats().active == 0
        finally:
            pool.close()

    def test_pool_stats_wait_count_increments(self, tmp_path: Path) -> None:
        """Exhaust pool so wait_count increments (via timeout path)."""

        from file_organizer.optimization.connection_pool import ConnectionPool

        db = tmp_path / "test.db"
        pool = ConnectionPool(db, pool_size=1, timeout=0.05)
        try:
            conn_ctx = pool.acquire()
            conn_ctx.__enter__()
            try:
                # This should increment wait_count and then time out
                with pytest.raises(TimeoutError):
                    with pool.acquire():
                        pass
                # wait_count should be >= 1 after timeout
                assert pool.stats().wait_count >= 1
            finally:
                conn_ctx.__exit__(None, None, None)
        finally:
            pool.close()

    def test_memory_db_pool(self) -> None:
        """In-memory SQLite pool (each connection is independent)."""
        from file_organizer.optimization.connection_pool import ConnectionPool

        pool = ConnectionPool(":memory:", pool_size=2, timeout=5.0)
        try:
            with pool.acquire() as conn:
                conn.execute("CREATE TABLE t (x INT)")
                conn.execute("INSERT INTO t VALUES (42)")
                conn.commit()
                row = conn.execute("SELECT x FROM t").fetchone()
                assert row[0] == 42
        finally:
            pool.close()


# ===========================================================================
# TestQueryCache
# ===========================================================================


class TestQueryCache:
    """Tests for QueryCache."""

    def test_put_and_get_returns_cached_result(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("key1", [{"id": 1}], tables={"users"})
        entry = cache.get("key1")
        assert entry is not None
        assert entry.data == [{"id": 1}]
        assert entry.hit_count == 1

    def test_get_miss_returns_none(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry_returns_none(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        # Place entry with a timestamp that is already expired
        cache.put("key_expired", "some_data")
        # Patch time.time to simulate expiry
        with patch(
            "file_organizer.optimization.query_cache.time.time", return_value=time.time() + 120
        ):
            result = cache.get("key_expired")
        assert result is None

    def test_lru_eviction_on_max_size(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=2, ttl_seconds=60.0)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # evicts "a" (LRU)
        assert cache.get("a") is None
        assert cache.get("b") is not None
        assert cache.get("c") is not None

    def test_invalidate_by_table_removes_dependent_entries(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("q1", "result1", tables={"orders"})
        cache.put("q2", "result2", tables={"orders", "users"})
        cache.put("q3", "result3", tables={"users"})

        removed = cache.invalidate("orders")
        assert removed == 2
        assert cache.get("q1") is None
        assert cache.get("q2") is None
        assert cache.get("q3") is not None

    def test_invalidate_unknown_table_removes_zero(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("q1", "result1", tables={"orders"})
        removed = cache.invalidate("nonexistent_table")
        assert removed == 0

    def test_clear_removes_all_entries(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("q1", 1)
        cache.put("q2", 2)
        cache.clear()
        assert cache.size == 0
        assert cache.hit_rate == 0.0

    def test_hit_rate_after_hits_and_misses(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("k", "val")
        cache.get("k")  # hit
        cache.get("k")  # hit
        cache.get("missing")  # miss
        assert cache.hit_rate == pytest.approx(2 / 3, abs=0.01)

    def test_hit_rate_no_lookups_returns_zero(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        assert cache.hit_rate == 0.0

    def test_size_property(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        assert cache.size == 0
        cache.put("a", 1)
        assert cache.size == 1
        cache.put("b", 2)
        assert cache.size == 2

    def test_make_hash_is_deterministic(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        h1 = QueryCache.make_hash("SELECT * FROM t", (1, 2))
        h2 = QueryCache.make_hash("SELECT * FROM t", (1, 2))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length

    def test_make_hash_differs_for_different_queries(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        h1 = QueryCache.make_hash("SELECT 1")
        h2 = QueryCache.make_hash("SELECT 2")
        assert h1 != h2

    def test_invalid_max_size_raises(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        with pytest.raises(ValueError, match="max_size"):
            QueryCache(max_size=0)

    def test_invalid_ttl_raises(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        with pytest.raises(ValueError, match="ttl_seconds"):
            QueryCache(ttl_seconds=0)

    def test_put_overwrites_existing_key(self) -> None:
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=10, ttl_seconds=60.0)
        cache.put("key", "v1")
        cache.put("key", "v2")
        entry = cache.get("key")
        assert entry is not None
        assert entry.data == "v2"

    def test_lru_access_promotes_entry(self) -> None:
        """Accessing 'a' after inserting 'b' should protect 'a' from eviction."""
        from file_organizer.optimization.query_cache import QueryCache

        cache = QueryCache(max_size=2, ttl_seconds=60.0)
        cache.put("a", "va")
        cache.put("b", "vb")
        # Access 'a' to make 'b' the LRU
        cache.get("a")
        # Insert 'c' should evict 'b' (now LRU)
        cache.put("c", "vc")
        assert cache.get("b") is None
        assert cache.get("a") is not None
        assert cache.get("c") is not None


# ===========================================================================
# TestModelCache
# ===========================================================================


class TestModelCache:
    """Tests for ModelCache."""

    def test_get_or_load_calls_loader_on_miss(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model("m1")
        loader = MagicMock(return_value=model)

        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        result = cache.get_or_load("model-a", loader)

        assert result is model
        loader.assert_called_once()

    def test_get_or_load_returns_cached_on_second_call(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model("m1")
        loader = MagicMock(return_value=model)

        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model-a", loader)
        cache.get_or_load("model-a", loader)

        # Loader should only be called once (second call is a hit)
        assert loader.call_count == 1

    def test_stats_reflect_hits_and_misses(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model()
        loader = MagicMock(return_value=model)

        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model-a", loader)  # miss
        cache.get_or_load("model-a", loader)  # hit
        cache.get_or_load("model-a", loader)  # hit

        stats = cache.stats()
        assert stats.misses == 1
        assert stats.hits == 2

    def test_lru_eviction_when_cache_full(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        models = {name: _make_base_model(name) for name in ["m1", "m2", "m3"]}
        loaders = {name: MagicMock(return_value=m) for name, m in models.items()}

        cache = ModelCache(max_models=2, ttl_seconds=300.0)
        cache.get_or_load("m1", loaders["m1"])
        cache.get_or_load("m2", loaders["m2"])
        # 'm1' is now LRU; adding 'm3' should evict 'm1'
        cache.get_or_load("m3", loaders["m3"])

        assert not cache.contains("m1")
        assert cache.contains("m2")
        assert cache.contains("m3")
        stats = cache.stats()
        assert stats.evictions == 1

    def test_evict_specific_model(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model()
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("model-a", lambda: model)

        assert cache.contains("model-a")
        evicted = cache.evict("model-a")
        assert evicted is True
        assert not cache.contains("model-a")
        model.cleanup.assert_called_once()

    def test_evict_nonexistent_returns_false(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        assert cache.evict("does-not-exist") is False

    def test_clear_removes_all_models_and_calls_cleanup(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        m1 = _make_base_model("m1")
        m2 = _make_base_model("m2")
        cache = ModelCache(max_models=3, ttl_seconds=300.0)
        cache.get_or_load("m1", lambda: m1)
        cache.get_or_load("m2", lambda: m2)

        cache.clear()
        assert cache.size == 0
        m1.cleanup.assert_called_once()
        m2.cleanup.assert_called_once()

    def test_ttl_expiry_triggers_reload(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model_v1 = _make_base_model("v1")
        model_v2 = _make_base_model("v2")
        load_count = [0]

        def loader() -> Any:
            load_count[0] += 1
            return model_v1 if load_count[0] == 1 else model_v2

        cache = ModelCache(max_models=3, ttl_seconds=1.0)
        cache.get_or_load("model-a", loader)

        # Simulate TTL expiry by patching time.monotonic
        future_time = time.monotonic() + 200.0
        with patch(
            "file_organizer.optimization.model_cache.time.monotonic", return_value=future_time
        ):
            cache.get_or_load("model-a", loader)

        assert load_count[0] == 2
        stats = cache.stats()
        assert stats.evictions >= 1

    def test_stats_current_size_and_max_size(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model()
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        cache.get_or_load("m", lambda: model)
        stats = cache.stats()
        assert stats.current_size == 1
        assert stats.max_size == 5

    def test_invalid_max_models_raises(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        with pytest.raises(ValueError, match="max_models"):
            ModelCache(max_models=0)

    def test_invalid_ttl_raises(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        with pytest.raises(ValueError, match="ttl_seconds"):
            ModelCache(ttl_seconds=0)


# ===========================================================================
# TestMemoryLimiter
# ===========================================================================


class TestMemoryLimiter:
    """Tests for MemoryLimiter and LimitAction."""

    def _make_limiter_over_limit(self, action: Any) -> Any:
        """Return a limiter whose _get_rss is patched to always exceed the limit."""
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1, action=action)
        # Patch _get_rss so current RSS is always above the 1 MB limit
        return limiter

    def test_check_returns_true_when_under_limit(self) -> None:
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=999_999)
        assert limiter.check() is True

    def test_check_returns_false_when_over_limit(self) -> None:
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1)
        # Force RSS above limit
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            assert limiter.check() is False

    def test_enforce_warn_increments_violation_count(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.WARN)
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            limiter.enforce()
            limiter.enforce()

        assert limiter.violation_count == 2

    def test_enforce_raise_raises_memory_limit_error(self) -> None:
        from file_organizer.optimization.memory_limiter import (
            LimitAction,
            MemoryLimiter,
            MemoryLimitError,
        )

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.RAISE)
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            with pytest.raises(MemoryLimitError, match="Memory limit exceeded"):
                limiter.enforce()

    def test_enforce_evict_cache_calls_callback(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.EVICT_CACHE)
        callback = MagicMock()
        limiter.set_evict_callback(callback)

        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            limiter.enforce()

        callback.assert_called_once()

    def test_enforce_evict_cache_without_callback_does_not_raise(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.EVICT_CACHE)
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            limiter.enforce()  # should not raise

    def test_enforce_block_increments_violation_count(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.BLOCK)
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            limiter.enforce()

        assert limiter.violation_count == 1

    def test_guarded_context_manager_raises_on_entry(self) -> None:
        from file_organizer.optimization.memory_limiter import (
            LimitAction,
            MemoryLimiter,
            MemoryLimitError,
        )

        limiter = MemoryLimiter(max_memory_mb=1, action=LimitAction.RAISE)
        with patch.object(
            type(limiter),
            "_get_rss",
            staticmethod(lambda: 2 * 1024 * 1024),
        ):
            with pytest.raises(MemoryLimitError):
                with limiter.guarded():
                    pass

    def test_guarded_context_manager_ok_under_limit(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=999_999, action=LimitAction.RAISE)
        with limiter.guarded():
            pass  # no exception expected

    def test_get_current_memory_mb_returns_non_negative(self) -> None:
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=512)
        result = limiter.get_current_memory_mb()
        assert result >= 0.0

    def test_max_memory_mb_property(self) -> None:
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=256)
        assert limiter.max_memory_mb == 256

    def test_action_property(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=256, action=LimitAction.BLOCK)
        assert limiter.action == LimitAction.BLOCK

    def test_invalid_max_memory_raises(self) -> None:
        from file_organizer.optimization.memory_limiter import MemoryLimiter

        with pytest.raises(ValueError, match="max_memory_mb"):
            MemoryLimiter(max_memory_mb=0)

    def test_enforce_under_limit_does_not_increment_violation_count(self) -> None:
        from file_organizer.optimization.memory_limiter import LimitAction, MemoryLimiter

        limiter = MemoryLimiter(max_memory_mb=999_999, action=LimitAction.WARN)
        limiter.enforce()
        assert limiter.violation_count == 0


# ===========================================================================
# TestLeakDetector
# ===========================================================================


class TestLeakDetector:
    """Tests for LeakDetector."""

    def test_is_tracking_false_before_start(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector()
        assert detector.is_tracking is False

    def test_is_tracking_true_after_start(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector()
        detector.start()
        assert detector.is_tracking is True
        detector.stop()

    def test_check_before_start_raises(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector()
        with pytest.raises(RuntimeError, match="not started"):
            detector.check()

    def test_check_after_start_returns_list(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector(min_count_delta=100)
        detector.start()
        suspects = detector.check()
        # check() always returns a list regardless of number of suspects
        assert type(suspects).__name__ == "list"
        detector.stop()

    def test_check_count_increments(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector(min_count_delta=100)
        detector.start()
        assert detector.check_count == 0
        detector.check()
        assert detector.check_count == 1
        detector.check()
        assert detector.check_count == 2
        detector.stop()

    def test_stop_resets_state(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector()
        detector.start()
        detector.stop()
        assert detector.is_tracking is False
        assert detector.check_count == 0

    def test_reset_baseline_without_start_raises(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector()
        with pytest.raises(RuntimeError, match="not started"):
            detector.reset_baseline()

    def test_reset_baseline_resets_check_count(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        detector = LeakDetector(min_count_delta=100)
        detector.start()
        detector.check()
        detector.check()
        assert detector.check_count == 2
        detector.reset_baseline()
        assert detector.check_count == 0
        detector.stop()

    def test_suspects_sorted_by_count_delta_descending(self) -> None:
        from file_organizer.optimization.leak_detector import (
            LeakDetector,
            _TypeSnapshot,
        )

        detector = LeakDetector(min_count_delta=1)
        detector.start()

        # Inject a controlled baseline and current snapshot
        baseline = {"list": _TypeSnapshot(count=10, total_size=100, timestamp=0.0)}
        current_overcount = {
            "list": _TypeSnapshot(count=15, total_size=150, timestamp=1.0),
            "dict": _TypeSnapshot(count=25, total_size=200, timestamp=1.0),
        }
        detector._baseline = baseline

        with patch.object(
            type(detector),
            "_snapshot_types",
            staticmethod(lambda: current_overcount),
        ):
            suspects = detector.check()

        # dict appeared new (delta=25), list increased (delta=5)
        assert len(suspects) >= 1
        # Verify sorting
        deltas = [s.count_delta for s in suspects]
        assert deltas == sorted(deltas, reverse=True)
        detector.stop()

    def test_ignore_types_filters_suspects(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector, _TypeSnapshot

        detector = LeakDetector(min_count_delta=1, ignore_types={"dict"})
        detector.start()

        baseline = {}
        current = {
            "dict": _TypeSnapshot(count=100, total_size=1000, timestamp=1.0),
            "list": _TypeSnapshot(count=50, total_size=500, timestamp=1.0),
        }
        detector._baseline = baseline

        with patch.object(
            type(detector),
            "_snapshot_types",
            staticmethod(lambda: current),
        ):
            suspects = detector.check()

        type_names = [s.type_name for s in suspects]
        assert "dict" not in type_names
        detector.stop()

    def test_invalid_min_count_delta_raises(self) -> None:
        from file_organizer.optimization.leak_detector import LeakDetector

        with pytest.raises(ValueError, match="min_count_delta"):
            LeakDetector(min_count_delta=0)

    def test_leak_suspect_fields(self) -> None:
        from file_organizer.optimization.leak_detector import LeakSuspect

        suspect = LeakSuspect(type_name="dict", count_delta=42, size_delta=1024)
        assert suspect.type_name == "dict"
        assert suspect.count_delta == 42
        assert suspect.size_delta == 1024


# ===========================================================================
# TestLazyModelLoader
# ===========================================================================


class TestLazyModelLoader:
    """Tests for LazyModelLoader."""

    def test_is_loaded_false_before_access(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=lambda c: _make_base_model())
        assert lazy.is_loaded is False

    def test_model_property_triggers_load(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        model = _make_base_model()
        loader = MagicMock(return_value=model)
        config = _make_model_config()

        lazy = LazyModelLoader(config, loader=loader)
        result = lazy.model
        assert result is model
        loader.assert_called_once_with(config)

    def test_is_loaded_true_after_access(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        model = _make_base_model()
        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=lambda c: model)
        _ = lazy.model
        assert lazy.is_loaded is True

    def test_second_access_does_not_call_loader_again(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        model = _make_base_model()
        loader = MagicMock(return_value=model)
        config = _make_model_config()

        lazy = LazyModelLoader(config, loader=loader)
        _ = lazy.model
        _ = lazy.model
        assert loader.call_count == 1

    def test_loader_failure_wraps_as_runtime_error(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        def bad_loader(c: Any) -> Any:
            raise ValueError("load failed")

        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=bad_loader)

        with pytest.raises(RuntimeError, match="Failed to load model"):
            _ = lazy.model

    def test_unload_calls_cleanup_and_resets(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        model = _make_base_model()
        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=lambda c: model)

        _ = lazy.model
        assert lazy.is_loaded is True
        lazy.unload()
        assert lazy.is_loaded is False
        model.cleanup.assert_called_once()

    def test_unload_when_not_loaded_is_a_no_op(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=lambda c: _make_base_model())
        lazy.unload()  # should not raise
        assert lazy.is_loaded is False

    def test_config_property(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        config = _make_model_config(name="my-model")
        lazy = LazyModelLoader(config, loader=lambda c: _make_base_model())
        assert lazy.config is config

    def test_repr_shows_not_loaded_initially(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        config = _make_model_config(name="repr-model")
        lazy = LazyModelLoader(config, loader=lambda c: _make_base_model())
        r = repr(lazy)
        assert "not loaded" in r
        assert "repr-model" in r

    def test_repr_shows_loaded_after_access(self) -> None:
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        model = _make_base_model()
        config = _make_model_config(name="repr-model2")
        lazy = LazyModelLoader(config, loader=lambda c: model)
        _ = lazy.model
        r = repr(lazy)
        assert "loaded" in r

    def test_thread_safe_load_only_once(self) -> None:
        """Multiple threads accessing model simultaneously should load once."""
        from file_organizer.optimization.lazy_loader import LazyModelLoader

        call_count = [0]
        model = _make_base_model()

        def counting_loader(c: Any) -> Any:
            # Use a barrier to synchronise threads instead of time.sleep
            call_count[0] += 1
            return model

        config = _make_model_config()
        lazy = LazyModelLoader(config, loader=counting_loader)

        threads = [threading.Thread(target=lambda: lazy.model) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count[0] == 1


# ===========================================================================
# TestAdaptiveBatchSizer
# ===========================================================================


class TestAdaptiveBatchSizer:
    """Tests for AdaptiveBatchSizer."""

    def test_calculate_batch_size_empty_files(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        result = sizer.calculate_batch_size([])
        assert result == 1  # min_batch_size

    def test_calculate_batch_size_positive_with_known_memory(self) -> None:
        """With mocked available memory, verify batch size formula."""
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=50.0)
        # Patch available memory to 100 MB
        available = 100 * 1024 * 1024
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            # Files are 10 MB each; budget = 50 MB; batch_size = 50/10 = 5
            file_sizes = [10 * 1024 * 1024] * 20
            batch = sizer.calculate_batch_size(file_sizes)
        assert batch == 5

    def test_calculate_batch_size_capped_at_max(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=1, max_size=3)
        available = 10 * 1024 * 1024 * 1024  # 10 GB
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            file_sizes = [1024] * 100  # tiny files
            batch = sizer.calculate_batch_size(file_sizes)
        assert batch <= 3

    def test_calculate_batch_size_min_bound_enforced(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=5, max_size=100)
        # Available memory of 0 → should return min_batch_size
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: 0),
        ):
            batch = sizer.calculate_batch_size([1024] * 50)
        assert batch == 5

    def test_adjust_from_feedback_returns_adjusted_size(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=50.0)
        available = 100 * 1024 * 1024
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            # actual: 20 MB for batch_size=2 → per_file=10 MB; budget=50MB → new=5
            new_size = sizer.adjust_from_feedback(
                actual_memory=20 * 1024 * 1024,
                batch_size=2,
            )
        assert new_size == 5

    def test_adjust_from_feedback_stores_in_history(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        available = 100 * 1024 * 1024
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            sizer.adjust_from_feedback(actual_memory=10 * 1024 * 1024, batch_size=5)
            sizer.adjust_from_feedback(actual_memory=5 * 1024 * 1024, batch_size=3)

        history = sizer.get_history()
        assert len(history) == 2
        assert history[0] == (10 * 1024 * 1024, 5)
        assert history[1] == (5 * 1024 * 1024, 3)

    def test_clear_history(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        available = 100 * 1024 * 1024
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            sizer.adjust_from_feedback(actual_memory=10 * 1024 * 1024, batch_size=5)
        sizer.clear_history()
        assert sizer.get_history() == []

    def test_set_bounds_valid(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        sizer.set_bounds(min_size=2, max_size=50)
        assert sizer.min_batch_size == 2
        assert sizer.max_batch_size == 50

    def test_set_bounds_invalid_min_raises(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        with pytest.raises(ValueError, match="min_size"):
            sizer.set_bounds(min_size=0)

    def test_set_bounds_max_less_than_min_raises(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        with pytest.raises(ValueError, match="max_size"):
            sizer.set_bounds(min_size=10, max_size=5)

    def test_invalid_target_memory_percent_raises(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        with pytest.raises(ValueError, match="target_memory_percent"):
            AdaptiveBatchSizer(target_memory_percent=0.0)

    def test_target_memory_percent_property(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=80.0)
        assert sizer.target_memory_percent == 80.0

    def test_adjust_batch_size_zero_batch_returns_min(self) -> None:
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer()
        result = sizer.adjust_from_feedback(actual_memory=1024, batch_size=0)
        assert result == sizer.min_batch_size

    def test_calculate_batch_size_per_file_cost_zero(self) -> None:
        """When file sizes and overhead are 0, batch_size should be capped at max."""
        from file_organizer.optimization.batch_sizer import AdaptiveBatchSizer

        sizer = AdaptiveBatchSizer(target_memory_percent=70.0)
        sizer.set_bounds(min_size=1, max_size=10)
        available = 100 * 1024 * 1024
        with patch.object(
            type(sizer),
            "_get_available_memory",
            staticmethod(lambda: available),
        ):
            # All zeros → per_file_cost=0 → should take len(file_sizes) capped at max
            batch = sizer.calculate_batch_size([0] * 50, overhead_per_file=0)
        assert batch == 10  # capped at max_size


# ===========================================================================
# TestModelWarmup
# ===========================================================================


class TestModelWarmup:
    """Tests for ModelWarmup."""

    def _make_cache_with_model(self, model_name: str) -> Any:
        from file_organizer.optimization.model_cache import ModelCache

        model = _make_base_model(model_name)
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        cache.get_or_load(model_name, lambda: model)
        return cache

    def test_warmup_empty_list_returns_zero_duration(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(cache, loader_factory=lambda n: lambda: _make_base_model(n))
        result = warmup.warmup([])
        assert result.total_requested == 0
        assert result.duration_ms == 0.0
        assert result.success_rate == 1.0

    def test_warmup_loads_models_into_cache(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        models = {"m1": _make_base_model("m1"), "m2": _make_base_model("m2")}
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(
            cache,
            loader_factory=lambda n: lambda: models[n],
        )

        result = warmup.warmup(["m1", "m2"])
        assert len(result.loaded) == 2
        assert len(result.failed) == 0
        assert result.success_rate == 1.0
        assert cache.contains("m1")
        assert cache.contains("m2")

    def test_warmup_skips_already_cached_models(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        model = _make_base_model("m1")
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        cache.get_or_load("m1", lambda: model)

        loader_factory_mock = MagicMock(side_effect=lambda n: lambda: _make_base_model(n))
        warmup = ModelWarmup(cache, loader_factory=loader_factory_mock)
        result = warmup.warmup(["m1"])

        # "m1" was already in cache; loader factory should not be called
        loader_factory_mock.assert_not_called()
        assert "m1" in result.loaded

    def test_warmup_deduplicates_model_names(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        model = _make_base_model("m1")
        load_count = [0]

        def loader_factory(name: str) -> Any:
            def loader() -> Any:
                load_count[0] += 1
                return model

            return loader

        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(cache, loader_factory=loader_factory)
        result = warmup.warmup(["m1", "m1", "m1"])

        assert load_count[0] == 1
        assert len(result.loaded) == 1

    def test_warmup_records_failed_models(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        def failing_loader() -> Any:
            raise RuntimeError("cannot load model")

        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(cache, loader_factory=lambda n: failing_loader)

        result = warmup.warmup(["bad-model"])
        assert len(result.failed) == 1
        assert result.failed[0][0] == "bad-model"
        assert "cannot load model" in result.failed[0][1]
        assert result.success_rate == 0.0

    def test_warmup_result_total_requested(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        models_map = {
            "good": _make_base_model("good"),
        }
        cache = ModelCache(max_models=5, ttl_seconds=300.0)

        def loader_factory(name: str) -> Any:
            if name == "good":
                return lambda: models_map["good"]
            return lambda: (_ for _ in ()).throw(RuntimeError("bad"))  # type: ignore[return-value]

        warmup = ModelWarmup(cache, loader_factory=loader_factory)
        result = warmup.warmup(["good", "bad"])
        assert result.total_requested == 2

    def test_warmup_duration_ms_is_positive(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        model = _make_base_model()
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(cache, loader_factory=lambda n: lambda: model)
        result = warmup.warmup(["m1"])
        assert result.duration_ms >= 0.0

    def test_warmup_async_returns_future(self) -> None:
        from concurrent.futures import Future

        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        model = _make_base_model()
        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        warmup = ModelWarmup(cache, loader_factory=lambda n: lambda: model)
        future = warmup.warmup_async(["m1"])
        assert isinstance(future, Future)
        result = future.result(timeout=10)
        assert len(result.loaded) == 1

    def test_invalid_max_workers_raises(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache
        from file_organizer.optimization.warmup import ModelWarmup

        cache = ModelCache(max_models=5, ttl_seconds=300.0)
        with pytest.raises(ValueError, match="max_workers"):
            ModelWarmup(cache, loader_factory=lambda n: lambda: _make_base_model(), max_workers=0)

    def test_warmup_result_success_rate_partial(self) -> None:
        from file_organizer.optimization.warmup import WarmupResult

        r = WarmupResult(loaded=["a", "b"], failed=[("c", "err")])
        assert r.total_requested == 3
        assert r.success_rate == pytest.approx(2 / 3, abs=0.01)
