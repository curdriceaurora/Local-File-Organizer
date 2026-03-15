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
    """Find function by name, searching both module-level and inside classes."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
        # Also search inside classes
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
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


def _is_explicit_empty_sequence_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.List):
        return len(node.elts) == 0
    if isinstance(node, ast.Tuple):
        return len(node.elts) == 0
    return False


def _is_structured_delegation_argument(node: ast.expr) -> bool:
    """Accept structured payload expressions and reject scalar literals."""
    if _is_explicit_empty_sequence_literal(node):
        return False
    if isinstance(node, (ast.List, ast.Tuple)):
        return True
    if isinstance(
        node,
        (
            ast.Name,
            ast.Attribute,
            ast.Subscript,
            ast.Call,
            ast.ListComp,
            ast.GeneratorExp,
            ast.SetComp,
            ast.DictComp,
        ),
    ):
        return True
    return False


def _has_mock_assert_called_once_with(function: ast.FunctionDef, *, mock_name: str) -> bool:
    """Check for mock.assert_called_once_with(...) call with strong argument payload.

    Requires at least one structured, non-empty candidate payload argument.
    This rejects scalar literals (for example, ``1``) and explicit empty
    list/tuple literals while preserving flexibility for variables and
    computed payload expressions.
    """
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "assert_called_once_with"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == mock_name
        ):
            if (
                node.args
                and _is_structured_delegation_argument(node.args[0])
                and not any(_is_explicit_empty_sequence_literal(arg) for arg in node.args)
            ):
                return True
    return False


def _has_strong_processed_count_assert(function: ast.FunctionDef) -> bool:
    """Check for any assert with .processed_count == value (variable-name agnostic)."""

    def _is_processed_count_attr(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.attr == "processed_count"
        )

    for node in ast.walk(function):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        compare = node.test
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq):
            continue
        if len(compare.comparators) != 1:
            continue
        left, right = compare.left, compare.comparators[0]
        if _is_processed_count_attr(left) or _is_processed_count_attr(right):
            return True
    return False


def _has_model_safe_cleanup_call(function: ast.FunctionDef) -> bool:
    """Check for any .safe_cleanup() call on any variable (variable-name agnostic)."""
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr == "safe_cleanup"
        ):
            return True
    return False


def _asserted_model_initialized_state_events(function: ast.FunctionDef) -> list[tuple[int, bool]]:
    """Collect ``is_initialized is <bool>`` assertion events with source line ordering."""
    events: list[tuple[int, bool]] = []
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
            and test.left.attr == "is_initialized"
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, bool)
        ):
            events.append((node.lineno, test.comparators[0].value))
    return sorted(events, key=lambda entry: entry[0])


def _safe_cleanup_call_lines(function: ast.FunctionDef) -> list[int]:
    """Collect source lines containing ``*.safe_cleanup()`` invocations."""
    lines: list[int] = []
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr == "safe_cleanup"
        ):
            lines.append(node.lineno)
    return sorted(lines)


def _has_initialized_state_transition_around_cleanup(function: ast.FunctionDef) -> bool:
    """Require ``is_initialized`` to be asserted True before cleanup and False after."""
    cleanup_lines = _safe_cleanup_call_lines(function)
    if not cleanup_lines:
        return False
    cleanup_line = cleanup_lines[0]
    state_events = _asserted_model_initialized_state_events(function)
    has_true_before = any(state is True and line < cleanup_line for line, state in state_events)
    has_false_after = any(state is False and line > cleanup_line for line, state in state_events)
    return has_true_before and has_false_after


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
        "a structured non-empty candidate payload via mocked_io_suite.assert_called_once_with(...)."
    )
    assert _has_strong_processed_count_assert(function), (
        "Audio fallback delegation test must assert returned payload strength with "
        "an equality assertion involving result.processed_count (for example, "
        "result.processed_count == expected_result)."
    )


def test_benchmark_stub_cleanup_parity_test_enforces_pre_and_post_state() -> None:
    """Benchmark model-stub parity test must verify cleanup interface and state transition."""
    tree = _parse_python_ast(SUITE_RUNNERS_TEST_PATH)
    function = _find_function(tree, "test_benchmark_model_stub_exposes_safe_cleanup")

    assert _has_model_safe_cleanup_call(function), (
        "Benchmark model-stub test must call model.safe_cleanup() to enforce "
        "processor cleanup interface parity."
    )
    assert _has_initialized_state_transition_around_cleanup(function), (
        "Benchmark model-stub cleanup test must assert model.is_initialized is True "
        "before safe_cleanup() and model.is_initialized is False after safe_cleanup()."
    )
