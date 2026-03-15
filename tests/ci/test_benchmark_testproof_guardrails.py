"""CI guardrails for benchmark test-proof and marker quality."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUITE_RUNNERS_TEST_PATH = REPO_ROOT / "tests" / "cli" / "test_benchmark_suite_runners.py"


def _parse_python_ast(path: Path) -> ast.Module:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing required benchmark guardrail test function: {name}")


def _marker_from_decorator(decorator: ast.expr) -> str | None:
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
        and node.value.attr == "mark"
    ):
        return node.attr
    return None


def _pytest_markers(function: ast.FunctionDef) -> set[str]:
    markers: set[str] = set()
    for decorator in function.decorator_list:
        marker = _marker_from_decorator(decorator)
        if marker is not None:
            markers.add(marker)
    return markers


def _has_mock_assert_called_once_with(function: ast.FunctionDef, *, mock_name: str) -> bool:
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "assert_called_once_with"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == mock_name
        ):
            return True
    return False


def _assert_mentions_result_processed_count(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert):
            continue
        for expr in ast.walk(node.test):
            if (
                isinstance(expr, ast.Attribute)
                and isinstance(expr.value, ast.Name)
                and expr.value.id == "result"
                and expr.attr == "processed_count"
            ):
                return True
    return False


def _has_model_safe_cleanup_call(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "model"
            and node.func.attr == "safe_cleanup"
        ):
            return True
    return False


def _asserted_model_initialized_states(function: ast.FunctionDef) -> set[bool]:
    states: set[bool] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Is)
            and len(test.comparators) == 1
            and isinstance(test.left, ast.Attribute)
            and isinstance(test.left.value, ast.Name)
            and test.left.value.id == "model"
            and test.left.attr == "is_initialized"
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, bool)
        ):
            states.add(test.comparators[0].value)
    return states


def test_smoke_schema_test_has_required_pytest_markers() -> None:
    """Deterministic benchmark smoke contracts must keep smoke+ci+unit markers."""
    tree = _parse_python_ast(SUITE_RUNNERS_TEST_PATH)
    function = _find_function(tree, "test_benchmark_suite_smoke_outputs_expected_schema")
    markers = _pytest_markers(function)
    required = {"smoke", "ci", "unit"}
    assert required.issubset(markers), (
        "Benchmark deterministic schema smoke test is missing required markers.\n"
        f"Required: {sorted(required)}\nFound: {sorted(markers)}"
    )


def test_audio_fallback_test_proves_delegation_call_and_result_contract() -> None:
    """Fallback/delegation test must prove both delegated call path and returned payload."""
    tree = _parse_python_ast(SUITE_RUNNERS_TEST_PATH)
    function = _find_function(tree, "test_audio_suite_warns_when_falling_back_to_io")

    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite"), (
        "Audio fallback delegation test must assert delegated runner call arguments with "
        "mocked_io_suite.assert_called_once_with(...)."
    )
    assert _assert_mentions_result_processed_count(function), (
        "Audio fallback delegation test must assert the returned processed_count payload "
        "from the delegated runner result."
    )


def test_benchmark_stub_cleanup_parity_test_enforces_pre_and_post_state() -> None:
    """Benchmark model-stub parity test must verify cleanup interface and state transition."""
    tree = _parse_python_ast(SUITE_RUNNERS_TEST_PATH)
    function = _find_function(tree, "test_benchmark_model_stub_exposes_safe_cleanup")

    assert _has_model_safe_cleanup_call(function), (
        "Benchmark model-stub test must call model.safe_cleanup() to enforce "
        "processor cleanup interface parity."
    )
    states = _asserted_model_initialized_states(function)
    assert states == {False, True}, (
        "Benchmark model-stub cleanup test must assert pre/post initialization states "
        "(True before cleanup and False after cleanup)."
    )
