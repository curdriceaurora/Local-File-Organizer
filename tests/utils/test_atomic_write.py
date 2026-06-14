"""Tests for ``utils.atomic_write`` — crash-safe state-file writers (B1a/B1b).

Epic B.atomic of the hardening roadmap: every persistent state file this
project writes (config YAML, suggestion feedback, rule manager, JD system,
PARA migration manifest, embedder pickle cache, event discovery state,
…) currently uses ``path.write_text(...)`` or ``with open(path, "w"/"wb")``.
That pattern truncates the file *before* the new content lands — a crash
or concurrent writer in the window between truncation and close leaves
the file half-written or empty, and the downstream tool reads garbage.

The fix landed in this module is the temp-file-plus-``os.replace()``
pattern, exposed via four helpers:

- ``atomic_write_text``  — for the 15 YAML / JSON state files.
- ``atomic_write_bytes`` — in-memory payload.
- ``atomic_write_with``  — streaming callback (e.g. ``pickle.dump(obj, f)``).
- ``append_durable``     — single-line fsynced append for audit / VS Code logs.

All three share the same implementation; only the surface API differs.
Temp file is created in the destination's *parent directory* so the
``os.replace`` is same-filesystem atomic on POSIX and Windows.

These tests cover:

- Happy path (content lands, temp file cleaned up).
- Crash injection — writer raises mid-stream, destination unchanged,
  no temp file lingers.
- Idempotency — repeated writes leave one canonical file.
- Pre-existing target is overwritten atomically (pre-existing reader
  of old content during write never sees a truncated file).
- Concurrent writers — last writer wins, no partial state.
- Parent-directory creation — helper does NOT auto-create missing
  parents (surfaces the bug instead of silently swallowing).
- Append durability — ``append_durable`` preserves prior content,
  appends one newline-terminated record, and fsyncs.

``utils.atomic_io.fsync_directory`` (already in the tree from a prior
PR) is reused to persist the directory entry on POSIX.
"""

from __future__ import annotations

import io
import os
import pickle
import sys
import threading
from pathlib import Path

import pytest

from file_organizer.utils.atomic_write import (
    append_durable,
    atomic_write_bytes,
    atomic_write_text,
    atomic_write_with,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


# ---------------------------------------------------------------------------
# atomic_write_text
# ---------------------------------------------------------------------------


class TestAtomicWriteText:
    """The YAML/JSON state-file path (15 B1a sites)."""

    def test_writes_content_utf8_by_default(self, tmp_path: Path) -> None:
        target = tmp_path / "config.yaml"
        atomic_write_text(target, "key: valué\n")
        assert target.read_text(encoding="utf-8") == "key: valué\n"

    def test_respects_encoding_kwarg(self, tmp_path: Path) -> None:
        target = tmp_path / "latin.txt"
        atomic_write_text(target, "café", encoding="latin-1")
        assert target.read_bytes() == "café".encode("latin-1")

    def test_overwrites_pre_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "state.yaml"
        target.write_text("old contents", encoding="utf-8")
        atomic_write_text(target, "new contents")
        assert target.read_text(encoding="utf-8") == "new contents"

    def test_no_temp_files_remain_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "s.yaml"
        atomic_write_text(target, "payload")
        # Only the target itself should exist in the directory; no
        # lingering ``*.tmp`` artifacts from the helper.
        entries = list(tmp_path.iterdir())
        assert entries == [target]

    def test_rejects_missing_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nonexistent" / "s.yaml"
        # Helper must NOT silently ``mkdir -p`` — callers that need the
        # directory auto-created have always done it themselves.
        # Surface the bug so missing-parent issues get caught early.
        with pytest.raises((FileNotFoundError, OSError)):
            atomic_write_text(target, "payload")


# ---------------------------------------------------------------------------
# atomic_write_bytes
# ---------------------------------------------------------------------------


class TestAtomicWriteBytes:
    """In-memory binary payload path (no streaming writer needed)."""

    def test_writes_payload(self, tmp_path: Path) -> None:
        target = tmp_path / "blob.bin"
        atomic_write_bytes(target, b"\x00\xff\x01\xfe")
        assert target.read_bytes() == b"\x00\xff\x01\xfe"

    def test_overwrites_pre_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "blob.bin"
        target.write_bytes(b"old")
        atomic_write_bytes(target, b"new")
        assert target.read_bytes() == b"new"

    def test_empty_payload_produces_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.bin"
        atomic_write_bytes(target, b"")
        assert target.read_bytes() == b""


# ---------------------------------------------------------------------------
# atomic_write_with
# ---------------------------------------------------------------------------


class TestAtomicWriteWith:
    """Callback / streaming writer path.

    Mirrors the real usage site in ``src/services/deduplication/embedder.py``
    where ``pickle.dump(obj, f)`` streams directly into the handle without
    buffering the full pickle into RAM.
    """

    def test_writer_receives_binary_handle_by_default(self, tmp_path: Path) -> None:
        target = tmp_path / "cache.pkl"
        payload = {"embedding": [1.0, 2.0, 3.0], "model": "sentence-bert"}

        def _writer(fh: io.BufferedWriter) -> None:
            pickle.dump(payload, fh)

        atomic_write_with(target, _writer)
        with target.open("rb") as fh:
            assert pickle.load(fh) == payload

    def test_text_mode_opens_text_handle(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"

        def _writer(fh: io.TextIOBase) -> None:
            fh.write("line 1\n")
            fh.write("line 2\n")

        atomic_write_with(target, _writer, mode="w")
        assert target.read_text() == "line 1\nline 2\n"

    def test_writer_exception_leaves_target_untouched(self, tmp_path: Path) -> None:
        target = tmp_path / "cache.pkl"
        target.write_bytes(b"ORIGINAL")

        def _broken_writer(_fh: io.BufferedWriter) -> None:
            raise RuntimeError("pickle failed halfway")

        with pytest.raises(RuntimeError, match="pickle failed halfway"):
            atomic_write_with(target, _broken_writer)

        # Crash-safety invariant: destination unchanged, NO temp file
        # left behind for operators to puzzle over.
        assert target.read_bytes() == b"ORIGINAL"
        assert list(tmp_path.iterdir()) == [target]

    def test_invalid_mode_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "x.bin"

        def _writer(_fh: io.BufferedWriter) -> None:
            pass  # pragma: no cover — should not be called

        with pytest.raises(ValueError):
            atomic_write_with(target, _writer, mode="r")  # type: ignore[arg-type]

    def test_text_mode_defaults_to_utf8(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """codex P1 (PRRT_kwDOR_Rkws59ML8K): ``atomic_write_with(mode="w")``
        must default to UTF-8, not the process locale. On non-UTF-8
        locales (common on Windows), a locale-default open would emit
        bytes that later fail to decode as UTF-8. Simulate a non-UTF-8
        locale by forcing ``locale.getpreferredencoding`` and confirm
        the written bytes are valid UTF-8 regardless.
        """
        import locale as _locale

        monkeypatch.setattr(_locale, "getpreferredencoding", lambda _do_setlocale=True: "cp1252")

        target = tmp_path / "unicode.json"

        def _writer(fh: io.TextIOBase) -> None:
            fh.write('{"key": "café ñ 你好"}')

        atomic_write_with(target, _writer, mode="w")
        # Round-trip through UTF-8 — must not raise and must match.
        assert target.read_text(encoding="utf-8") == '{"key": "café ñ 你好"}'

    def test_text_mode_respects_explicit_encoding(self, tmp_path: Path) -> None:
        """Caller-supplied ``encoding`` overrides the UTF-8 default."""
        target = tmp_path / "latin.txt"

        def _writer(fh: io.TextIOBase) -> None:
            fh.write("café")

        atomic_write_with(target, _writer, mode="w", encoding="latin-1")
        assert target.read_bytes() == "café".encode("latin-1")

    def test_binary_mode_rejects_encoding(self, tmp_path: Path) -> None:
        """Passing ``encoding`` with binary mode is a caller bug —
        surface it as ``ValueError`` rather than silently ignoring.
        """
        target = tmp_path / "x.bin"

        def _writer(_fh: io.BufferedWriter) -> None:
            pass  # pragma: no cover — should not be called

        with pytest.raises(ValueError, match="invalid for binary mode"):
            atomic_write_with(target, _writer, mode="wb", encoding="utf-8")


# ---------------------------------------------------------------------------
# append_durable
# ---------------------------------------------------------------------------


class TestAppendDurable:
    """The audit/VS Code JSONL log path (2 B1b sites)."""

    def test_appends_single_line_and_terminates_with_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "audit.jsonl"
        append_durable(target, '{"event":"ORGANIZE"}')
        assert target.read_text(encoding="utf-8") == '{"event":"ORGANIZE"}\n'

    def test_appends_do_not_truncate_prior_content(self, tmp_path: Path) -> None:
        target = tmp_path / "audit.jsonl"
        target.write_text('{"event":"OLD"}\n', encoding="utf-8")
        append_durable(target, '{"event":"NEW"}')
        assert target.read_text(encoding="utf-8") == '{"event":"OLD"}\n{"event":"NEW"}\n'

    def test_line_already_newline_terminated_is_not_double_terminated(self, tmp_path: Path) -> None:
        target = tmp_path / "audit.jsonl"
        append_durable(target, '{"event":"A"}\n')
        assert target.read_text(encoding="utf-8") == '{"event":"A"}\n'

    def test_creates_file_if_absent(self, tmp_path: Path) -> None:
        target = tmp_path / "fresh.jsonl"
        append_durable(target, "hello")
        assert target.read_text() == "hello\n"

    def test_rejects_missing_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nonexistent" / "audit.jsonl"
        with pytest.raises((FileNotFoundError, OSError)):
            append_durable(target, "line")


# ---------------------------------------------------------------------------
# Shared cross-cutting invariants
# ---------------------------------------------------------------------------


class TestAtomicityInvariants:
    """Cross-cutting guarantees the entire module must uphold."""

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="os.replace raises WinError 5 when destination is open by another thread; "
        "POSIX rename(2) atomicity guarantee does not apply on Windows",
    )
    def test_concurrent_writers_leave_one_canonical_file(self, tmp_path: Path) -> None:
        """Two threads racing ``atomic_write_text`` must produce one file.

        Last-writer-wins is acceptable; half-written / truncated is not.
        Verifies the ``os.replace`` final step is actually used (rather
        than a naive truncate-then-write loop).
        """
        target = tmp_path / "race.yaml"
        payloads = [f"writer-{i}:{'x' * 1024}" for i in range(20)]

        def _writer(payload: str) -> None:
            atomic_write_text(target, payload)

        threads = [threading.Thread(target=_writer, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # The final content must match exactly one of the payloads —
        # no interleaving, no truncation.
        final = target.read_text()
        assert final in payloads
        # And no racing-writer ``*.tmp`` artifact survives the storm
        # (coderabbit PRRT_kwDOR_Rkws59MONu).
        assert list(tmp_path.iterdir()) == [target]

    def test_temp_file_removed_when_replace_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ``os.replace`` fails (e.g. cross-device EXDEV), the temp file
        must be cleaned up — otherwise repeated failures accumulate garbage
        next to the target, which operators then confuse for real state.
        """
        target = tmp_path / "s.yaml"

        def _broken_replace(_src: object, _dst: object) -> None:
            raise OSError("simulated cross-device replace failure")

        monkeypatch.setattr(os, "replace", _broken_replace)

        with pytest.raises(OSError, match="simulated cross-device"):
            atomic_write_text(target, "payload")

        # Nothing left behind — no target, no temp file.
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlink semantics on Windows require elevated privileges",
    )
    def test_follows_symlinks_instead_of_replacing_link(self, tmp_path: Path) -> None:
        """codex P2 (PRRT_kwDOR_Rkws59MXyc): the pre-existing
        ``path.write_text`` / ``open(path, "w")`` sites followed
        symlinks — users who symlink config/state files to shared
        storage expect a save to write through to the real target, not
        replace the symlink with a regular file. Regression guard:
        when the target is a symlink, the write must update the
        symlink's target, and the symlink itself must remain a
        symlink pointing at the same real path.
        """
        real_target = tmp_path / "real_config.yaml"
        real_target.write_text("original")
        link = tmp_path / "link.yaml"
        link.symlink_to(real_target)

        atomic_write_text(link, "updated")

        # Link still exists and still points to the same real target.
        assert link.is_symlink()
        assert link.resolve() == real_target.resolve()
        # The real file (not the link) now has the new content.
        assert real_target.read_text() == "updated"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX file-mode bits not meaningful on Windows",
    )
    def test_preserves_existing_target_permissions(self, tmp_path: Path) -> None:
        """coderabbit Minor (PRRT_kwDOR_Rkws59MONs): ``tempfile.NamedTemporaryFile``
        creates the temp file with 0o600, and ``os.replace`` inherits
        the temp inode's mode. Without explicit preservation, a user
        who chmodded their config file to 0o644 would silently lose
        that on every save. Pre-existing target mode must survive the
        atomic replace.
        """
        target = tmp_path / "config.yaml"
        target.write_text("initial")
        # User customised to group-readable.
        target.chmod(0o640)

        atomic_write_text(target, "updated")
        new_mode = target.stat().st_mode & 0o7777
        assert new_mode == 0o640, f"mode drifted: expected 0o640, got {oct(new_mode)}"

    def test_chmod_oserror_ignored(self, tmp_path: Path) -> None:
        """chmod failures are silently ignored — write still succeeds."""
        from unittest.mock import patch

        target = tmp_path / "existing.txt"
        target.write_text("original")
        with patch("os.chmod", side_effect=OSError("chmod denied")):
            atomic_write_text(target, "new content")
        assert target.read_text() == "new content"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX file-mode bits not meaningful on Windows",
    )
    def test_new_target_gets_default_safe_mode(self, tmp_path: Path) -> None:
        """First-time writes have no pre-existing mode to inherit, so
        they retain the tempfile default of 0o600 — safer than the
        locale-default umask-derived mode and acceptable for the state
        files this module is used for.
        """
        target = tmp_path / "new.yaml"
        atomic_write_text(target, "first write")
        new_mode = target.stat().st_mode & 0o7777
        assert new_mode == 0o600

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Directory fsync is POSIX-only; atomic_io.fsync_directory is a no-op on Windows",
    )
    def test_directory_fsync_invoked_on_posix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies the helper delegates durability to
        ``atomic_io.fsync_directory`` rather than silently skipping it —
        the whole point of the B1a work is that the new state survives
        a mid-write crash, which requires a directory fsync on POSIX.
        """
        from file_organizer.utils import atomic_write as aw

        called: list[Path] = []

        def _fake_fsync_directory(path: Path) -> None:
            called.append(path)

        monkeypatch.setattr(aw, "fsync_directory", _fake_fsync_directory)

        target = tmp_path / "s.yaml"
        atomic_write_text(target, "payload")
        # ``atomic_io.fsync_directory`` is called with the target path
        # (it internally opens ``target.parent`` for the fsync).
        assert called == [target]
