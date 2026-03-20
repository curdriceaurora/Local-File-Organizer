"""Integration tests for core API infrastructure modules.

Covers:
  - api/jobs.py  — in-memory job store
  - api/cache.py — InMemoryCache and build_cache_backend
  - api/routers/health.py — health endpoint
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from threading import Thread
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.cache import InMemoryCache, build_cache_backend
from file_organizer.api.jobs import (
    JobState,
    create_job,
    get_job,
    job_count,
    list_jobs,
    update_job,
)
from file_organizer.api.routers.health import router as health_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain_jobs() -> None:
    """Remove all jobs from the in-memory store for test isolation.

    Jobs are module-level globals so we poke them out between tests.
    """
    import file_organizer.api.jobs as _jobs_mod

    with _jobs_mod._JOB_STORE_LOCK:
        _jobs_mod._JOB_STORE.clear()


# ---------------------------------------------------------------------------
# api/jobs.py
# ---------------------------------------------------------------------------


class TestJobCreation:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_create_job_returns_job_state(self) -> None:
        job = create_job("organize")
        assert isinstance(job, JobState)
        assert job.job_type == "organize"
        assert job.status == "queued"

    def test_create_job_has_unique_id(self) -> None:
        job1 = create_job("organize")
        job2 = create_job("organize")
        assert job1.job_id != job2.job_id

    def test_create_job_timestamps_set(self) -> None:
        before = datetime.now(UTC)
        job = create_job("scan")
        after = datetime.now(UTC)
        assert before <= job.created_at <= after
        assert job.created_at == job.updated_at

    def test_create_job_no_result_or_error(self) -> None:
        job = create_job("dedupe")
        assert job.result is None
        assert job.error is None


class TestGetJob:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_get_existing_job(self) -> None:
        job = create_job("organize")
        found = get_job(job.job_id)
        assert found is not None
        assert found.job_id == job.job_id

    def test_get_missing_job_returns_none(self) -> None:
        result = get_job("nonexistent-id-xyz")
        assert result is None

    def test_get_job_does_not_modify_state(self) -> None:
        job = create_job("organize")
        original_status = job.status
        get_job(job.job_id)
        found = get_job(job.job_id)
        assert found is not None
        assert found.status == original_status


class TestUpdateJob:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_update_status_to_running(self) -> None:
        job = create_job("organize")
        updated = update_job(job.job_id, status="running")
        assert updated is not None
        assert updated.status == "running"

    def test_update_status_to_completed_with_result(self) -> None:
        job = create_job("organize")
        result = {"processed_files": 5, "total_files": 5}
        updated = update_job(job.job_id, status="completed", result=result)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.result == result

    def test_update_status_to_failed_with_error(self) -> None:
        job = create_job("organize")
        updated = update_job(job.job_id, status="failed", error="disk full")
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error == "disk full"

    def test_update_missing_job_returns_none(self) -> None:
        result = update_job("no-such-job", status="running")
        assert result is None

    def test_update_invalid_field_raises_value_error(self) -> None:
        job = create_job("organize")
        with pytest.raises(ValueError, match="Unknown job fields"):
            update_job(job.job_id, nonexistent_field="value")

    def test_update_bumps_updated_at(self) -> None:
        job = create_job("organize")
        original_ts = job.updated_at
        updated = update_job(job.job_id, status="running")
        assert updated is not None
        assert updated.updated_at >= original_ts


class TestListJobs:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_list_jobs_empty(self) -> None:
        assert list_jobs() == []

    def test_list_jobs_returns_all(self) -> None:
        create_job("organize")
        create_job("dedupe")
        jobs = list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filtered_by_type(self) -> None:
        create_job("organize")
        create_job("organize")
        create_job("dedupe")
        jobs = list_jobs(job_type="organize")
        assert len(jobs) == 2
        assert all(j.job_type == "organize" for j in jobs)

    def test_list_jobs_filtered_by_status(self) -> None:
        j1 = create_job("organize")
        j2 = create_job("organize")
        update_job(j1.job_id, status="running")
        update_job(j2.job_id, status="completed")
        running = list_jobs(statuses={"running"})
        assert len(running) == 1
        assert running[0].status == "running"

    def test_list_jobs_respects_limit(self) -> None:
        for _ in range(5):
            create_job("scan")
        result = list_jobs(limit=3)
        assert len(result) == 3

    def test_list_jobs_newest_first(self) -> None:
        create_job("organize")
        j2 = create_job("organize")
        jobs = list_jobs()
        # Most recently updated should be first
        assert jobs[0].job_id == j2.job_id or jobs[0].updated_at >= jobs[1].updated_at


class TestJobCount:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_job_count_empty(self) -> None:
        assert job_count() == 0

    def test_job_count_counts_active_only(self) -> None:
        j1 = create_job("organize")
        create_job("organize")
        assert job_count() == 2  # both queued (active)
        update_job(j1.job_id, status="completed")
        assert job_count() == 1  # j1 done, j2 still queued

    def test_job_count_running_is_active(self) -> None:
        j = create_job("organize")
        update_job(j.job_id, status="running")
        assert job_count() == 1

    def test_job_count_failed_is_inactive(self) -> None:
        j = create_job("organize")
        update_job(j.job_id, status="failed", error="boom")
        assert job_count() == 0


class TestJobPruning:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_expired_jobs_pruned_on_get(self) -> None:
        import file_organizer.api.jobs as _jobs_mod

        job = create_job("organize")

        # Force expiry by backdating updated_at
        with _jobs_mod._JOB_STORE_LOCK:
            stored = _jobs_mod._JOB_STORE[job.job_id]
            stored.updated_at = datetime.now(UTC) - timedelta(hours=25)

        result = get_job(job.job_id)
        assert result is None

    def test_max_jobs_enforced_on_create(self) -> None:
        import file_organizer.api.jobs as _jobs_mod

        original_max = _jobs_mod._MAX_JOBS
        _jobs_mod._MAX_JOBS = 5
        try:
            for _ in range(7):
                create_job("scan")
            with _jobs_mod._JOB_STORE_LOCK:
                count = len(_jobs_mod._JOB_STORE)
            assert count <= 5
        finally:
            _jobs_mod._MAX_JOBS = original_max


class TestJobThreadSafety:
    def setup_method(self) -> None:
        _drain_jobs()

    def test_concurrent_creates_all_stored(self) -> None:
        created: list[JobState] = []
        lock = __import__("threading").Lock()

        def _create() -> None:
            job = create_job("organize")
            with lock:
                created.append(job)

        threads = [Thread(target=_create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(created) == 20
        ids = {j.job_id for j in created}
        assert len(ids) == 20  # all unique


# ---------------------------------------------------------------------------
# api/cache.py
# ---------------------------------------------------------------------------


class TestInMemoryCache:
    def test_set_and_get(self) -> None:
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=10)
        assert cache.get("key1") == "value1"

    def test_get_missing_returns_none(self) -> None:
        cache = InMemoryCache()
        assert cache.get("no-such-key") is None

    def test_delete_removes_key(self) -> None:
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=10)
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent_key_no_error(self) -> None:
        cache = InMemoryCache()
        cache.delete("phantom")  # Should not raise

    def test_ttl_expiry(self) -> None:
        cache = InMemoryCache()
        cache.set("key1", "val", ttl_seconds=1)
        assert cache.get("key1") == "val"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cache.get("key1") is None:
                break
        assert cache.get("key1") is None

    def test_close_clears_all(self) -> None:
        cache = InMemoryCache()
        for i in range(5):
            cache.set(f"key{i}", f"val{i}", ttl_seconds=60)
        cache.close()
        for i in range(5):
            assert cache.get(f"key{i}") is None

    def test_overwrite_existing_key(self) -> None:
        cache = InMemoryCache()
        cache.set("key", "old", ttl_seconds=60)
        cache.set("key", "new", ttl_seconds=60)
        assert cache.get("key") == "new"

    def test_thread_safe_concurrent_writes(self) -> None:
        cache = InMemoryCache()
        errors: list[Exception] = []

        def _write(i: int) -> None:
            try:
                cache.set(f"key{i}", f"val{i}", ttl_seconds=60)
            except Exception as exc:
                errors.append(exc)

        threads = [Thread(target=_write, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_ttl_min_1_second(self) -> None:
        """TTL is clamped to at least 1 second even when 0 is passed."""
        cache = InMemoryCache()
        cache.set("key", "val", ttl_seconds=0)
        # Should not immediately expire (clamped to 1s)
        assert cache.get("key") == "val"


class TestBuildCacheBackend:
    def test_no_redis_url_returns_in_memory(self) -> None:
        backend = build_cache_backend(None)
        assert isinstance(backend, InMemoryCache)

    def test_empty_redis_url_returns_in_memory(self) -> None:
        backend = build_cache_backend("")
        assert isinstance(backend, InMemoryCache)

    def test_invalid_redis_url_scheme_falls_back(self) -> None:
        backend = build_cache_backend("http://localhost:6379")
        assert isinstance(backend, InMemoryCache)

    def test_valid_url_returns_redis_cache_or_fallback(self) -> None:
        # build_cache_backend with a valid redis:// URL may return RedisCache
        # (which silently swallows connection errors) or InMemoryCache if the
        # package is missing. Either is acceptable — we just verify it doesn't
        # raise.
        from file_organizer.api.cache import InMemoryCache, RedisCache

        backend = build_cache_backend("redis://localhost:9")
        assert isinstance(backend, (InMemoryCache, RedisCache))


# ---------------------------------------------------------------------------
# api/routers/health.py
# ---------------------------------------------------------------------------


@pytest.fixture()
def health_client() -> TestClient:
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_ok_returns_200(self, health_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.health_check",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "version": "1.0.0",
                    "provider": "ollama",
                    "ollama": True,
                }
            ),
        ):
            r = health_client.get("/health")
        assert r.status_code == 200

    def test_health_ok_shape(self, health_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.health_check",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "version": "1.2.3",
                    "provider": "ollama",
                    "ollama": True,
                }
            ),
        ):
            r = health_client.get("/health")
        body = r.json()
        assert body["status"] == "ok"
        assert body["readiness"] == "ready"
        assert body["provider"] == "ollama"
        assert body["ollama"] is True
        assert body["version"] == "1.2.3"
        assert "uptime" in body

    def test_health_degraded_returns_207(self, health_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.health_check",
            new=AsyncMock(
                return_value={
                    "status": "degraded",
                    "version": "0.9.0",
                    "provider": "ollama",
                    "ollama": False,
                }
            ),
        ):
            r = health_client.get("/health")
        assert r.status_code == 207
        assert r.json()["readiness"] == "starting"

    def test_health_error_returns_503(self, health_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.health_check",
            new=AsyncMock(side_effect=RuntimeError("facade exploded")),
        ):
            r = health_client.get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "error"
        assert r.json()["readiness"] == "unhealthy"

    def test_health_unknown_status_is_ready(self, health_client: TestClient) -> None:
        with patch(
            "file_organizer.api.service_facade.ServiceFacade.health_check",
            new=AsyncMock(return_value={"status": "unknown", "provider": "openai"}),
        ):
            r = health_client.get("/health")
        assert r.status_code == 200
        assert r.json()["readiness"] == "ready"
