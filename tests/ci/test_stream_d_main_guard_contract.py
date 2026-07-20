"""Contracts for Stream D standalone __main__ cleanup targets."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_MODULES: tuple[Path, ...] = (
    REPO_ROOT / "src" / "file_organizer" / "cli" / "dedupe.py",
    REPO_ROOT / "src" / "file_organizer" / "cli" / "analytics.py",
    REPO_ROOT / "src" / "file_organizer" / "cli" / "undo_redo.py",
    REPO_ROOT / "src" / "file_organizer" / "api" / "api_keys.py",
    REPO_ROOT / "src" / "file_organizer" / "review_regressions" / "audit.py",
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _is_name_main_compare(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq) or len(node.comparators) != 1:
        return False

    left = node.left
    right = node.comparators[0]
    name_main = isinstance(left, ast.Name) and left.id == "__name__"
    const_main = isinstance(right, ast.Constant) and right.value == "__main__"
    reverse_const = isinstance(left, ast.Constant) and left.value == "__main__"
    reverse_name = isinstance(right, ast.Name) and right.id == "__name__"
    return (name_main and const_main) or (reverse_const and reverse_name)


def _has_main_guard(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            if _is_name_main_compare(node.test):
                return True
    return False


@pytest.mark.parametrize("module_path", TARGET_MODULES, ids=lambda path: path.name)
def test_stream_d_modules_do_not_define_standalone_main_guards(module_path: Path) -> None:
    source = module_path.read_text(encoding="utf-8")
    assert not _has_main_guard(source), (
        f"{module_path.relative_to(REPO_ROOT)} must not define "
        'if __name__ == "__main__" after Stream D cleanup.'
    )


def test_api_keys_help_usage_matches_cli_command(capsys: pytest.CaptureFixture[str]) -> None:
    from file_organizer.api.api_keys import _main

    assert _main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "Usage: fo api-keys generate --output PATH [--prefix PREFIX]" in captured.out
