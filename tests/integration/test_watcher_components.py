"""Integration tests for file system watcher components.

Covers:
  - watcher/config.py  — WatcherConfig, _matches_pattern
  - watcher/queue.py   — EventQueue, FileEvent, EventType
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.watcher.config import WatcherConfig
from file_organizer.watcher.queue import EventQueue, EventType, FileEvent

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# WatcherConfig
# ---------------------------------------------------------------------------


class TestWatcherConfigInit:
    def test_default_recursive(self) -> None:
        cfg = WatcherConfig()
        assert cfg.recursive is True

    def test_default_debounce(self) -> None:
        cfg = WatcherConfig()
        assert cfg.debounce_seconds == 2.0

    def test_default_batch_size(self) -> None:
        cfg = WatcherConfig()
        assert cfg.batch_size == 10

    def test_default_no_file_types(self) -> None:
        cfg = WatcherConfig()
        assert cfg.file_types is None

    def test_default_exclude_patterns_populated(self) -> None:
        cfg = WatcherConfig()
        assert len(cfg.exclude_patterns) > 0
        assert "*.tmp" in cfg.exclude_patterns

    def test_watch_directories_normalized_to_path(self, tmp_path: Path) -> None:
        cfg = WatcherConfig(watch_directories=[str(tmp_path)])
        assert isinstance(cfg.watch_directories[0], Path)

    def test_file_types_normalized_with_dot(self) -> None:
        cfg = WatcherConfig(file_types=["txt", ".pdf"])
        assert ".txt" in cfg.file_types
        assert ".pdf" in cfg.file_types

    def test_negative_debounce_raises(self) -> None:
        with pytest.raises(ValueError):
            WatcherConfig(debounce_seconds=-1.0)

    def test_zero_batch_size_raises(self) -> None:
        with pytest.raises(ValueError):
            WatcherConfig(batch_size=0)

    def test_custom_values(self, tmp_path: Path) -> None:
        cfg = WatcherConfig(
            watch_directories=[tmp_path],
            recursive=False,
            debounce_seconds=0.5,
            batch_size=5,
            file_types=[".py", ".txt"],
        )
        assert cfg.recursive is False
        assert cfg.debounce_seconds == 0.5
        assert cfg.batch_size == 5


class TestWatcherConfigShouldInclude:
    def test_includes_normal_txt_file(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        f = tmp_path / "document.txt"
        assert cfg.should_include_file(f) is True

    def test_excludes_tmp_file(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        f = tmp_path / "upload.tmp"
        assert cfg.should_include_file(f) is False

    def test_excludes_pyc_file(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        f = tmp_path / "module.pyc"
        assert cfg.should_include_file(f) is False

    def test_excludes_ds_store(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        f = tmp_path / ".DS_Store"
        assert cfg.should_include_file(f) is False

    def test_file_type_filter_includes_matching(self, tmp_path: Path) -> None:
        cfg = WatcherConfig(file_types=[".py"])
        assert cfg.should_include_file(tmp_path / "script.py") is True

    def test_file_type_filter_excludes_non_matching(self, tmp_path: Path) -> None:
        cfg = WatcherConfig(file_types=[".py"])
        assert cfg.should_include_file(tmp_path / "data.txt") is False

    def test_excludes_git_directory_files(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        # .git itself should be excluded
        git_path = tmp_path / ".git"
        assert cfg.should_include_file(git_path) is False

    def test_custom_exclude_pattern(self, tmp_path: Path) -> None:
        cfg = WatcherConfig(exclude_patterns=["*.log"])
        assert cfg.should_include_file(tmp_path / "app.log") is False
        assert cfg.should_include_file(tmp_path / "app.txt") is True

    def test_swp_file_excluded(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        assert cfg.should_include_file(tmp_path / "file.swp") is False

    def test_pycache_excluded(self, tmp_path: Path) -> None:
        cfg = WatcherConfig()
        pc = tmp_path / "__pycache__"
        assert cfg.should_include_file(pc) is False


# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------


class TestEventType:
    def test_values(self) -> None:
        assert EventType.CREATED == "created"
        assert EventType.MODIFIED == "modified"
        assert EventType.DELETED == "deleted"
        assert EventType.MOVED == "moved"


# ---------------------------------------------------------------------------
# FileEvent
# ---------------------------------------------------------------------------


def _make_event(
    event_type: EventType = EventType.CREATED,
    path: Path | None = None,
) -> FileEvent:
    return FileEvent(
        event_type=event_type,
        path=path or Path("test.txt"),
        timestamp=datetime.now(UTC),
    )


class TestFileEvent:
    def test_created_event(self) -> None:
        e = _make_event(EventType.CREATED)
        assert e.event_type == EventType.CREATED

    def test_event_is_frozen(self) -> None:
        e = _make_event()
        with pytest.raises((AttributeError, TypeError)):
            e.event_type = EventType.MODIFIED  # type: ignore[misc]

    def test_default_is_directory_false(self) -> None:
        e = _make_event()
        assert e.is_directory is False

    def test_default_dest_path_none(self) -> None:
        e = _make_event()
        assert e.dest_path is None

    def test_move_event_has_dest_path(self, tmp_path: Path) -> None:
        e = FileEvent(
            event_type=EventType.MOVED,
            path=tmp_path / "old.txt",
            timestamp=datetime.now(UTC),
            dest_path=tmp_path / "new.txt",
        )
        assert e.dest_path is not None


# ---------------------------------------------------------------------------
# EventQueue
# ---------------------------------------------------------------------------


class TestEventQueueBasics:
    def test_starts_empty(self) -> None:
        q = EventQueue()
        assert q.is_empty is True
        assert q.size == 0

    def test_enqueue_increases_size(self) -> None:
        q = EventQueue()
        q.enqueue(_make_event())
        assert q.size == 1

    def test_dequeue_batch_returns_events(self) -> None:
        q = EventQueue()
        q.enqueue(_make_event(EventType.CREATED))
        batch = q.dequeue_batch()
        assert len(batch) == 1
        assert batch[0].event_type == EventType.CREATED

    def test_dequeue_batch_empties_queue(self) -> None:
        q = EventQueue()
        for _ in range(3):
            q.enqueue(_make_event())
        q.dequeue_batch(max_size=3)
        assert q.is_empty

    def test_dequeue_batch_respects_max_size(self) -> None:
        q = EventQueue()
        for _ in range(5):
            q.enqueue(_make_event())
        batch = q.dequeue_batch(max_size=2)
        assert len(batch) == 2
        assert q.size == 3

    def test_dequeue_empty_queue_returns_empty_list(self) -> None:
        q = EventQueue()
        batch = q.dequeue_batch()
        assert batch == []

    def test_peek_returns_first_event(self) -> None:
        q = EventQueue()
        e1 = _make_event(EventType.CREATED, Path("a.txt"))
        e2 = _make_event(EventType.MODIFIED, Path("b.txt"))
        q.enqueue(e1)
        q.enqueue(e2)
        assert q.peek() is e1

    def test_peek_empty_returns_none(self) -> None:
        q = EventQueue()
        assert q.peek() is None

    def test_clear_removes_all(self) -> None:
        q = EventQueue()
        for _ in range(5):
            q.enqueue(_make_event())
        removed = q.clear()
        assert removed == 5
        assert q.is_empty

    def test_clear_returns_count(self) -> None:
        q = EventQueue()
        q.enqueue(_make_event())
        q.enqueue(_make_event())
        count = q.clear()
        assert count == 2

    def test_clear_empty_returns_zero(self) -> None:
        q = EventQueue()
        assert q.clear() == 0


class TestEventQueueMaxSize:
    def test_max_size_drops_oldest(self) -> None:
        q = EventQueue(max_size=2)
        e1 = _make_event(EventType.CREATED, Path("a.txt"))
        e2 = _make_event(EventType.MODIFIED, Path("b.txt"))
        e3 = _make_event(EventType.DELETED, Path("c.txt"))
        q.enqueue(e1)
        q.enqueue(e2)
        q.enqueue(e3)  # drops e1
        assert q.size == 2
        batch = q.dequeue_batch()
        paths = [str(e.path) for e in batch]
        assert "c.txt" in paths

    def test_zero_max_size_unlimited(self) -> None:
        q = EventQueue(max_size=0)
        for i in range(100):
            q.enqueue(_make_event(EventType.CREATED, Path(f"f{i}.txt")))
        assert q.size == 100


class TestEventQueueBlocking:
    def test_dequeue_blocking_returns_immediately_if_events_present(self) -> None:
        q = EventQueue()
        q.enqueue(_make_event())
        batch = q.dequeue_batch_blocking(max_size=1, timeout=0.0)
        assert len(batch) == 1

    def test_dequeue_blocking_timeout_returns_empty(self) -> None:
        q = EventQueue()
        batch = q.dequeue_batch_blocking(max_size=1, timeout=0.01)
        assert batch == []
