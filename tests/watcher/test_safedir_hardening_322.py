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
from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from file_organizer.watcher.config import WatcherConfig
from file_organizer.watcher.handler import FileEventHandler
from file_organizer.watcher.monitor import FileMonitor
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
def test_symlinked_ancestor_within_root_is_skipped(tmp_path: Path) -> None:
    """A symlinked ancestor whose target is *also under* the root passes the
    resolved-containment check, but the per-component symlink walk still refuses
    it — the enqueued symlink-bearing path would otherwise be a TOCTOU foothold
    (Codex review, fo-core#322)."""
    root = tmp_path / "watched"
    root.mkdir()
    real = root / "real"
    real.mkdir()
    (real / "doc.txt").write_text("content")
    try:
        (root / "link").symlink_to(real)  # symlinked ancestor, target under root
    except OSError:
        pytest.skip("symlink creation not supported")
    handler, queue = _handler(root)

    handler.on_created(FileCreatedEvent(src_path=str(root / "link" / "doc.txt")))

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


def test_lstat_error_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If ``lstat`` on a component raises a non-FileNotFound OS error (e.g. a
    permission error) during the per-component symlink walk, the event is
    refused rather than processed — fail-closed."""
    import file_organizer.watcher.handler as handler_mod

    root = tmp_path / "watched"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content")
    handler, queue = _handler(root)

    real_lstat = handler_mod.os.lstat

    def _raise_for_target(p: object, *args: object, **kwargs: object) -> object:
        if str(p).endswith("doc.txt"):
            raise PermissionError("simulated lstat failure")
        return real_lstat(p, *args, **kwargs)  # type: ignore[arg-type]

    # Only the handler's per-component walk uses this os.lstat; Path.resolve
    # uses pathlib's own os reference, so canonicalization is unaffected.
    monkeypatch.setattr(handler_mod.os, "lstat", _raise_for_target)

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

    events = queue.dequeue_batch(max_size=1)
    assert len(events) == 1
    # A MOVED event is represented downstream by its destination (the live,
    # to-be-organized file), not the now-vacated source.
    assert events[0].path == dest
    assert events[0].dest_path == dest


@posix_only
def test_symlinked_watch_root_still_processes(tmp_path: Path) -> None:
    """A deliberately symlinked *watch root* is trusted: events under it still
    flow (the per-component walk anchors on the configured root form and never
    lstat-checks the root itself)."""
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "doc.txt").write_text("content")
    link_root = tmp_path / "link"
    try:
        link_root.symlink_to(real_root)
    except OSError:
        pytest.skip("symlink creation not supported")
    config = WatcherConfig(watch_directories=[link_root], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    handler.on_created(FileCreatedEvent(src_path=str(link_root / "doc.txt")))

    assert queue.size == 1


@posix_only
def test_symlinked_ancestor_under_symlinked_root_is_skipped(tmp_path: Path) -> None:
    """Even under a symlinked watch root, a symlinked *ancestor below* the root
    is refused — the non-canonical root prefix must not bypass the walk."""
    real_root = tmp_path / "real"
    real_root.mkdir()
    inner = real_root / "inner"
    inner.mkdir()
    (inner / "doc.txt").write_text("content")
    # Symlinked ancestor below the root, target still under the root.
    try:
        (real_root / "link").symlink_to(inner)
    except OSError:
        pytest.skip("symlink creation not supported")
    link_root = tmp_path / "link_root"
    try:
        link_root.symlink_to(real_root)
    except OSError:
        pytest.skip("symlink creation not supported")
    config = WatcherConfig(watch_directories=[link_root], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    handler.on_created(FileCreatedEvent(src_path=str(link_root / "link" / "doc.txt")))

    assert queue.size == 0


@posix_only
def test_resolved_prefix_event_under_symlinked_root_processes(tmp_path: Path) -> None:
    """When the watch root is configured as a symlink but the event arrives with
    the *resolved* prefix (as watchdog emits), the walk falls through to the
    resolved-root alignment and still processes the event."""
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "doc.txt").write_text("content")
    link_root = tmp_path / "link"
    try:
        link_root.symlink_to(real_root)
    except OSError:
        pytest.skip("symlink creation not supported")
    config = WatcherConfig(watch_directories=[link_root], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    # Event path uses the resolved prefix, not the configured (link) prefix.
    handler.on_created(FileCreatedEvent(src_path=str(real_root / "doc.txt")))

    assert queue.size == 1


@posix_only
def test_event_via_unconfigured_symlink_fails_closed(tmp_path: Path) -> None:
    """An event whose path reaches the root through a symlink that is *not* the
    configured watch root aligns to neither root form and is refused — only the
    configured root's prefix is trusted."""
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "doc.txt").write_text("content")
    link_root = tmp_path / "link"
    other_link = tmp_path / "other"
    try:
        link_root.symlink_to(real_root)
        other_link.symlink_to(real_root)
    except OSError:
        pytest.skip("symlink creation not supported")
    config = WatcherConfig(watch_directories=[link_root], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    # Resolves under the root, but via an unconfigured symlink prefix.
    handler.on_created(FileCreatedEvent(src_path=str(other_link / "doc.txt")))

    assert queue.size == 0


def test_excluded_file_is_filtered_before_guard(tmp_path: Path) -> None:
    """A file matching an exclude pattern is dropped by the filter before the
    containment guard runs."""
    root = tmp_path / "watched"
    root.mkdir()
    config = WatcherConfig(
        watch_directories=[root], debounce_seconds=0.0, exclude_patterns=["*.tmp"]
    )
    queue = EventQueue()
    handler = FileEventHandler(config, queue)
    target = root / "scratch.tmp"
    target.write_text("content")

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 0


def test_debounced_event_is_dropped(tmp_path: Path) -> None:
    """A second event on the same path within the debounce window is dropped."""
    root = tmp_path / "watched"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content")
    config = WatcherConfig(watch_directories=[root], debounce_seconds=60.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    handler.on_created(FileCreatedEvent(src_path=str(target)))
    handler.on_modified(FileModifiedEvent(src_path=str(target)))

    # First event enqueued; second collapsed by the debounce window.
    assert queue.size == 1


def test_missing_component_ends_walk(tmp_path: Path) -> None:
    """A DELETED/move-away event whose path no longer exists ends the
    per-component walk at the missing component and is allowed through (it
    resolved under the root; there is nothing left on disk to follow)."""
    root = tmp_path / "watched"
    root.mkdir()
    handler, queue = _handler(root)

    # No such file on disk — e.g. a DELETED event arriving after removal.
    handler.on_deleted(FileDeletedEvent(src_path=str(root / "gone.txt")))

    assert queue.size == 1


def test_missing_intermediate_component_fails_closed(tmp_path: Path) -> None:
    """A missing *intermediate* component (e.g. a symlinked ancestor removed
    between resolve() and the lstat) fails closed — only a missing final
    component is treated as a benign delete."""
    root = tmp_path / "watched"
    root.mkdir()
    handler, queue = _handler(root)

    # 'sub' does not exist, so the walk hits FileNotFoundError on a non-final
    # component → refused.
    handler.on_created(FileCreatedEvent(src_path=str(root / "sub" / "doc.txt")))

    assert queue.size == 0


def test_missing_leaf_for_live_event_fails_closed(tmp_path: Path) -> None:
    """A live CREATED/MODIFIED event whose leaf vanished between resolve() and
    lstat fails closed — only DELETED events tolerate a missing leaf, since a
    live name could be recreated as an out-of-root symlink before the watch loop
    opens it."""
    root = tmp_path / "watched"
    root.mkdir()
    handler, queue = _handler(root)

    # doc.txt does not exist on disk, but this is a live CREATED event.
    handler.on_created(FileCreatedEvent(src_path=str(root / "doc.txt")))

    assert queue.size == 0


def test_all_roots_unresolvable_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If watch directories are configured but none resolve (e.g. a root turned
    into a symlink loop), the guard fails closed rather than degrading to the
    no-boundary 'allow everything' mode."""
    root = tmp_path / "watched"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content")
    config = WatcherConfig(watch_directories=[root], debounce_seconds=0.0, exclude_patterns=[])
    queue = EventQueue()
    handler = FileEventHandler(config, queue)

    real_resolve = Path.resolve

    def _raise_for_root(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "watched":
            raise OSError("simulated unresolvable root (symlink loop)")
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", _raise_for_root)

    handler.on_created(FileCreatedEvent(src_path=str(target)))

    assert queue.size == 0


class TestAddDirectoryConfigSync:
    """``FileMonitor.add_directory`` keeps ``config.watch_directories`` in sync so
    the handler's containment guard sees dynamically-added roots (WP-2.3)."""

    def test_add_before_start_syncs_config(self, tmp_path: Path) -> None:
        watched = tmp_path / "watched"
        watched.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        config = WatcherConfig(
            watch_directories=[watched], debounce_seconds=0.0, exclude_patterns=[]
        )
        mon = FileMonitor(config)

        mon.add_directory(extra)

        assert extra.resolve() in config.watch_directories

    def test_add_already_in_config_is_noop(self, tmp_path: Path) -> None:
        watched = tmp_path / "watched"
        watched.mkdir()
        config = WatcherConfig(
            watch_directories=[watched.resolve()], debounce_seconds=0.0, exclude_patterns=[]
        )
        mon = FileMonitor(config)
        before = list(config.watch_directories)

        mon.add_directory(watched)  # resolves to an entry already present

        assert config.watch_directories == before

    def test_add_while_running_syncs_config(self, tmp_path: Path) -> None:
        watched = tmp_path / "watched"
        watched.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        config = WatcherConfig(
            watch_directories=[watched], debounce_seconds=0.0, exclude_patterns=[]
        )
        mon = FileMonitor(config)
        mon.start()
        try:
            mon.add_directory(extra)
            assert extra.resolve() in config.watch_directories
        finally:
            mon.stop()

    def test_add_nonexistent_while_running_rolls_back(self, tmp_path: Path) -> None:
        watched = tmp_path / "watched"
        watched.mkdir()
        config = WatcherConfig(
            watch_directories=[watched], debounce_seconds=0.0, exclude_patterns=[]
        )
        mon = FileMonitor(config)
        mon.start()
        try:
            missing = tmp_path / "nope"
            with pytest.raises(FileNotFoundError):
                mon.add_directory(missing)
            # Scheduling failed → the config append is rolled back.
            assert missing.resolve() not in config.watch_directories
        finally:
            mon.stop()
