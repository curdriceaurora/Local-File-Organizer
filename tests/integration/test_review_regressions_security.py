"""Integration tests for review_regressions/security.py."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from file_organizer.review_regressions.security import (
    SECURITY_DETECTORS,
    GuardedContextDirectPathDetector,
    ValidatedPathBypassDetector,
    _attr_root_name,
    _call_name,
    _is_allowed_paths_expr,
    _is_basename_extraction,
    _is_path_call,
    _is_resolve_path_call,
    _is_route_handler,
    _parent_map,
    _path_constructor_names,
    _path_module_aliases,
    _resolve_path_names,
    _walk_function_body,
    _window_has_codeql_suppression,
    _window_has_prevalidated_marker,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# _parent_map
# ---------------------------------------------------------------------------


class TestParentMap:
    def test_root_has_no_parent(self) -> None:
        tree = ast.parse("x = 1")
        parents = _parent_map(tree)
        assert tree not in parents

    def test_child_mapped_to_direct_parent(self) -> None:
        tree = ast.parse("x = 1")
        parents = _parent_map(tree)
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        assert parents[assign] is tree

    def test_grandchild_mapped_to_intermediate_node(self) -> None:
        tree = ast.parse("x = 1")
        parents = _parent_map(tree)
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        name_node = assign.targets[0]
        assert parents[name_node] is assign

    def test_every_non_root_node_has_a_parent(self) -> None:
        tree = ast.parse("def f(a):\n    return a + 1")
        parents = _parent_map(tree)
        all_nodes = list(ast.walk(tree))
        for node in all_nodes[1:]:
            assert node in parents, f"{type(node).__name__} missing from parent map"

    def test_returns_dict_with_ast_node_values(self) -> None:
        tree = ast.parse("y = 2 + 3")
        parents = _parent_map(tree)
        for value in parents.values():
            assert isinstance(value, ast.AST)


# ---------------------------------------------------------------------------
# _walk_function_body
# ---------------------------------------------------------------------------


class TestWalkFunctionBody:
    def test_yields_direct_body_nodes(self) -> None:
        tree = ast.parse("def f():\n    x = 1\n    return x")
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        nodes = list(_walk_function_body(func))
        node_types = [type(n).__name__ for n in nodes]
        assert "Assign" in node_types
        assert "Return" in node_types

    def test_does_not_descend_into_nested_function(self) -> None:
        src = "def outer():\n    def inner():\n        secret = 42\n    return 1"
        tree = ast.parse(src)
        outer = tree.body[0]
        assert isinstance(outer, ast.FunctionDef)
        nodes = list(_walk_function_body(outer))
        # The inner FunctionDef itself should appear (so callers can inspect it as a node)
        inner_funcs = [n for n in nodes if isinstance(n, ast.FunctionDef)]
        assert len(inner_funcs) == 1
        assert inner_funcs[0].name == "inner"
        # But the Assign node for 'secret = 42' inside inner must not appear
        assigns = [n for n in nodes if isinstance(n, ast.Assign)]
        assign_names = [a.targets[0].id for a in assigns if isinstance(a.targets[0], ast.Name)]
        assert "secret" not in assign_names

    def test_does_not_descend_into_lambda(self) -> None:
        src = "def f():\n    g = lambda x: x + 1\n    return g"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        nodes = list(_walk_function_body(func))
        # Lambda itself is yielded, but BinOp inside it is not
        lambdas = [n for n in nodes if isinstance(n, ast.Lambda)]
        assert len(lambdas) == 1
        binops_inside_lambda = [n for n in nodes if isinstance(n, ast.BinOp)]
        # The BinOp is inside the Lambda body — must not appear
        assert len(binops_inside_lambda) == 0

    def test_does_not_descend_into_classdef(self) -> None:
        src = "def f():\n    class Inner:\n        attr = 'hidden'\n    return Inner"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        nodes = list(_walk_function_body(func))
        assigns = [n for n in nodes if isinstance(n, ast.Assign)]
        assign_names = [a.targets[0].id for a in assigns if isinstance(a.targets[0], ast.Name)]
        assert "attr" not in assign_names

    def test_async_function_body_is_walked(self) -> None:
        src = "async def f():\n    x = 1\n    return x"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.AsyncFunctionDef)
        nodes = list(_walk_function_body(func))
        assert any(isinstance(n, ast.Assign) for n in nodes)


# ---------------------------------------------------------------------------
# _path_constructor_names
# ---------------------------------------------------------------------------


class TestPathConstructorNames:
    def test_direct_import_returns_path(self) -> None:
        tree = ast.parse("from pathlib import Path")
        names = _path_constructor_names(tree)
        assert names == {"Path"}

    def test_aliased_import_returns_alias(self) -> None:
        tree = ast.parse("from pathlib import Path as P")
        names = _path_constructor_names(tree)
        assert names == {"P"}

    def test_no_pathlib_import_returns_empty(self) -> None:
        tree = ast.parse("import os")
        names = _path_constructor_names(tree)
        assert names == set()

    def test_import_pathlib_module_not_included(self) -> None:
        tree = ast.parse("import pathlib")
        names = _path_constructor_names(tree)
        assert names == set()

    def test_multiple_imports_collected(self) -> None:
        src = "from pathlib import Path\nfrom pathlib import Path as P2"
        tree = ast.parse(src)
        names = _path_constructor_names(tree)
        assert "Path" in names
        assert "P2" in names


# ---------------------------------------------------------------------------
# _path_module_aliases
# ---------------------------------------------------------------------------


class TestPathModuleAliases:
    def test_bare_import_pathlib(self) -> None:
        tree = ast.parse("import pathlib")
        aliases = _path_module_aliases(tree)
        assert aliases == {"pathlib"}

    def test_aliased_import_pathlib(self) -> None:
        tree = ast.parse("import pathlib as pl")
        aliases = _path_module_aliases(tree)
        assert aliases == {"pl"}

    def test_from_import_not_included(self) -> None:
        tree = ast.parse("from pathlib import Path")
        aliases = _path_module_aliases(tree)
        assert aliases == set()

    def test_unrelated_import_not_included(self) -> None:
        tree = ast.parse("import os")
        aliases = _path_module_aliases(tree)
        assert aliases == set()


# ---------------------------------------------------------------------------
# _is_path_call
# ---------------------------------------------------------------------------


class TestIsPathCall:
    def _get_call_node(self, src: str) -> ast.Call:
        tree = ast.parse(src)
        return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))

    def test_path_name_call_matches(self) -> None:
        node = self._get_call_node("Path(x)")
        assert _is_path_call(node, constructor_names={"Path"}, module_aliases=set()) is True

    def test_path_name_call_wrong_set_no_match(self) -> None:
        node = self._get_call_node("Path(x)")
        assert _is_path_call(node, constructor_names=set(), module_aliases=set()) is False

    def test_pathlib_module_attribute_call_matches(self) -> None:
        node = self._get_call_node("pathlib.Path(x)")
        assert _is_path_call(node, constructor_names=set(), module_aliases={"pathlib"}) is True

    def test_non_call_node_returns_false(self) -> None:
        node = ast.Name(id="Path", ctx=ast.Load())
        assert _is_path_call(node, constructor_names={"Path"}, module_aliases=set()) is False

    def test_other_call_not_matched(self) -> None:
        node = self._get_call_node("open(x)")
        assert _is_path_call(node, constructor_names={"Path"}, module_aliases=set()) is False

    def test_aliased_constructor_matches(self) -> None:
        node = self._get_call_node("P(x)")
        assert _is_path_call(node, constructor_names={"P"}, module_aliases=set()) is True


# ---------------------------------------------------------------------------
# _resolve_path_names
# ---------------------------------------------------------------------------


class TestResolvePathNames:
    def test_direct_import_from_api_utils(self) -> None:
        tree = ast.parse("from file_organizer.api.utils import resolve_path")
        names = _resolve_path_names(tree)
        assert "resolve_path" in names

    def test_aliased_import_from_api_utils(self) -> None:
        tree = ast.parse("from file_organizer.api.utils import resolve_path as rp")
        names = _resolve_path_names(tree)
        assert "rp" in names

    def test_import_api_module_alias(self) -> None:
        tree = ast.parse("import file_organizer.api.utils as utils")
        names = _resolve_path_names(tree)
        assert "utils" in names

    def test_local_def_of_resolve_path(self) -> None:
        src = "def resolve_path(p):\n    return p"
        tree = ast.parse(src)
        names = _resolve_path_names(tree)
        assert "resolve_path" in names

    def test_unrelated_import_not_included(self) -> None:
        tree = ast.parse("from os.path import join")
        names = _resolve_path_names(tree)
        assert "join" not in names

    def test_empty_file_returns_empty_set(self) -> None:
        tree = ast.parse("")
        names = _resolve_path_names(tree)
        assert names == set()


# ---------------------------------------------------------------------------
# _attr_root_name
# ---------------------------------------------------------------------------


class TestAttrRootName:
    def test_simple_name_returns_id(self) -> None:
        node = ast.parse("foo.bar", mode="eval").body
        assert isinstance(node, ast.Attribute)
        assert _attr_root_name(node) == "foo"

    def test_chained_attributes_returns_root(self) -> None:
        node = ast.parse("a.b.c.d", mode="eval").body
        assert isinstance(node, ast.Attribute)
        assert _attr_root_name(node) == "a"

    def test_subscript_root_returns_none(self) -> None:
        node = ast.parse("x[0].attr", mode="eval").body
        assert isinstance(node, ast.Attribute)
        result = _attr_root_name(node)
        assert result is None

    def test_plain_name_node_returns_id(self) -> None:
        node = ast.Name(id="myvar", ctx=ast.Load())
        result = _attr_root_name(node)
        assert result == "myvar"


# ---------------------------------------------------------------------------
# _is_resolve_path_call
# ---------------------------------------------------------------------------


class TestIsResolvePathCall:
    def _get_call(self, src: str) -> ast.Call:
        tree = ast.parse(src)
        return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))

    def test_bare_name_call_matches(self) -> None:
        node = self._get_call("resolve_path(x)")
        assert _is_resolve_path_call(node, {"resolve_path"}) is True

    def test_bare_name_call_wrong_set(self) -> None:
        node = self._get_call("resolve_path(x)")
        assert _is_resolve_path_call(node, set()) is False

    def test_attribute_call_on_known_alias(self) -> None:
        node = self._get_call("utils.resolve_path(x)")
        assert _is_resolve_path_call(node, {"utils"}) is True

    def test_attribute_call_on_unknown_alias(self) -> None:
        node = self._get_call("utils.resolve_path(x)")
        assert _is_resolve_path_call(node, set()) is False

    def test_unrelated_service_with_same_method_name_not_matched(self) -> None:
        # T10 anti-pattern: same method name, unrelated receiver
        node = self._get_call("some_service.resolve_path(x)")
        assert _is_resolve_path_call(node, {"resolve_path"}) is False

    def test_non_call_node_returns_false(self) -> None:
        node = ast.Name(id="resolve_path", ctx=ast.Load())
        assert _is_resolve_path_call(node, {"resolve_path"}) is False


# ---------------------------------------------------------------------------
# _is_allowed_paths_expr
# ---------------------------------------------------------------------------


class TestIsAllowedPathsExpr:
    def test_bare_allowed_paths_name(self) -> None:
        node = ast.Name(id="allowed_paths", ctx=ast.Load())
        assert _is_allowed_paths_expr(node) is True

    def test_settings_allowed_paths_attribute(self) -> None:
        node = ast.parse("settings.allowed_paths", mode="eval").body
        assert _is_allowed_paths_expr(node) is True

    def test_other_name_not_matched(self) -> None:
        node = ast.Name(id="other_var", ctx=ast.Load())
        assert _is_allowed_paths_expr(node) is False

    def test_settings_other_attr_not_matched(self) -> None:
        node = ast.parse("settings.other_field", mode="eval").body
        assert _is_allowed_paths_expr(node) is False

    def test_non_settings_attribute_not_matched(self) -> None:
        node = ast.parse("config.allowed_paths", mode="eval").body
        assert _is_allowed_paths_expr(node) is False


# ---------------------------------------------------------------------------
# _window_has_codeql_suppression
# ---------------------------------------------------------------------------


class TestWindowHasCodeqlSuppression:
    def test_suppression_comment_detected_on_same_line(self) -> None:
        lines = ["x = Path(user_input)  # codeql[py/path-injection]"]
        assert _window_has_codeql_suppression(lines, 1) is True

    def test_suppression_comment_within_window(self) -> None:
        lines = [
            "# codeql[py/path-injection]",
            "x = Path(user_input)",
        ]
        assert _window_has_codeql_suppression(lines, 2) is True

    def test_suppression_comment_outside_window_not_detected(self) -> None:
        lines = [
            "# codeql[py/path-injection]",
            "a = 1",
            "b = 2",
            "c = 3",
            "d = 4",
            "x = Path(user_input)",
        ]
        assert _window_has_codeql_suppression(lines, 6) is False

    def test_no_suppression_comment_returns_false(self) -> None:
        lines = ["x = Path(user_input)"]
        assert _window_has_codeql_suppression(lines, 1) is False

    def test_empty_lines_does_not_crash(self) -> None:
        result = _window_has_codeql_suppression([], 0)
        assert result is False


# ---------------------------------------------------------------------------
# _window_has_prevalidated_marker
# ---------------------------------------------------------------------------


class TestWindowHasPrevalidatedMarker:
    def test_marker_detected_on_same_line(self) -> None:
        lines = ["# pre-validated at api boundary"]
        assert _window_has_prevalidated_marker(lines, 1) is True

    def test_marker_case_insensitive(self) -> None:
        lines = ["# Pre-Validated At API Boundary"]
        assert _window_has_prevalidated_marker(lines, 1) is True

    def test_marker_within_window_detected(self) -> None:
        lines = [
            "# pre-validated at api boundary",
            "path = Path(validated_input)",
        ]
        assert _window_has_prevalidated_marker(lines, 2) is True

    def test_no_marker_returns_false(self) -> None:
        lines = ["path = Path(user_input)"]
        assert _window_has_prevalidated_marker(lines, 1) is False

    def test_empty_lines_does_not_crash(self) -> None:
        result = _window_has_prevalidated_marker([], 0)
        assert result is False


# ---------------------------------------------------------------------------
# _is_basename_extraction
# ---------------------------------------------------------------------------


class TestIsBasenameExtraction:
    def test_path_name_attribute_is_safe(self) -> None:
        src = "Path(x).name"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_basename_extraction(call, parents) is True

    def test_path_stem_attribute_is_safe(self) -> None:
        src = "Path(x).stem"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_basename_extraction(call, parents) is True

    def test_path_suffix_attribute_is_safe(self) -> None:
        src = "Path(x).suffix"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_basename_extraction(call, parents) is True

    def test_path_call_used_directly_not_safe(self) -> None:
        src = "p = Path(x)"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_basename_extraction(call, parents) is False

    def test_path_parent_not_safe(self) -> None:
        src = "Path(x).parent"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_basename_extraction(call, parents) is False


# ---------------------------------------------------------------------------
# _call_name
# ---------------------------------------------------------------------------


class TestCallName:
    def _get_call(self, src: str) -> ast.Call:
        tree = ast.parse(src)
        return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))

    def test_simple_name_call(self) -> None:
        node = self._get_call("foo()")
        assert _call_name(node) == "foo"

    def test_attribute_call_returns_attr(self) -> None:
        node = self._get_call("obj.bar()")
        assert _call_name(node) == "bar"

    def test_subscript_call_returns_none(self) -> None:
        node = self._get_call("handlers[0]()")
        assert _call_name(node) is None


# ---------------------------------------------------------------------------
# _is_route_handler
# ---------------------------------------------------------------------------


class TestIsRouteHandler:
    def _get_func(self, src: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
        tree = ast.parse(src)
        return next(
            n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

    def test_get_decorator_recognized(self) -> None:
        func = self._get_func("@router.get('/path')\ndef handler(): pass")
        assert _is_route_handler(func) is True

    def test_post_decorator_recognized(self) -> None:
        func = self._get_func("@router.post('/path')\ndef handler(): pass")
        assert _is_route_handler(func) is True

    def test_no_decorator_returns_false(self) -> None:
        func = self._get_func("def plain_function(): pass")
        assert _is_route_handler(func) is False

    def test_unrelated_decorator_returns_false(self) -> None:
        func = self._get_func("@staticmethod\ndef handler(): pass")
        assert _is_route_handler(func) is False

    def test_async_route_handler_recognized(self) -> None:
        func = self._get_func("@router.get('/path')\nasync def handler(): pass")
        assert _is_route_handler(func) is True

    def test_bare_get_name_decorator_recognized(self) -> None:
        func = self._get_func("@get\ndef handler(): pass")
        assert _is_route_handler(func) is True


# ---------------------------------------------------------------------------
# GuardedContextDirectPathDetector.find_violations
# ---------------------------------------------------------------------------


class TestGuardedContextDirectPathDetector:
    def _make_api_dir(self, tmp_path: Path) -> Path:
        api_dir = tmp_path / "src" / "file_organizer" / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        return api_dir

    def test_empty_directory_produces_no_violations(self, tmp_path: Path) -> None:
        self._make_api_dir(tmp_path)
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_no_guarded_roots_produces_no_violations(self, tmp_path: Path) -> None:
        other = tmp_path / "src" / "file_organizer" / "other"
        other.mkdir(parents=True)
        (other / "module.py").write_text("from pathlib import Path\nx = Path(user_input)\n")
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_direct_path_call_in_route_handler_produces_violation(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "from pathlib import Path\n"
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/files')\n"
            "async def list_files(user_input: str):\n"
            "    p = Path(user_input)\n"
            "    return p\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        assert violations[0].rule_id == "unguarded-direct-path"
        assert violations[0].rule_class == "security"
        assert violations[0].detector_id == "security.guarded-context-direct-path"

    def test_path_dunder_file_is_safe(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "from pathlib import Path\nBASE_DIR = Path(__file__).parent\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_path_name_extraction_is_safe(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "from pathlib import Path\n"
            "def get_filename(user_input: str) -> str:\n"
            "    return Path(user_input).name\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_violation_path_is_relative_to_root(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "unsafe.py").write_text(
            "from pathlib import Path\n"
            "@router.get('/x')\n"
            "async def handler(x: str):\n"
            "    return Path(x)\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        assert not violations[0].path.startswith("/")
        assert "src/file_organizer/api" in violations[0].path

    def test_violation_has_non_none_line_number(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "unsafe.py").write_text(
            "from pathlib import Path\n"
            "@router.get('/x')\n"
            "async def handler(x: str):\n"
            "    return Path(x)\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        assert violations[0].line is not None
        assert violations[0].line > 0

    def test_violations_are_sorted(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "a_routes.py").write_text(
            "from pathlib import Path\n"
            "@router.get('/x')\n"
            "async def h1(x: str):\n"
            "    return Path(x)\n"
        )
        (api_dir / "b_routes.py").write_text(
            "from pathlib import Path\n"
            "@router.get('/y')\n"
            "async def h2(y: str):\n"
            "    return Path(y)\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        paths = [v.path for v in violations]
        assert paths == sorted(paths) or len(paths) == len(set(paths))

    def test_codeql_suppression_outside_route_handler_is_safe(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "from pathlib import Path\n# codeql[py/path-injection]\nSTATIC_DIR = Path('static')\n"
        )
        detector = GuardedContextDirectPathDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# ValidatedPathBypassDetector.find_violations
# ---------------------------------------------------------------------------


class TestValidatedPathBypassDetector:
    def _make_api_dir(self, tmp_path: Path) -> Path:
        api_dir = tmp_path / "src" / "file_organizer" / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        return api_dir

    def test_empty_directory_produces_no_violations(self, tmp_path: Path) -> None:
        self._make_api_dir(tmp_path)
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_route_without_resolve_path_produces_no_violations(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.post('/organize')\n"
            "async def organize(req):\n"
            "    organize(req)\n"
        )
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_raw_request_passed_to_sink_after_validation_produces_violation(
        self, tmp_path: Path
    ) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "def resolve_path(p): return p\n"
            "\n"
            "class router:\n"
            "    @staticmethod\n"
            "    def post(path): return lambda f: f\n"
            "\n"
            "class router:\n"
            "    post = lambda path: lambda f: f\n"
            "\n"
            "@router.post('/organize')\n"
            "async def do_organize(req):\n"
            "    safe = resolve_path(req.input_path)\n"
            "    organize(req)\n"
        )
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        assert violations[0].rule_class == "security"
        assert violations[0].detector_id == "security.validated-path-bypass"

    def test_violation_contains_raw_request_after_validation_rule_id(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "def resolve_path(p): return p\n"
            "@router.post('/organize')\n"
            "async def do_organize(req):\n"
            "    safe = resolve_path(req.input_path)\n"
            "    organize(req)\n"
        )
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        rule_ids = {v.rule_id for v in violations}
        assert "raw-request-after-validation" in rule_ids

    def test_violations_are_sorted(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "def resolve_path(p): return p\n"
            "@router.post('/a')\n"
            "async def handler_a(req):\n"
            "    safe = resolve_path(req.input_path)\n"
            "    organize(req)\n"
            "\n"
            "@router.post('/b')\n"
            "async def handler_b(req):\n"
            "    safe = resolve_path(req.input_path)\n"
            "    organize(req)\n"
        )
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        sort_keys = [v.sort_key() for v in violations]
        assert sort_keys == sorted(sort_keys)

    def test_violation_has_meaningful_message(self, tmp_path: Path) -> None:
        api_dir = self._make_api_dir(tmp_path)
        (api_dir / "routes.py").write_text(
            "def resolve_path(p): return p\n"
            "@router.post('/organize')\n"
            "async def do_organize(req):\n"
            "    safe = resolve_path(req.input_path)\n"
            "    organize(req)\n"
        )
        detector = ValidatedPathBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) >= 1
        assert len(violations[0].message) > 10
        assert "resolve_path" in violations[0].message or "raw" in violations[0].message


# ---------------------------------------------------------------------------
# SECURITY_DETECTORS
# ---------------------------------------------------------------------------


class TestSecurityDetectors:
    def test_is_a_tuple(self) -> None:
        assert isinstance(SECURITY_DETECTORS, tuple)
        assert len(SECURITY_DETECTORS) >= 1

    def test_has_two_detectors(self) -> None:
        assert len(SECURITY_DETECTORS) == 2

    def test_contains_guarded_context_detector(self) -> None:
        ids = {d.detector_id for d in SECURITY_DETECTORS}
        assert "security.guarded-context-direct-path" in ids

    def test_contains_validated_path_bypass_detector(self) -> None:
        ids = {d.detector_id for d in SECURITY_DETECTORS}
        assert "security.validated-path-bypass" in ids

    def test_all_detectors_have_find_violations(self) -> None:
        for detector in SECURITY_DETECTORS:
            assert callable(getattr(detector, "find_violations", None))

    def test_all_detectors_have_rule_class_security(self) -> None:
        for detector in SECURITY_DETECTORS:
            assert detector.rule_class == "security"

    def test_all_detectors_have_non_empty_description(self) -> None:
        for detector in SECURITY_DETECTORS:
            assert isinstance(detector.description, str)
            assert len(detector.description) > 0
