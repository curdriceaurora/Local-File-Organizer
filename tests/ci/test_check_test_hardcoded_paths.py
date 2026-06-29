"""Tests for the WP-6.2 test-hardcoded-paths CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_test_hardcoded_paths as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_unix_home_path(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('path = Path("/home/user/documents")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "/home/user/documents" in violations[0][1]  # noqa: test-hardcoded-paths


def test_flags_tmp_path_literal(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('result = do_thing(Path("/tmp/test.txt"))\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "/tmp/test.txt" in violations[0][1]  # noqa: test-hardcoded-paths


def test_flags_users_path(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('assert result == "/Users/someone/Documents"\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "/Users/someone/Documents" in violations[0][1]  # noqa: test-hardcoded-paths


def test_flags_windows_absolute_path(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('path = Path("C:\\\\Users\\\\test\\\\file.txt")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "C:\\" in violations[0][1]  # noqa: test-hardcoded-paths


def test_flags_etc_path(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text('assert is_hidden(Path("/etc/passwd"))\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_string_literal_noqa_directive_does_not_suppress(tmp_path: Path) -> None:
    """Verify that 'noqa: test-hardcoded-paths' inside string literal doesn't suppress violation."""
    src = tmp_path / "string_literal_false_positive.py"
    src.write_text(  # noqa: test-hardcoded-paths
        'msg = "some text with noqa: test-hardcoded-paths in it"\npath = Path("/tmp/test")\n',
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "/tmp/test" in violations[0][1]  # noqa: test-hardcoded-paths


def test_targeted_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "exempt.py"
    src.write_text(
        'path = Path("/home/user/docs")  # noqa: test-hardcoded-paths\n', encoding="utf-8"
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text('path = Path("/home/user/docs")  # noqa\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_unrelated_noqa_code_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "other.py"
    src.write_text('path = Path("/home/user/docs")  # noqa: E501\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_relative_path_not_flagged(tmp_path: Path) -> None:
    src = tmp_path / "ok.py"
    src.write_text('path = Path("relative/path/to/file.txt")\n', encoding="utf-8")
    assert checker.check_file(src) == []


def test_url_like_path_not_flagged(tmp_path: Path) -> None:
    src = tmp_path / "ok.py"
    src.write_text('url = "/api/v1/users"\n', encoding="utf-8")
    assert checker.check_file(src) == []


def test_non_path_root_not_flagged(tmp_path: Path) -> None:
    src = tmp_path / "ok.py"
    src.write_text('url = "/some/relative-ish/path"\n', encoding="utf-8")
    assert checker.check_file(src) == []


def test_multiple_violations_reported(tmp_path: Path) -> None:
    src = tmp_path / "multi.py"
    src.write_text('a = Path("/tmp/a.txt")\nb = Path("/home/user/b.txt")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 2


def test_multiple_violations_one_suppressed(tmp_path: Path) -> None:
    src = tmp_path / "mixed.py"
    src.write_text(
        'a = Path("/tmp/a.txt")  # noqa: test-hardcoded-paths\nb = Path("/home/user/b.txt")\n',
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "/home/user/b.txt" in violations[0][1]  # noqa: test-hardcoded-paths


def test_syntax_error_returns_empty(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def bad_syntax(:\n", encoding="utf-8")
    assert checker.check_file(src) == []


def test_check_file_returns_line_number(tmp_path: Path) -> None:
    src = tmp_path / "lineno.py"
    src.write_text('x = 1\ny = Path("/tmp/foo.txt")\n', encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    lineno, msg, line = violations[0]
    assert lineno == 2
    assert "/tmp/foo.txt" in msg  # noqa: test-hardcoded-paths
