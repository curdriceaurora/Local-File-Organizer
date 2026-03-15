"""CI guardrails for benchmark test-proof and marker quality."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUITE_RUNNERS_TEST_PATH = REPO_ROOT / "tests" / "cli" / "test_benchmark_suite_runners.py"


def _parse_python_ast(path: Path) -> ast.Module:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Find function by name, honoring module execution order for shadowed defs."""
    matches: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            matches.append(node)
        elif isinstance(node, ast.ClassDef) and _is_pytest_collected_test_class(node):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    matches.append(item)
    if matches:
        # Pytest executes the last module binding for a redefined test name.
        return matches[-1]
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


def _is_pytest_collected_test_class(node: ast.ClassDef) -> bool:
    """Return True when class matches pytest's class collection contract."""
    if not node.name.startswith("Test"):
        return False
    return not any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__"
        for item in node.body
    )


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


def _iter_statement_nodes_excluding_nested_defs(statement: ast.stmt) -> ast.AST:
    """Yield statement subtree nodes while skipping deferred/nested executable bodies."""
    stack: list[ast.AST] = [statement]
    while stack:
        node = stack.pop()
        yield node

        # Prune branches proven unreachable by constant-condition truthiness.
        if isinstance(node, ast.If) and isinstance(node.test, ast.Constant):
            children = list(node.body if bool(node.test.value) else node.orelse)
        elif isinstance(node, ast.While) and isinstance(node.test, ast.Constant):
            # while <const>: body executes iff truthy constant; orelse runs on normal completion.
            children = list(node.body if bool(node.test.value) else node.orelse)
        else:
            children = list(ast.iter_child_nodes(node))

        for child in reversed(children):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            stack.append(child)


def _iter_top_level_statement_nodes(function: ast.FunctionDef) -> ast.AST:
    """Yield AST nodes from executable top-level statements only.

    Nested ``def``/``class`` bodies are intentionally skipped so dead helper
    code cannot satisfy guardrail requirements.
    """
    for statement in function.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield from _iter_statement_nodes_excluding_nested_defs(statement)


def _has_mock_assert_called_once_with(function: ast.FunctionDef, *, mock_name: str) -> bool:
    """Check for mock.assert_called_once_with(...) call with strong argument payload.

    Requires at least one structured, non-empty candidate payload argument.
    This rejects scalar literals (for example, ``1``) and explicit empty
    list/tuple literals while preserving flexibility for variables and
    computed payload expressions.
    """
    for node in _iter_top_level_statement_nodes(function):
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
    """Check for assert on processed_count tied to the direct suite-run result."""

    result_names: set[str] = set()
    for node in _iter_top_level_statement_nodes(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value.func
            if (
                isinstance(call, ast.Attribute)
                and call.attr == "_run_audio_suite"
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                result_names.add(node.targets[0].id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            call = node.value.func
            if (
                isinstance(call, ast.Attribute)
                and call.attr == "_run_audio_suite"
                and isinstance(node.target, ast.Name)
            ):
                result_names.add(node.target.id)

    if not result_names:
        return False

    def _is_processed_count_attr(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.attr == "processed_count"
            and node.value.id in result_names
        )

    for node in _iter_top_level_statement_nodes(function):
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
    """Check for any top-level .safe_cleanup() call on a named receiver."""
    for node in _iter_top_level_statement_nodes(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr == "safe_cleanup"
        ):
            return True
    return False


def _asserted_model_initialized_state_events(
    function: ast.FunctionDef,
) -> list[tuple[int, str, bool]]:
    """Collect ``<receiver>.is_initialized is <bool>`` events with line ordering."""
    events: list[tuple[int, str, bool]] = []
    for node in _iter_top_level_statement_nodes(function):
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
            events.append((node.lineno, test.left.value.id, test.comparators[0].value))
    return sorted(events, key=lambda entry: entry[0])


def _safe_cleanup_call_events(function: ast.FunctionDef) -> list[tuple[int, str]]:
    """Collect source lines and receivers for top-level ``*.safe_cleanup()`` calls."""
    events: list[tuple[int, str]] = []
    for node in _iter_top_level_statement_nodes(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr == "safe_cleanup"
        ):
            events.append((node.lineno, node.func.value.id))
    return sorted(events, key=lambda entry: entry[0])


def _has_initialized_state_transition_around_cleanup(function: ast.FunctionDef) -> bool:
    """Require receiver-matched True-before and False-after assertions for every cleanup call."""
    cleanup_events = _safe_cleanup_call_events(function)
    if not cleanup_events:
        return False
    state_events = _asserted_model_initialized_state_events(function)
    for cleanup_line, cleanup_receiver in cleanup_events:
        has_true_before = any(
            state is True and line < cleanup_line and receiver == cleanup_receiver
            for line, receiver, state in state_events
        )
        has_false_after = any(
            state is False and line > cleanup_line and receiver == cleanup_receiver
            for line, receiver, state in state_events
        )
        if not (has_true_before and has_false_after):
            return False
    return True


def _parse_single_function(source: str, function_name: str = "subject") -> ast.FunctionDef:
    """Parse and return a single function from source text."""
    module = ast.parse(textwrap.dedent(source))
    function = _find_function(module, function_name)
    return function


def test_find_function_ignores_non_test_class_methods() -> None:
    """Class methods should be discoverable only for pytest-collected test classes."""
    module = ast.parse(
        textwrap.dedent(
            """
            class Helper:
                def test_target(self) -> None:
                    pass
            """
        )
    )
    with pytest.raises(AssertionError):
        _find_function(module, "test_target")


def test_find_function_accepts_pytest_collected_test_class_methods() -> None:
    """Methods on pytest-collected classes should remain discoverable."""
    module = ast.parse(
        textwrap.dedent(
            """
            class TestSuite:
                def test_target(self) -> None:
                    pass
            """
        )
    )
    function = _find_function(module, "test_target")
    assert function.name == "test_target"


def test_find_function_rejects_test_class_with_init() -> None:
    """Pytest does not collect test classes that define __init__."""
    module = ast.parse(
        textwrap.dedent(
            """
            class TestSuite:
                def __init__(self) -> None:
                    self.x = 1

                def test_target(self) -> None:
                    pass
            """
        )
    )
    with pytest.raises(AssertionError):
        _find_function(module, "test_target")


def test_find_function_prefers_last_shadowed_module_definition() -> None:
    """When test names are redefined, guardrails must inspect the executed binding."""
    module = ast.parse(
        textwrap.dedent(
            """
            def test_target() -> None:
                pass

            def test_target() -> None:
                assert True
            """
        )
    )
    function = _find_function(module, "test_target")
    assert function.lineno == 5


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


@pytest.mark.parametrize(
    ("call_expr", "expected"),
    [
        ("mocked_io_suite.assert_called_once_with([candidate])", True),
        ("mocked_io_suite.assert_called_once_with(candidates)", True),
        ("mocked_io_suite.assert_called_once_with(build_candidates())", True),
        ("mocked_io_suite.assert_called_once_with([p for p in candidates])", True),
        ("mocked_io_suite.assert_called_once_with([])", False),
        ("mocked_io_suite.assert_called_once_with(())", False),
        ("mocked_io_suite.assert_called_once_with(1)", False),
        ("mocked_io_suite.assert_called_once_with('candidate')", False),
        ("mocked_io_suite.assert_called_once_with()", False),
        ("different_mock.assert_called_once_with([candidate])", False),
    ],
)
def test_mock_assert_guardrail_rejects_weak_or_non_structured_payloads(
    call_expr: str, expected: bool
) -> None:
    """Guardrail must accept structured candidate payload assertions only."""
    function = _parse_single_function(
        f"""
        def subject() -> None:
            {call_expr}
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is expected


def test_mock_assert_guardrail_ignores_nested_helper_assertions() -> None:
    """Nested helper assertions must not satisfy top-level delegation guardrails."""
    function = _parse_single_function(
        """
        def subject() -> None:
            def hidden() -> None:
                mocked_io_suite.assert_called_once_with([candidate])
            pass
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is False


def test_mock_assert_guardrail_ignores_nested_helper_assertions_in_conditionals() -> None:
    """Nested helper assertions inside top-level conditionals must be ignored."""
    function = _parse_single_function(
        """
        def subject() -> None:
            if True:
                def hidden() -> None:
                    mocked_io_suite.assert_called_once_with([candidate])
            pass
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is False


def test_mock_assert_guardrail_ignores_unreachable_branch_assertions() -> None:
    """Assertions under ``if False`` must not satisfy delegation guardrails."""
    function = _parse_single_function(
        """
        def subject() -> None:
            if False:
                mocked_io_suite.assert_called_once_with([candidate])
            pass
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is False


@pytest.mark.parametrize("constant_expr", ["0", "''", "None"])
def test_mock_assert_guardrail_ignores_non_bool_constant_false_branch_assertions(
    constant_expr: str,
) -> None:
    """Assertions in falsy constant branches must not satisfy delegation guardrails."""
    function = _parse_single_function(
        f"""
        def subject() -> None:
            if {constant_expr}:
                mocked_io_suite.assert_called_once_with([candidate])
            pass
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is False


def test_mock_assert_guardrail_ignores_lambda_body_assertions() -> None:
    """Deferred lambda bodies must not satisfy delegation guardrails."""
    function = _parse_single_function(
        """
        def subject() -> None:
            _hidden = lambda: mocked_io_suite.assert_called_once_with([candidate])
            pass
        """
    )
    assert _has_mock_assert_called_once_with(function, mock_name="mocked_io_suite") is False


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            assert result.processed_count == expected_result
            """,
            True,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            assert other.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            def hidden() -> None:
                assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            if True:
                def hidden() -> None:
                    assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            if False:
                assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            if 0:
                assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            if "":
                assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            if None:
                assert result.processed_count == expected_result
            """,
            False,
        ),
        (
            """
            result = benchmark_cli._run_audio_suite(files)
            _hidden = lambda: (result.processed_count == expected_result)
            """,
            False,
        ),
    ],
)
def test_processed_count_guardrail_binds_to_run_audio_result(body: str, expected: bool) -> None:
    """Processed-count guardrail must bind to the direct suite-run result variable."""
    function_body = textwrap.indent(textwrap.dedent(body).strip(), "    ")
    source = f"def subject() -> None:\n{function_body}\n"
    function = _parse_single_function(source)
    assert _has_strong_processed_count_assert(function) is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            """
            assert model.is_initialized is True
            model.safe_cleanup()
            assert model.is_initialized is False
            """,
            True,
        ),
        (
            """
            assert model.is_initialized is False
            model.safe_cleanup()
            assert model.is_initialized is True
            """,
            False,
        ),
        (
            """
            assert model.is_initialized is True
            model.safe_cleanup()
            """,
            False,
        ),
        (
            """
            model.safe_cleanup()
            assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            assert model.is_initialized is True
            assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            assert model.is_initialized is True
            other.safe_cleanup()
            assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            assert other.is_initialized is True
            model.safe_cleanup()
            assert other.is_initialized is False
            """,
            False,
        ),
        (
            """
            if True:
                def hidden() -> None:
                    assert model.is_initialized is True
                    model.safe_cleanup()
                    assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            assert model.is_initialized is True
            model.safe_cleanup()
            assert model.is_initialized is False
            assert other.is_initialized is True
            other.safe_cleanup()
            assert other.is_initialized is False
            """,
            True,
        ),
        (
            """
            assert model.is_initialized is True
            model.safe_cleanup()
            assert model.is_initialized is False
            other.safe_cleanup()
            assert other.is_initialized is False
            """,
            False,
        ),
        (
            """
            if False:
                assert model.is_initialized is True
                model.safe_cleanup()
                assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            if 0:
                assert model.is_initialized is True
                model.safe_cleanup()
                assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            if "":
                assert model.is_initialized is True
                model.safe_cleanup()
                assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            if None:
                assert model.is_initialized is True
                model.safe_cleanup()
                assert model.is_initialized is False
            """,
            False,
        ),
        (
            """
            _hidden = lambda: (
                model.is_initialized is True,
                model.safe_cleanup(),
                model.is_initialized is False,
            )
            """,
            False,
        ),
    ],
)
def test_cleanup_transition_guardrail_enforces_ordered_pre_post_assertions(
    body: str, expected: bool
) -> None:
    """Guardrail must enforce True-before and False-after around safe_cleanup()."""
    function_body = textwrap.indent(textwrap.dedent(body).strip(), "    ")
    source = f"def subject() -> None:\n{function_body}\n"
    function = _parse_single_function(source)
    assert _has_initialized_state_transition_around_cleanup(function) is expected
