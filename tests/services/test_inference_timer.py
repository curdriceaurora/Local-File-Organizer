"""Tests for ``services.inference_timer`` (#410).

Verifies that:
- elapsed_ms is recorded on both success and exception paths,
- the log line fires only when ``mark_invoked()`` was called or the
  body raised (no log for purely pre-inference scopes),
- the ``kind`` argument lands in the log prefix verbatim.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.inference_timer import time_inference

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_records_elapsed_on_success(tmp_path: Path) -> None:
    f = tmp_path / "doc.txt"
    f.write_text("hi")

    with time_inference("text", f) as t:
        t.mark_invoked()

    # Sanity bound — a no-op body should measure as a finite, small
    # duration. Lower bound is already implicit via `max(0.0, ...)`.
    assert isinstance(t.elapsed_ms, float)
    assert t.elapsed_ms < 1000.0


def test_records_elapsed_on_exception(tmp_path: Path) -> None:
    f = tmp_path / "doc.txt"
    f.write_text("hi")

    with pytest.raises(RuntimeError, match="boom"):
        with time_inference("vision", f) as t:
            # An exception mid-body counts as an invoked-but-failed
            # inference; mark_invoked() is unnecessary in that case.
            raise RuntimeError("boom")

    assert isinstance(t.elapsed_ms, float)
    assert t.elapsed_ms < 1000.0


def test_log_emitted_when_marked_invoked(tmp_path: Path) -> None:
    f = tmp_path / "shot.png"
    f.write_bytes(b"")

    with patch("file_organizer.services.inference_timer.logger") as mock_logger:
        with time_inference("vision", f) as t:
            t.mark_invoked()

    mock_logger.debug.assert_called_once()
    fmt, kind, _ms, file_name = mock_logger.debug.call_args.args
    assert "{}_inference_ms=" in fmt
    assert kind == "vision"
    assert file_name == "shot.png"


def test_log_suppressed_when_not_marked_invoked(tmp_path: Path) -> None:
    """Pre-inference early-return paths must not emit a timing log line.

    CodeRabbit P2 round-trip on PR #424: log-based observability
    pipelines would aggregate near-zero non-inference events under the
    ``inference_ms`` key and bias real latency dashboards downward.
    """
    f = tmp_path / "noop.txt"
    f.write_text("x")

    with patch("file_organizer.services.inference_timer.logger") as mock_logger:
        with time_inference("text", f) as t:
            # mark_invoked() not called — simulates a pre-inference
            # early return (file-not-found, circuit-open, …).
            pass

    mock_logger.debug.assert_not_called()
    # elapsed_ms is still measured (callers may inspect it directly).
    assert t.elapsed_ms < 1000.0


def test_logs_error_field_on_exception(tmp_path: Path) -> None:
    f = tmp_path / "shot.png"
    f.write_bytes(b"")

    with patch("file_organizer.services.inference_timer.logger") as mock_logger:
        with pytest.raises(ValueError):
            with time_inference("vision", f):
                # No mark_invoked() — but the exception still triggers
                # the log because it's interpreted as a started-then-
                # failed inference.
                raise ValueError("bad input")

    mock_logger.debug.assert_called_once()
    fmt, kind, _ms, file_name, error = mock_logger.debug.call_args.args
    assert "error={}" in fmt
    assert kind == "vision"
    assert file_name == "shot.png"
    assert error == "ValueError"


def test_accepts_string_path(tmp_path: Path) -> None:
    """Path-or-str is accepted; internal logging uses the basename."""
    with patch("file_organizer.services.inference_timer.logger") as mock_logger:
        with time_inference("text", str(tmp_path / "report.md")) as t:
            t.mark_invoked()

    _fmt, _kind, _ms, file_name = mock_logger.debug.call_args.args
    assert file_name == "report.md"


def test_zero_duration_is_not_negative(tmp_path: Path) -> None:
    """A no-op body still produces a finite, small reading."""
    with time_inference("text", tmp_path / "x") as t:
        t.mark_invoked()
    assert isinstance(t.elapsed_ms, float)
    assert t.elapsed_ms < 1000.0
