"""Watcher symlink/containment hardening (WP-2.3, #1228 / fo-core#322).

``FileEventHandler`` refuses events whose path is a symlink or resolves outside
the configured watch roots, failing closed on resolution errors (symlink loops).
This prevents a symlink planted in (or a move targeting outside) the watched
tree from driving a downstream read/organize of out-of-root content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from watchdog.events import FileCreatedEvent, FileMovedEvent

from file_organizer.watcher.config import WatcherConfig
from file_organizer.watcher.handler import FileEventHandler
from file_organizer.watcher.queue import EventQueue

pytestmark = [pytest.mark.unit, pytest.mark.ci]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink hardening is POSIX-focused"
)


def _handler(root: Path) -> tuple[FileEventHandler, EventQueue]:
    config = WatcherConfig(
        watch_directories=[root],
        debounce_seconds=0.0,
        exclude_patterns=[],
    )
    queue = EventQueue()
    return FileEventHandler(config, queue), queue


def test_in_root_file_is_processed(tmp_path: Path) -> None:
    root = tmp_path / "watched"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 1


def test_no_watch_roots_does_not_block(tmp_path: Path) -> None:
    """With no configured roots there is no boundary to enforce; events pass."""
    target = tmp_path / "doc.txt"
    target.write_text("content")
    config = WatcherConfig(watch_directories=[], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 1


def test_path_outside_root_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "watched"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "doc.txt"
    target.write_text("content")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 0


@posix_only
def test_symlinked_event_path_is_skipped(tmp_path: Path) -> None:
    """A symlink planted in the watched tree is refused (lstat S_ISLNK)."""
    root = tmp_path / "watched"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("attacker secret")
    link = root / "link.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlink creation not supported")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(link)))

    assert queue.size == 0


@posix_only
def test_symlinked_ancestor_escape_is_skipped(tmp_path: Path) -> None:
    """A real file reached via a symlinked ancestor that escapes the root is
    refused by the resolve-based containment check."""
    root = tmp_path / "watched"
    root.mkdir()
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "sub" / "doc.txt").write_text("attacker secret")
    try:
        (root / "sub").symlink_to(outside / "sub")
    except OSError:
        pytest.skip("symlink creation not supported")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(root / "sub" / "doc.txt")))

    assert queue.size == 0


@posix_only
def test_symlink_loop_fails_closed(tmp_path: Path) -> None:
    """A symlink loop makes resolution raise; the event is refused (fail-closed)."""
    root = tmp_path / "watched"
    root.mkdir()
    a = root / "a"
    b = root / "b"
    try:
        a.symlink_to(b)
        b.symlink_to(a)
    except OSError:
        pytest.skip("symlink creation not supported")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(a / "doc.txt")))

    assert queue.size == 0


def test_move_with_out_of_root_dest_is_skipped(tmp_path: Path) -> None:
    """A move whose destination escapes the watched root is refused — the dest
    is the path that would be organized."""
    root = tmp_path / "watched"
    root.mkdir()
    src = root / "doc.txt"
    src.write_text("content")
    outside = tmp_path / "outside"
    outside.mkdir()
    dest = outside / "doc.txt"
    handler, queue = _handler(root)

    handler.on_moved(FileMovedEvent(src_path=str(src), dest_path=str(dest)))

    assert queue.size == 0


def test_resolution_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If canonicalizing the event path raises (e.g. an OS-level resolution
    failure), the event is refused rather than processed — fail-closed."""
    root = tmp_path / "watched"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content")
    handler, queue = _handler(root)

    real_resolve = Path.resolve

    def _raise_for_target(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "doc.txt":
            raise OSError("simulated resolution failure")
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", _raise_for_target)

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 0


def test_move_within_root_is_processed(tmp_path: Path) -> None:
    root = tmp_path / "watched"
    root.mkdir()
    src = root / "a.txt"
    src.write_text("content")
    dest = root / "b.txt"
    dest.write_text("content")
    handler, queue = _handler(root)

    handler.on_moved(FileMovedEvent(src_path=str(src), dest_path=str(dest)))

    assert queue.size == 1
