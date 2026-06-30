"""CI guardrails for daemon PID lifecycle contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
PID_MODULE = FO_ROOT / "src" / "file_organizer" / "daemon" / "pid.py"
SERVICE_MODULE = FO_ROOT / "src" / "file_organizer" / "daemon" / "service.py"


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                segment = ast.get_source_segment(source, item)
                assert segment is not None
                return segment
    raise AssertionError(f"Missing {class_name}.{method_name} in {path}")


def test_pid_record_write_includes_creation_time() -> None:
    source = _method_source(PID_MODULE, "PidFileManager", "write_pid_record")
    assert "psutil.Process(pid).create_time()" in source
    assert 'json.dumps({"pid": pid, "create_time": create_time})' in source


def test_pid_removal_revalidates_expected_record_before_unlink() -> None:
    source = _method_source(PID_MODULE, "PidFileManager", "remove_pid")
    assert "current_record = self.read_pid_record(pid_file)" in source
    assert "if current_record != expected_record:" in source
    assert "pid_file.unlink()" in source


def test_pid_claim_uses_atomic_exclusive_create() -> None:
    source = _method_source(PID_MODULE, "PidFileManager", "claim_pid_file")
    assert "os.O_CREAT | os.O_EXCL | os.O_WRONLY" in source
    assert "pid_file.unlink()" in source


def test_background_startup_failures_propagate_to_callers() -> None:
    source = _method_source(SERVICE_MODULE, "DaemonService", "start_background")
    assert 'raise RuntimeError("Daemon failed to start") from exc' in source
    assert "self._start_exception = None" in source
