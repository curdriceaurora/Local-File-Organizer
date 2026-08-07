"""Tests for the global-state-assertion CI rail (issue #1721).

The rail flags tests that reach for a process-global channel when they mean
something specific. Every positive case below is the real shape of a flake
fixed in #1720 — none of them reproduced on a developer machine, and each
cost a CI cycle to even observe:

- ``sys.platform`` mutated on the real module: ``pydub.utils`` calling
  ``shutil.which("ffmpeg")`` at import took shutil's win32 branch, which
  dereferences ``_winapi`` (``None`` off Windows).
- ``logging.Logger.error`` patched on the class: an unrelated library log
  turned ``assert_called_once`` into "Called 2 times" on py3.14.
- A whole captured stream compared for equality: PyMuPDF's ``fitz``
  deprecation notice, printed on import, broke the match on py3.14.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.ci.guardrails import check_global_state_assertions as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _check(tmp_path: Path, source: str) -> list[tuple[int, str]]:
    src = tmp_path / "test_sample.py"
    src.write_text(dedent(source), encoding="utf-8")
    return checker.check_file(src)


class TestSysPlatformMutation:
    """Rule 1 — mutating the real sys module."""

    def test_flags_bare_sys_platform_mutation(self, tmp_path: Path) -> None:
        violations = _check(
            tmp_path,
            """
            import sys

            def test_windows_path(monkeypatch):
                monkeypatch.setattr(sys, "platform", "win32")
            """,
        )
        assert len(violations) == 1
        assert "process-wide" in violations[0][1]

    def test_flags_module_qualified_sys_mutation(self, tmp_path: Path) -> None:
        """``ext.sys`` IS ``sys`` — the qualification does not make it local."""
        violations = _check(
            tmp_path,
            """
            def test_windows_path(monkeypatch):
                import pkg.mod as ext

                monkeypatch.setattr(ext.sys, "platform", "win32")
            """,
        )
        assert len(violations) == 1

    def test_allows_patching_the_modules_own_sys_reference(self, tmp_path: Path) -> None:
        """The fix shape must stay clean: swap the module's sys, not sys itself."""
        violations = _check(
            tmp_path,
            """
            from types import SimpleNamespace

            def test_windows_path(monkeypatch):
                import pkg.mod as ext

                monkeypatch.setattr(ext, "sys", SimpleNamespace(platform="win32"))
            """,
        )
        assert violations == []

    def test_ignores_routine_sys_attributes(self, tmp_path: Path) -> None:
        """argv/modules are mutated legitimately all over; only platform is guarded."""
        violations = _check(
            tmp_path,
            """
            import sys

            def test_args(monkeypatch):
                monkeypatch.setattr(sys, "argv", ["prog"])
            """,
        )
        assert violations == []


class TestLoggerClassPatch:
    """Rule 2 — patching the Logger class rather than a logger."""

    def test_flags_logger_class_patch_by_string(self, tmp_path: Path) -> None:
        violations = _check(
            tmp_path,
            """
            from unittest.mock import patch

            def test_logs_once():
                with patch("logging.Logger.error") as mock_err:
                    mock_err.assert_called_once()
            """,
        )
        assert len(violations) == 1
        assert "every logger in the process" in violations[0][1]

    def test_flags_logger_class_patch_by_object(self, tmp_path: Path) -> None:
        violations = _check(
            tmp_path,
            """
            import logging
            from unittest.mock import patch

            def test_logs_once():
                with patch.object(logging.Logger, "error"):
                    pass
            """,
        )
        assert len(violations) == 1

    def test_allows_patching_a_module_logger(self, tmp_path: Path) -> None:
        """The fix shape: patch the logger the code under test actually uses."""
        violations = _check(
            tmp_path,
            """
            from unittest.mock import patch

            def test_logs_once():
                import pkg.mod as mod

                with patch.object(mod.logger, "error") as mock_err:
                    mock_err.assert_called_once()
            """,
        )
        assert violations == []


class TestWholeStreamEquality:
    """Rule 3 — comparing an entire captured stream."""

    def test_flags_subprocess_stdout_equality(self, tmp_path: Path) -> None:
        violations = _check(
            tmp_path,
            """
            import subprocess

            def test_prints_value():
                result = subprocess.run(["prog"], capture_output=True, text=True)
                assert result.stdout.strip() == "1,3"
            """,
        )
        assert len(violations) == 1
        assert "entire captured stream" in violations[0][1]

    def test_flags_capsys_equality(self, tmp_path: Path) -> None:
        violations = _check(
            tmp_path,
            """
            def test_prints_value(capsys):
                print("hello")
                assert capsys.readouterr().out == "hello\\n"
            """,
        )
        assert len(violations) == 1

    def test_allows_membership_and_marked_lines(self, tmp_path: Path) -> None:
        """Both documented fix shapes must stay clean."""
        violations = _check(
            tmp_path,
            """
            import subprocess

            def test_prints_value():
                result = subprocess.run(["prog"], capture_output=True, text=True)
                assert "1,3" in result.stdout
                marked = [
                    line.partition(":")[2]
                    for line in result.stdout.splitlines()
                    if line.startswith("RESULT:")
                ]
                assert marked == ["1,3"]
            """,
        )
        assert violations == []


def test_targeted_noqa_suppresses(tmp_path: Path) -> None:
    """Sometimes the global really is the subject under test."""
    violations = _check(
        tmp_path,
        """
        import sys

        def test_platform_reporting(monkeypatch):
            monkeypatch.setattr(sys, "platform", "win32")  # noqa: global-state-assertion
        """,
    )
    assert violations == []


def test_bare_noqa_does_not_suppress(tmp_path: Path) -> None:
    """Suppression must name this rail, matching the repo-wide convention."""
    violations = _check(
        tmp_path,
        """
        import sys

        def test_platform_reporting(monkeypatch):
            monkeypatch.setattr(sys, "platform", "win32")  # noqa
        """,
    )
    assert len(violations) == 1
