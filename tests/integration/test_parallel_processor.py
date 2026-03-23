"""Integration tests for the parallel file processing package.

Covers ParallelProcessor, CheckpointManager, PriorityQueue, TaskScheduler,
RateThrottler, models (JobState, Checkpoint, BatchResult, FileResult), and config.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# ParallelConfig
# ---------------------------------------------------------------------------


class TestParallelConfig:
    """Tests for ParallelConfig dataclass validation."""

    def test_default_config(self) -> None:
        from file_organizer.parallel.config import ExecutorType, ParallelConfig

        cfg = ParallelConfig()
        assert cfg.max_workers is None
        assert cfg.executor_type == ExecutorType.THREAD
        assert cfg.retry_count == 2
        assert cfg.timeout_per_file == 60.0
        assert cfg.chunk_size == 10
        assert cfg.prefetch_depth == 2

    def test_custom_config(self) -> None:
        from file_organizer.parallel.config import ExecutorType, ParallelConfig

        cfg = ParallelConfig(
            max_workers=4,
            executor_type=ExecutorType.PROCESS,
            retry_count=0,
            timeout_per_file=5.0,
        )
        assert cfg.max_workers == 4
        assert cfg.executor_type == ExecutorType.PROCESS
        assert cfg.retry_count == 0
        assert cfg.timeout_per_file == 5.0

    def test_invalid_max_workers_raises(self) -> None:
        from file_organizer.parallel.config import ParallelConfig

        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            ParallelConfig(max_workers=0)

    def test_invalid_chunk_size_raises(self) -> None:
        from file_organizer.parallel.config import ParallelConfig

        with pytest.raises(ValueError, match="chunk_size must be >= 1"):
            ParallelConfig(chunk_size=0)

    def test_invalid_timeout_raises(self) -> None:
        from file_organizer.parallel.config import ParallelConfig

        with pytest.raises(ValueError, match="timeout_per_file must be > 0"):
            ParallelConfig(timeout_per_file=0.0)

    def test_negative_retry_raises(self) -> None:
        from file_organizer.parallel.config import ParallelConfig

        with pytest.raises(ValueError, match="retry_count must be >= 0"):
            ParallelConfig(retry_count=-1)

    def test_negative_prefetch_depth_raises(self) -> None:
        from file_organizer.parallel.config import ParallelConfig

        with pytest.raises(ValueError, match="prefetch_depth must be >= 0"):
            ParallelConfig(prefetch_depth=-1)


# ---------------------------------------------------------------------------
# Models — JobState, Checkpoint, FileResult, BatchResult
# ---------------------------------------------------------------------------


class TestJobState:
    """Tests for JobState serialization and lifecycle."""

    def test_default_job_state(self) -> None:
        from file_organizer.parallel.models import JobState, JobStatus

        job = JobState(id="job-001")
        assert job.id == "job-001"
        assert job.status == JobStatus.PENDING
        assert job.total_files == 0
        assert job.completed_files == 0
        assert job.failed_files == 0
        assert job.error is None

    def test_job_state_roundtrip(self) -> None:
        from file_organizer.parallel.models import JobState, JobStatus

        now = datetime.now(UTC)
        job = JobState(
            id="job-rt",
            status=JobStatus.RUNNING,
            created=now,
            updated=now,
            total_files=100,
            completed_files=50,
            failed_files=5,
            config={"batch": 10},
            error=None,
        )
        data = job.to_dict()
        restored = JobState.from_dict(data)
        assert restored.id == "job-rt"
        assert restored.status == JobStatus.RUNNING
        assert restored.total_files == 100
        assert restored.completed_files == 50
        assert restored.failed_files == 5
        assert restored.error is None

    def test_job_state_with_error_roundtrip(self) -> None:
        from file_organizer.parallel.models import JobState, JobStatus

        job = JobState(id="job-err", status=JobStatus.FAILED, error="disk full")
        data = job.to_dict()
        restored = JobState.from_dict(data)
        assert restored.status == JobStatus.FAILED
        assert restored.error == "disk full"

    def test_all_job_statuses(self) -> None:
        from file_organizer.parallel.models import JobStatus

        expected = {"pending", "running", "paused", "completed", "failed"}
        actual = {s.value for s in JobStatus}
        assert actual == expected


class TestJobSummary:
    """Tests for JobSummary.from_job_state."""

    def test_progress_calculation(self) -> None:
        from file_organizer.parallel.models import JobState, JobStatus, JobSummary

        job = JobState(
            id="s1",
            status=JobStatus.RUNNING,
            total_files=200,
            completed_files=50,
        )
        summary = JobSummary.from_job_state(job)
        assert summary.id == "s1"
        assert summary.progress_percent == 25.0
        assert summary.status == JobStatus.RUNNING

    def test_zero_total_files(self) -> None:
        from file_organizer.parallel.models import JobState, JobSummary

        job = JobState(id="s2", total_files=0)
        summary = JobSummary.from_job_state(job)
        assert summary.progress_percent == 0.0


class TestCheckpointModel:
    """Tests for the Checkpoint dataclass."""

    def test_checkpoint_roundtrip(self) -> None:
        from file_organizer.parallel.models import Checkpoint

        completed = [Path("/a/b.txt"), Path("/c/d.txt")]
        pending = [Path("/e/f.txt")]
        cp = Checkpoint(
            job_id="cp-test",
            completed_paths=completed,
            pending_paths=pending,
            file_hashes={"/a/b.txt": "abc123"},
        )
        data = cp.to_dict()
        restored = Checkpoint.from_dict(data)
        assert restored.job_id == "cp-test"
        assert len(restored.completed_paths) == 2
        assert len(restored.pending_paths) == 1
        assert restored.file_hashes["/a/b.txt"] == "abc123"

    def test_empty_checkpoint(self) -> None:
        from file_organizer.parallel.models import Checkpoint

        cp = Checkpoint(job_id="empty")
        assert cp.completed_paths == []
        assert cp.pending_paths == []
        assert cp.file_hashes == {}


class TestBatchResult:
    """Tests for BatchResult and FileResult data classes."""

    def test_empty_batch_result(self) -> None:
        from file_organizer.parallel.result import BatchResult

        result = BatchResult()
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        summary = result.summary()
        assert "0 files" in summary

    def test_batch_result_with_failures(self) -> None:
        from file_organizer.parallel.result import BatchResult, FileResult

        results = [
            FileResult(path=Path("a.txt"), success=True, duration_ms=5.0),
            FileResult(path=Path("b.txt"), success=False, error="oops", duration_ms=1.0),
        ]
        batch = BatchResult(
            total=2,
            succeeded=1,
            failed=1,
            results=results,
            total_duration_ms=10.0,
            files_per_second=200.0,
        )
        summary = batch.summary()
        assert "Failures:" in summary
        assert "b.txt" in summary
        assert "oops" in summary

    def test_batch_result_many_failures_truncated(self) -> None:
        from file_organizer.parallel.result import BatchResult, FileResult

        results = [FileResult(path=Path(f"{i}.txt"), success=False, error="err") for i in range(10)]
        batch = BatchResult(total=10, succeeded=0, failed=10, results=results)
        summary = batch.summary()
        assert "and 5 more" in summary

    def test_file_result_str_success(self) -> None:
        from file_organizer.parallel.result import FileResult

        fr = FileResult(path=Path("x.txt"), success=True, duration_ms=3.0)
        text = str(fr)
        assert text.startswith("OK")
        assert "x.txt" in text

    def test_file_result_str_failure(self) -> None:
        from file_organizer.parallel.result import FileResult

        fr = FileResult(path=Path("y.txt"), success=False, error="gone", duration_ms=1.0)
        text = str(fr)
        assert text.startswith("FAIL")
        assert "gone" in text


# ---------------------------------------------------------------------------
# CheckpointManager (uses tmp_path)
# ---------------------------------------------------------------------------


class TestCheckpointManager:
    """Tests for CheckpointManager persistence and state updates."""

    def test_create_and_load_checkpoint(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        cp = mgr.create_checkpoint("job-a", [f1], [f2])

        assert cp.job_id == "job-a"
        assert f1 in cp.completed_paths
        assert f2 in cp.pending_paths
        assert str(f1) in cp.file_hashes
        assert str(f2) in cp.file_hashes

        loaded = mgr.load_checkpoint("job-a")
        assert loaded is not None
        assert loaded.job_id == "job-a"
        assert len(loaded.completed_paths) == 1
        assert len(loaded.pending_paths) == 1

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        result = mgr.load_checkpoint("ghost-job")
        assert result is None

    def test_delete_checkpoint(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        f = tmp_path / "f.txt"
        f.write_text("data", encoding="utf-8")
        mgr.create_checkpoint("del-job", [f], [])

        assert mgr.load_checkpoint("del-job") is not None
        deleted = mgr.delete_checkpoint("del-job")
        assert deleted is True
        assert mgr.load_checkpoint("del-job") is None

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        result = mgr.delete_checkpoint("no-such-job")
        assert result is False

    def test_update_checkpoint_state(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager
        from file_organizer.parallel.models import Checkpoint

        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")

        cp = Checkpoint(job_id="upd", completed_paths=[], pending_paths=[f1, f2])
        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        mgr.update_checkpoint_state(cp, f1)

        assert f1 in cp.completed_paths
        assert f1 not in cp.pending_paths

    def test_has_file_changed_after_modification(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        f = tmp_path / "change_me.txt"
        f.write_text("original", encoding="utf-8")

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        cp = mgr.create_checkpoint("chg-job", [f], [])
        assert mgr.has_file_changed(cp, f) is False

        f.write_text("modified content", encoding="utf-8")
        assert mgr.has_file_changed(cp, f) is True

    def test_has_file_changed_unknown_path_returns_true(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager
        from file_organizer.parallel.models import Checkpoint

        cp = Checkpoint(job_id="unk", file_hashes={})
        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        result = mgr.has_file_changed(cp, tmp_path / "nonexistent.txt")
        assert result is True

    def test_update_checkpoint_full_cycle(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("x", encoding="utf-8")
        f2.write_text("y", encoding="utf-8")

        mgr = CheckpointManager(checkpoints_dir=tmp_path / "checkpoints")
        mgr.create_checkpoint("full-job", [], [f1, f2])

        updated = mgr.update_checkpoint("full-job", f1)
        assert updated is not None
        assert f1 in updated.completed_paths

    def test_checkpoints_dir_property(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import CheckpointManager

        cdir = tmp_path / "my_checkpoints"
        mgr = CheckpointManager(checkpoints_dir=cdir)
        assert mgr.checkpoints_dir == cdir


class TestComputeFileHash:
    """Tests for the standalone compute_file_hash function."""

    def test_hash_is_hex_string(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import compute_file_hash

        f = tmp_path / "hash_me.txt"
        f.write_text("test content", encoding="utf-8")
        h = compute_file_hash(f)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import compute_file_hash

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same", encoding="utf-8")
        f2.write_text("same", encoding="utf-8")
        assert compute_file_hash(f1) == compute_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import compute_file_hash

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content_a", encoding="utf-8")
        f2.write_text("content_b", encoding="utf-8")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        from file_organizer.parallel.checkpoint import compute_file_hash

        with pytest.raises(OSError):
            compute_file_hash(tmp_path / "does_not_exist.txt")


# ---------------------------------------------------------------------------
# ParallelProcessor
# ---------------------------------------------------------------------------


class TestParallelProcessor:
    """Tests for ParallelProcessor.process_batch."""

    def test_empty_batch_returns_empty_result(self) -> None:
        from file_organizer.parallel.config import ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        cfg = ParallelConfig(max_workers=2, retry_count=0, timeout_per_file=30.0)
        proc = ParallelProcessor(cfg)
        result = proc.process_batch([], lambda p: p.name)
        assert result.total == 0
        assert result.succeeded == 0

    def test_batch_processes_all_files(self, tmp_path: Path) -> None:
        from file_organizer.parallel.config import ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        files = []
        for i in range(5):
            f = tmp_path / f"f{i}.txt"
            f.write_text("data", encoding="utf-8")
            files.append(f)

        cfg = ParallelConfig(max_workers=2, retry_count=0, timeout_per_file=30.0)
        proc = ParallelProcessor(cfg)
        result = proc.process_batch(files, lambda p: p.name.upper())

        assert result.total == 5
        assert result.succeeded == 5
        assert result.failed == 0

    def test_batch_reports_failures(self, tmp_path: Path) -> None:
        from file_organizer.parallel.config import ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        files = [tmp_path / "x.txt", tmp_path / "y.txt"]
        for f in files:
            f.write_text("ok", encoding="utf-8")

        def always_fail(p: Path) -> None:
            raise RuntimeError("boom")

        cfg = ParallelConfig(max_workers=2, retry_count=0, timeout_per_file=30.0)
        proc = ParallelProcessor(cfg)
        result = proc.process_batch(files, always_fail)

        assert result.total == 2
        assert result.failed == 2
        assert result.succeeded == 0

    def test_config_property(self) -> None:
        from file_organizer.parallel.config import ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        cfg = ParallelConfig(max_workers=4)
        proc = ParallelProcessor(cfg)
        assert proc.config is cfg

    def test_progress_callback_invoked(self, tmp_path: Path) -> None:
        from file_organizer.parallel.config import ParallelConfig
        from file_organizer.parallel.processor import ParallelProcessor

        calls: list[int] = []

        def callback(completed: int, total: int, _result: object) -> None:
            calls.append(completed)

        files = []
        for i in range(3):
            f = tmp_path / f"cb{i}.txt"
            f.write_text("x", encoding="utf-8")
            files.append(f)

        cfg = ParallelConfig(
            max_workers=1, retry_count=0, timeout_per_file=30.0, progress_callback=callback
        )
        proc = ParallelProcessor(cfg)
        proc.process_batch(files, lambda p: "ok")
        assert len(calls) == 3


# ---------------------------------------------------------------------------
# PriorityQueue
# ---------------------------------------------------------------------------


class TestPriorityQueue:
    """Tests for the thread-safe PriorityQueue."""

    def test_enqueue_dequeue_basic(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        item = QueueItem(id="a", path=tmp_path / "a.txt", priority=5)
        q.enqueue(item)
        assert q.size == 1
        dequeued = q.dequeue()
        assert dequeued is not None
        assert dequeued.id == "a"

    def test_higher_priority_dequeued_first(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        q.enqueue(QueueItem(id="low", path=tmp_path / "low.txt", priority=1))
        q.enqueue(QueueItem(id="high", path=tmp_path / "high.txt", priority=10))
        q.enqueue(QueueItem(id="mid", path=tmp_path / "mid.txt", priority=5))

        first = q.dequeue()
        assert first is not None
        assert first.id == "high"

        second = q.dequeue()
        assert second is not None
        assert second.id == "mid"

    def test_empty_queue_dequeue_returns_none(self) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue

        q = PriorityQueue()
        assert q.dequeue() is None

    def test_peek_does_not_remove(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        item = QueueItem(id="p", path=tmp_path / "p.txt", priority=3)
        q.enqueue(item)
        peeked = q.peek()
        assert peeked is not None
        assert peeked.id == "p"
        assert q.size == 1

    def test_remove_by_id(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        q.enqueue(QueueItem(id="r1", path=tmp_path / "r1.txt", priority=1))
        q.enqueue(QueueItem(id="r2", path=tmp_path / "r2.txt", priority=2))
        assert q.remove("r1") is True
        assert q.size == 1
        assert q.remove("ghost") is False

    def test_reorder_changes_priority(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        q.enqueue(QueueItem(id="x", path=tmp_path / "x.txt", priority=1))
        q.enqueue(QueueItem(id="y", path=tmp_path / "y.txt", priority=2))
        q.reorder("x", 10)
        first = q.dequeue()
        assert first is not None
        assert first.id == "x"

    def test_clear_empties_queue(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        q.enqueue(QueueItem(id="z", path=tmp_path / "z.txt"))
        q.clear()
        assert q.is_empty is True

    def test_items_sorted_by_priority(self, tmp_path: Path) -> None:
        from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem

        q = PriorityQueue()
        for pri in [3, 1, 4, 1, 5]:
            q.enqueue(
                QueueItem(
                    id=str(pri) + str(time.monotonic()), path=tmp_path / "f.txt", priority=pri
                )
            )
        items = q.items()
        priorities = [item.priority for item in items]
        assert priorities == sorted(priorities, reverse=True)


# ---------------------------------------------------------------------------
# TaskScheduler
# ---------------------------------------------------------------------------


class TestTaskScheduler:
    """Tests for TaskScheduler file ordering strategies."""

    def test_size_asc_sorts_smallest_first(self, tmp_path: Path) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        small = tmp_path / "small.txt"
        large = tmp_path / "large.txt"
        small.write_text("hi", encoding="utf-8")
        large.write_text("x" * 1000, encoding="utf-8")

        scheduler = TaskScheduler()
        result = scheduler.schedule([large, small], PriorityStrategy.SIZE_ASC)
        assert result[0] == small
        assert result[1] == large

    def test_size_desc_sorts_largest_first(self, tmp_path: Path) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        small = tmp_path / "small.txt"
        large = tmp_path / "large.txt"
        small.write_text("x", encoding="utf-8")
        large.write_text("y" * 500, encoding="utf-8")

        scheduler = TaskScheduler()
        result = scheduler.schedule([small, large], PriorityStrategy.SIZE_DESC)
        assert result[0] == large

    def test_type_grouped_groups_by_extension(self, tmp_path: Path) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        py1 = tmp_path / "b.py"
        py2 = tmp_path / "a.py"
        txt = tmp_path / "c.txt"
        for f in [py1, py2, txt]:
            f.touch()

        scheduler = TaskScheduler()
        result = scheduler.schedule([py1, txt, py2], PriorityStrategy.TYPE_GROUPED)
        exts = [p.suffix for p in result]
        # TYPE_GROUPED sorts by extension then by name within each group:
        # .py group (a.py, b.py) before .txt group (c.txt)
        assert exts == [".py", ".py", ".txt"]

    def test_custom_strategy(self, tmp_path: Path) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        files = [tmp_path / "c.txt", tmp_path / "a.txt", tmp_path / "b.txt"]
        for f in files:
            f.touch()

        scheduler = TaskScheduler()
        result = scheduler.schedule(files, PriorityStrategy.CUSTOM, priority_fn=lambda p: p.name)
        assert [f.name for f in result] == ["a.txt", "b.txt", "c.txt"]

    def test_custom_without_fn_raises(self, tmp_path: Path) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        scheduler = TaskScheduler()
        with pytest.raises(ValueError, match="priority_fn is required"):
            scheduler.schedule([tmp_path / "x.txt"], PriorityStrategy.CUSTOM)

    def test_empty_list_returns_empty(self) -> None:
        from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.schedule([], PriorityStrategy.SIZE_ASC) == []


# ---------------------------------------------------------------------------
# RateThrottler
# ---------------------------------------------------------------------------


class TestRateThrottler:
    """Tests for the token-bucket RateThrottler."""

    def test_initial_acquire_succeeds(self) -> None:
        from file_organizer.parallel.throttle import RateThrottler

        throttler = RateThrottler(max_rate=10.0)
        result = throttler.acquire()
        assert result is True

    def test_exceed_rate_returns_false(self) -> None:
        from file_organizer.parallel.throttle import RateThrottler

        throttler = RateThrottler(max_rate=2.0)
        results = [throttler.acquire() for _ in range(5)]
        assert True in results
        assert False in results

    def test_invalid_max_rate_raises(self) -> None:
        from file_organizer.parallel.throttle import RateThrottler

        with pytest.raises(ValueError, match="max_rate must be > 0"):
            RateThrottler(max_rate=0)

    def test_invalid_window_raises(self) -> None:
        from file_organizer.parallel.throttle import RateThrottler

        with pytest.raises(ValueError, match="window_seconds must be > 0"):
            RateThrottler(max_rate=1.0, window_seconds=0)

    def test_stats_returns_data(self) -> None:
        from file_organizer.parallel.throttle import RateThrottler

        throttler = RateThrottler(max_rate=5.0)
        throttler.acquire()
        stats = throttler.stats()
        assert stats.max_rate == 5.0
        assert stats.allowed >= 1


# ---------------------------------------------------------------------------
# Persistence (ResourceManager)
# ---------------------------------------------------------------------------


class TestPersistence:
    """Tests for parallel persistence layer."""

    def test_save_and_load_job_state(self, tmp_path: Path) -> None:
        from file_organizer.parallel.models import JobState, JobStatus
        from file_organizer.parallel.persistence import JobPersistence

        mgr = JobPersistence(jobs_dir=tmp_path / "jobs")
        job = JobState(id="persist-1", status=JobStatus.RUNNING, total_files=10)
        mgr.save_job(job)

        loaded = mgr.load_job("persist-1")
        assert loaded is not None
        assert loaded.id == "persist-1"
        assert loaded.status == JobStatus.RUNNING
        assert loaded.total_files == 10

    def test_load_missing_job_returns_none(self, tmp_path: Path) -> None:
        from file_organizer.parallel.persistence import JobPersistence

        mgr = JobPersistence(jobs_dir=tmp_path / "jobs")
        assert mgr.load_job("ghost") is None

    def test_list_jobs(self, tmp_path: Path) -> None:
        from file_organizer.parallel.models import JobState
        from file_organizer.parallel.persistence import JobPersistence

        mgr = JobPersistence(jobs_dir=tmp_path / "jobs")
        for i in range(3):
            mgr.save_job(JobState(id=f"j{i}"))

        jobs = mgr.list_jobs()
        assert len(jobs) == 3

    def test_delete_job(self, tmp_path: Path) -> None:
        from file_organizer.parallel.models import JobState
        from file_organizer.parallel.persistence import JobPersistence

        mgr = JobPersistence(jobs_dir=tmp_path / "jobs")
        mgr.save_job(JobState(id="to-del"))
        assert mgr.delete_job("to-del") is True
        assert mgr.load_job("to-del") is None
        assert mgr.delete_job("to-del") is False
