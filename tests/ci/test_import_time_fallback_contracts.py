"""Import-time fallback contract checks for runtime-derived module defaults.

Issue #822 requires deterministic fallback tests for high-impact import-time probes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]

_IMPORT_TIME_FALLBACK_CONTRACTS = (
    {
        "module_path": "src/file_organizer/tui/settings_view.py",
        "probe_regex": r"^_MAX_WORKERS_CAP\s*=\s*max\(1,\s*os\.cpu_count\(\)\s*or\s*1\)",
        "test_path": "tests/tui/test_settings_view.py",
        "test_name": "test_load_parallel_runtime_settings_uses_cpu_count_fallback_when_unavailable",
        "required_snippets": (
            'patch("os.cpu_count", return_value=None)',
            "importlib.reload(settings_view_module)",
        ),
    },
)


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing required fallback test: {name}")


@pytest.mark.parametrize("contract", _IMPORT_TIME_FALLBACK_CONTRACTS)
def test_import_time_probe_has_runtime_and_test_contract(contract: dict[str, object]) -> None:
    module_path = FO_ROOT / str(contract["module_path"])
    test_path = FO_ROOT / str(contract["test_path"])

    assert module_path.is_file(), f"Missing module under fallback contract: {module_path}"
    assert test_path.is_file(), f"Missing fallback test file: {test_path}"

    module_source = module_path.read_text(encoding="utf-8")
    probe_pattern = re.compile(str(contract["probe_regex"]), flags=re.MULTILINE)
    assert probe_pattern.search(module_source), (
        f"Expected import-time probe assignment was not found in module:\n{module_path}"
    )

    test_source = test_path.read_text(encoding="utf-8")
    test_tree = ast.parse(test_source, filename=str(test_path))
    function = _find_function(test_tree, str(contract["test_name"]))
    function_source = ast.get_source_segment(test_source, function) or ""

    for snippet in contract["required_snippets"]:
        assert isinstance(snippet, str)
        assert snippet in function_source, (
            "Fallback test no longer proves import-time recomputation semantics. "
            f"Missing snippet {snippet!r} in {test_path}:{function.lineno}"
        )
