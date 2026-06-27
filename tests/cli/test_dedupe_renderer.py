"""Tests for ``cli.dedupe_renderer``: Renderer protocol + 3 implementations.

Issue #157 / Epic D / D4 Renderer extraction.

Test contract:
- ``make_renderer("invalid")`` raises ``ValueError`` listing accepted formats.
- ``RichRenderer`` writes through a Rich Console (we capture via ``StringIO``).
- ``JsonRenderer`` produces a single JSON envelope at ``end()``, with the
  ``version: 1`` schema (NOT ``schema``: ``$schema`` is conventionally a
  URI, so reusing it for an integer indicator misleads). The envelope
  always includes ``groups`` / ``actions`` / ``summary`` keys (possibly
  empty) so consumers can rely on a stable shape.
- ``PlainRenderer`` produces line-oriented output suitable for piping to ``awk``.
- All three handle every method on the protocol; no method silently no-ops in
  ways that hide a bug (begin/end pairing matters for JsonRenderer).
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from file_organizer.cli.dedupe_renderer import (
    JsonRenderer,
    PlainRenderer,
    Renderer,
    RichRenderer,
    make_renderer,
)
from file_organizer.services.deduplication.index import DuplicateGroup, FileMetadata

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(path: Path, size: int = 1024) -> FileMetadata:
    return FileMetadata(
        path=path,
        size=size,
        modified_time=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        accessed_time=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        hash_value="abc123",
    )


def _make_groups(tmp_path: Path) -> dict[str, DuplicateGroup]:
    a = _make_file(tmp_path / "a.txt", size=2048)
    b = _make_file(tmp_path / "b.txt", size=2048)
    c = _make_file(tmp_path / "c.txt", size=4096)
    d = _make_file(tmp_path / "d.txt", size=4096)
    return {
        "abc123": DuplicateGroup(hash_value="abc123", files=[a, b]),
        "def456": DuplicateGroup(hash_value="def456", files=[c, d]),
    }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestMakeRenderer:
    def test_rich(self) -> None:
        r = make_renderer("rich")
        assert isinstance(r, RichRenderer)

    def test_json(self) -> None:
        r = make_renderer("json")
        assert isinstance(r, JsonRenderer)

    def test_plain(self) -> None:
        r = make_renderer("plain")
        assert isinstance(r, PlainRenderer)

    def test_case_insensitive(self) -> None:
        # Typer is configured with case_sensitive=False, but the factory
        # normalizes too so it's safe to call directly.
        assert isinstance(make_renderer("RICH"), RichRenderer)
        assert isinstance(make_renderer("Json"), JsonRenderer)

    def test_invalid_format_raises_value_error_listing_accepted(self) -> None:
        with pytest.raises(ValueError, match="rich.*json.*plain") as exc_info:
            make_renderer("xml")
        # Mention the offending value too (helps the user fix their flag)
        assert "xml" in str(exc_info.value)

    def test_protocol_compliance(self) -> None:
        """Each concrete class implements the full Renderer protocol surface."""
        r_rich: Renderer = RichRenderer()
        r_json: Renderer = JsonRenderer()
        r_plain: Renderer = PlainRenderer()
        # Every required method is callable on every renderer.
        for r in (r_rich, r_json, r_plain):
            for method in (
                "begin",
                "end",
                "status",
                "render_groups_header",
                "render_groups",
                "render_resolve_action",
                "render_resolve_summary",
                "render_report",
                "render_message",
            ):
                assert callable(getattr(r, method)), f"{type(r).__name__}.{method} not callable"


# ---------------------------------------------------------------------------
# RichRenderer — captures via StringIO console
# ---------------------------------------------------------------------------


class TestRichRenderer:
    """RichRenderer writes through a Rich Console; we capture via a StringIO file."""

    def _renderer(self) -> tuple[RichRenderer, io.StringIO]:
        buf = io.StringIO()
        # RichRenderer accepts an optional console; we inject one writing to buf
        # with force_terminal=False so ANSI escapes are stripped, and
        # soft_wrap=True so long paths don't get split across lines (which
        # would break ``in`` substring assertions on file paths under
        # pytest's tmp_path, which can exceed 120 chars).
        from rich.console import Console

        console = Console(
            file=buf,
            force_terminal=False,
            width=200,
            no_color=True,
            soft_wrap=True,
        )
        return RichRenderer(console=console), buf

    def test_groups_header(self) -> None:
        r, buf = self._renderer()
        r.render_groups_header(3)
        assert "Found 3" in buf.getvalue()
        assert "duplicate groups" in buf.getvalue()

    def test_groups_renders_table(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        groups = _make_groups(tmp_path)
        r.render_groups(groups)
        out = buf.getvalue()
        # Each group's hash prefix appears in a header
        assert "abc123" in out
        assert "def456" in out
        # File paths appear in the rendered tables
        assert "a.txt" in out
        assert "b.txt" in out
        # Sizes appear (2.0 KB for the 2048-byte files)
        assert "KB" in out

    def test_resolve_action_removed(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.render_resolve_action("removed", tmp_path / "x.txt")
        out = buf.getvalue()
        assert "Removed" in out
        assert "x.txt" in out

    def test_resolve_action_would_remove_dry_run(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.render_resolve_action("would_remove", tmp_path / "x.txt")
        out = buf.getvalue()
        assert "Would remove" in out
        assert "x.txt" in out

    def test_resolve_action_error_includes_message(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.render_resolve_action("error", tmp_path / "x.txt", error="Permission denied")
        out = buf.getvalue()
        assert "Error" in out
        assert "x.txt" in out
        assert "Permission denied" in out

    def test_resolve_summary_dry_run(self) -> None:
        r, buf = self._renderer()
        r.render_resolve_summary(removed_count=5, dry_run=True)
        out = buf.getvalue()
        assert "Dry run" in out
        # Dry-run summary should NOT claim a removal count
        assert "Removed 5" not in out

    def test_resolve_summary_actual(self) -> None:
        r, buf = self._renderer()
        r.render_resolve_summary(removed_count=3, dry_run=False)
        out = buf.getvalue()
        assert "Removed 3" in out
        assert "Dry run" not in out

    def test_report_renders_table_with_metrics(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        groups = _make_groups(tmp_path)
        stats = {"total_files": 100, "duplicate_files": 4}
        r.render_report(stats=stats, groups=groups, total_wasted=6144)
        out = buf.getvalue()
        assert "Duplicate Report" in out
        assert "100" in out  # total_files
        assert "4" in out  # duplicate_files
        assert "2" in out  # 2 groups
        assert "KB" in out  # wasted space format

    def test_message_levels_are_distinguishable(self) -> None:
        r, buf = self._renderer()
        r.render_message("info", "info-marker")
        r.render_message("success", "success-marker")
        r.render_message("warning", "warning-marker")
        r.render_message("error", "error-marker")
        out = buf.getvalue()
        for marker in ("info-marker", "success-marker", "warning-marker", "error-marker"):
            assert marker in out, f"missing message text: {marker}"

    def test_status_is_context_manager(self) -> None:
        r, _ = self._renderer()
        # Must be usable as ``with renderer.status("..."):`` — Rich's
        # console.status() returns a Status object that is itself a context
        # manager; if our wrapper doesn't preserve that, this `with` raises.
        with r.status("Scanning…"):
            pass


# ---------------------------------------------------------------------------
# JsonRenderer — buffers and flushes a single envelope
# ---------------------------------------------------------------------------


class TestJsonRenderer:
    def _renderer(self) -> tuple[JsonRenderer, io.StringIO]:
        buf = io.StringIO()
        return JsonRenderer(stream=buf), buf

    def test_envelope_emitted_only_on_end(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.begin("scan")
        r.render_groups_header(1)
        r.render_groups(_make_groups(tmp_path))
        # No JSON written yet
        assert buf.getvalue() == ""
        r.end()
        out = buf.getvalue()
        assert out.strip(), "JsonRenderer.end() must flush the envelope"
        # Single document, parses cleanly
        envelope = json.loads(out)
        assert envelope["version"] == 1
        assert envelope["command"] == "scan"

    def test_envelope_always_includes_v1_schema_keys(self) -> None:
        """Empty run still emits ``groups`` / ``actions`` / ``summary``.

        Consumers piping ``--format json | jq '.summary'`` shouldn't have
        to special-case empty-result runs; the v1 envelope is documented
        as having a stable shape. CodeRabbit flagged the original
        conditional-omission behavior on PR #206.
        """
        r, buf = self._renderer()
        r.begin("scan")
        # No render_* calls — empty run
        r.end()
        envelope = json.loads(buf.getvalue())
        assert envelope == {
            "version": 1,
            "command": "scan",
            "groups": [],
            "actions": [],
            "summary": {},
        }

    def test_envelope_schema_for_scan(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.begin("scan")
        r.render_groups(_make_groups(tmp_path))
        r.end()
        envelope = json.loads(buf.getvalue())
        # Required keys per spec §2.1
        assert envelope["version"] == 1
        assert envelope["command"] == "scan"
        assert "groups" in envelope
        groups = envelope["groups"]
        assert len(groups) == 2
        # Each group has hash, files, size
        for g in groups:
            assert "hash" in g
            assert "files" in g
            assert isinstance(g["files"], list)
            assert "wasted_space" in g

    def test_envelope_schema_for_resolve(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.begin("resolve")
        r.render_resolve_action("removed", tmp_path / "a.txt")
        r.render_resolve_action("would_remove", tmp_path / "b.txt")
        r.render_resolve_action("error", tmp_path / "c.txt", error="EPERM")
        r.render_resolve_summary(removed_count=1, dry_run=False)
        r.end()
        envelope = json.loads(buf.getvalue())
        assert envelope["command"] == "resolve"
        assert "actions" in envelope
        actions = envelope["actions"]
        assert len(actions) == 3
        # Find the error action and check it carries the error message
        errors = [a for a in actions if a["action"] == "error"]
        assert len(errors) == 1
        assert errors[0]["error"] == "EPERM"
        # Summary keys
        assert envelope["summary"] == {"removed_count": 1, "dry_run": False}

    def test_envelope_schema_for_report(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.begin("report")
        groups = _make_groups(tmp_path)
        stats = {"total_files": 200, "duplicate_files": 4}
        r.render_report(stats=stats, groups=groups, total_wasted=6144)
        r.end()
        envelope = json.loads(buf.getvalue())
        assert envelope["command"] == "report"
        assert envelope["summary"]["total_files"] == 200
        assert envelope["summary"]["duplicate_files"] == 4
        assert envelope["summary"]["duplicate_groups"] == 2
        assert envelope["summary"]["total_wasted"] == 6144

    def test_status_is_noop(self) -> None:
        r, buf = self._renderer()
        with r.status("Scanning…"):
            pass
        # Status spinners are visual; JSON renderer must not pollute stdout
        assert buf.getvalue() == ""

    def test_message_routes_warnings_and_errors_to_stderr(self) -> None:
        # Per spec §2.1: "Banner / warnings / errors are NOT included in the
        # JSON body — they go to stderr as plain lines so
        # `dedupe scan --format=json | jq` works."
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        r = JsonRenderer(stream=stdout_buf, stderr=stderr_buf)
        r.begin("scan")
        r.render_message("warning", "watch out")
        r.render_message("error", "something broke")
        r.end()
        # JSON body has no warnings/errors content
        envelope = json.loads(stdout_buf.getvalue())
        assert "watch out" not in stdout_buf.getvalue()
        assert "something broke" not in stdout_buf.getvalue()
        assert envelope["command"] == "scan"
        # Stderr received the messages
        stderr_text = stderr_buf.getvalue()
        assert "watch out" in stderr_text
        assert "something broke" in stderr_text

    def test_end_without_begin_is_noop(self) -> None:
        r, buf = self._renderer()
        r.end()
        # Nothing buffered → nothing emitted
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# PlainRenderer — line-oriented, no colors, no tables
# ---------------------------------------------------------------------------


class TestPlainRenderer:
    def _renderer(self) -> tuple[PlainRenderer, io.StringIO]:
        buf = io.StringIO()
        return PlainRenderer(stream=buf), buf

    def test_groups_header(self) -> None:
        r, buf = self._renderer()
        r.render_groups_header(3)
        assert buf.getvalue().strip() == "Found 3 duplicate groups."

    def test_groups_one_line_per_file(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        groups = _make_groups(tmp_path)
        r.render_groups(groups)
        lines = [ln for ln in buf.getvalue().splitlines() if ln]
        # Each group emits a header line (hash:) then file lines (TAB+path)
        # 2 groups × (1 hash header + 2 file lines) = 6 lines minimum
        assert len(lines) >= 6
        # No Rich table characters
        assert "│" not in buf.getvalue()
        assert "─" not in buf.getvalue()
        # Hash and paths appear
        assert "abc123" in buf.getvalue()
        assert "a.txt" in buf.getvalue()
        assert "b.txt" in buf.getvalue()

    def test_resolve_action_lines(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        r.render_resolve_action("removed", tmp_path / "x.txt")
        r.render_resolve_action("would_remove", tmp_path / "y.txt")
        r.render_resolve_action("error", tmp_path / "z.txt", error="EPERM")
        out = buf.getvalue()
        assert "removed" in out.lower()
        assert "would_remove" in out or "would remove" in out.lower()
        assert "error" in out.lower()
        assert "EPERM" in out

    def test_resolve_summary_key_value(self) -> None:
        r, buf = self._renderer()
        r.render_resolve_summary(removed_count=3, dry_run=False)
        out = buf.getvalue()
        # key:value style for awk piping
        assert "removed_count: 3" in out
        assert "dry_run: false" in out.lower() or "dry_run: False" in out

    def test_report_key_value(self, tmp_path: Path) -> None:
        r, buf = self._renderer()
        groups = _make_groups(tmp_path)
        stats = {"total_files": 100, "duplicate_files": 4}
        r.render_report(stats=stats, groups=groups, total_wasted=6144)
        out = buf.getvalue()
        assert "total_files: 100" in out
        assert "duplicate_files: 4" in out
        assert "duplicate_groups: 2" in out
        assert "total_wasted: 6144" in out

    def test_message_no_color_codes(self) -> None:
        r, buf = self._renderer()
        r.render_message("warning", "be careful")
        r.render_message("error", "oops")
        out = buf.getvalue()
        # No ANSI escape sequences (\x1b[) — content only
        assert "\x1b[" not in out
        assert "be careful" in out
        assert "oops" in out

    def test_status_is_noop(self) -> None:
        r, buf = self._renderer()
        with r.status("Scanning…"):
            pass
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Cross-renderer invariants
# ---------------------------------------------------------------------------


class TestRendererInvariants:
    """Properties that must hold across all three renderers."""

    @pytest.mark.parametrize("fmt", ["rich", "json", "plain"])
    def test_begin_end_can_be_called(self, fmt: str) -> None:
        r = make_renderer(fmt)
        r.begin("scan")
        r.end()  # no exception

    @pytest.mark.parametrize("fmt", ["rich", "json", "plain"])
    def test_render_groups_handles_empty_dict(self, fmt: str) -> None:
        r = make_renderer(fmt)
        r.begin("scan")
        r.render_groups({})  # empty dict is valid input
        r.end()

    @pytest.mark.parametrize(
        "level",
        ["info", "success", "warning", "error"],
    )
    def test_message_levels_supported(self, level: str) -> None:
        # Every renderer accepts every documented level without raising.
        for fmt in ("rich", "json", "plain"):
            r = make_renderer(fmt)
            r.begin("scan")
            r.render_message(level, "test")  # type: ignore[arg-type]
            r.end()

    def test_message_invalid_level_raises(self) -> None:
        r: Any = make_renderer("plain")
        with pytest.raises(ValueError, match="info.*success.*warning.*error"):
            r.render_message("debug", "no debug level")
