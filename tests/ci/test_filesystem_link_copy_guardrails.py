"""CI guardrails for filesystem link/copy/move race safety."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_MODULE = (
    FO_ROOT / "src" / "file_organizer" / "services" / "copilot" / "rules" / "actions.py"
)
EXECUTOR_MODULE = (
    FO_ROOT / "src" / "file_organizer" / "services" / "copilot" / "rules" / "executor.py"
)
ROLLBACK_MODULE = FO_ROOT / "src" / "file_organizer" / "undo" / "rollback.py"
DURABLE_MOVE_MODULE = FO_ROOT / "src" / "file_organizer" / "undo" / "durable_move.py"


def _method_source(path: Path, method_name: str, *, class_name: str | None = None) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    def _segment(node: ast.AST) -> str:
        segment = ast.get_source_segment(source, node)
        assert segment is not None
        return segment

    for node in tree.body:
        if class_name is None and isinstance(node, ast.FunctionDef) and node.name == method_name:
            return _segment(node)
        if class_name is not None and isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return _segment(item)
    raise AssertionError(f"Missing {method_name} in {path}")


def test_resolve_conflict_rechecks_symlink_and_directory_state_before_unlink() -> None:
    source = _method_source(ACTIONS_MODULE, "resolve_conflict")
    assert "if not path.exists() and not path.is_symlink():" in source
    assert "if path.is_dir() and not path.is_symlink():" in source
    assert "path.unlink()" in source


def test_copy_file_reserves_destination_atomically() -> None:
    source = _method_source(ACTIONS_MODULE, "copy_file")
    assert "SafeDir.open_root(source.parent)" in source
    assert "os.O_CREAT | os.O_EXCL | os.O_WRONLY" in source
    assert "shutil.copyfileobj(src_file, dst_file)" in source


def test_link_helpers_route_mutations_through_conflict_resolution() -> None:
    hardlink_source = _method_source(ACTIONS_MODULE, "apply_hardlink")
    symlink_source = _method_source(ACTIONS_MODULE, "apply_symlink")

    assert "resolve_conflict(destination, strategy)" in hardlink_source
    assert "os.link(source, resolved)" in hardlink_source
    assert "resolve_conflict(destination, strategy)" in symlink_source
    assert "resolved.symlink_to(source)" in symlink_source


def test_rule_executor_revalidates_destination_root_containment() -> None:
    source = _method_source(EXECUTOR_MODULE, "_target_path", class_name="RuleExecutor")
    assert "if raw.is_absolute():" in source
    assert "resolved_candidate.relative_to(resolved_base)" in source
    assert "Path traversal detected:" in source


def test_rollback_move_revalidates_identity_close_to_mutation() -> None:
    source = _method_source(ROLLBACK_MODULE, "_durable_move", class_name="RollbackExecutor")
    assert "if stat_mod.S_ISLNK(src_stat.st_mode):" in source
    assert "if stat_mod.S_ISLNK(os.lstat(src).st_mode):" in source
    assert "shutil.move(str(src), str(dst))" in source
    assert "if not cross_device and (dst_stat.st_dev, dst_stat.st_ino) != src_identity:" in source


def test_durable_move_preserves_inode_identity_and_symlink_handling() -> None:
    source = _method_source(DURABLE_MOVE_MODULE, "_capture_dst_inode")
    assert "os.lstat(dst)" in source
    assert "return st.st_dev, st.st_ino, st.st_size" in source
