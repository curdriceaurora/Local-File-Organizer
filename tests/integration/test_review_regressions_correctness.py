"""Integration tests for review_regressions/correctness.py."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from file_organizer.review_regressions.correctness import (
    CORRECTNESS_DETECTORS,
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
    _annotation_contains_primitive,
    _call_matches_object_setattr,
    _enclosing_class_name,
    _enclosing_scope,
    _is_active_models_target,
    _is_name_annotation,
    _is_primitive_constant,
    _is_primitive_model_assignment,
    _is_stage_context_annotation,
    _is_stage_context_constructor,
    _iter_correctness_python_files,
    _iter_scope_nodes,
    _parent_map,
    _primitive_like_names,
    _setattr_target_name,
    _stage_context_aliases,
    _stage_context_names,
    _stage_field_name,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# _call_matches_object_setattr
# ---------------------------------------------------------------------------


class TestCallMatchesObjectSetattr:
    def _get_call(self, src: str) -> ast.Call:
        tree = ast.parse(src)
        return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))

    def test_object_setattr_call_matches(self) -> None:
        node = self._get_call("object.__setattr__(ctx, 'category', val)")
        assert _call_matches_object_setattr(node) is True

    def test_other_setattr_call_does_not_match(self) -> None:
        node = self._get_call("something.__setattr__(ctx, 'category', val)")
        assert _call_matches_object_setattr(node) is False

    def test_regular_function_call_does_not_match(self) -> None:
        node = self._get_call("setattr(ctx, 'category', val)")
        assert _call_matches_object_setattr(node) is False

    def test_object_other_method_does_not_match(self) -> None:
        node = self._get_call("object.__getattr__(ctx, 'category')")
        assert _call_matches_object_setattr(node) is False

    def test_non_name_receiver_does_not_match(self) -> None:
        node = self._get_call("get_obj().__setattr__(ctx, 'category', val)")
        assert _call_matches_object_setattr(node) is False


# ---------------------------------------------------------------------------
# _stage_context_aliases
# ---------------------------------------------------------------------------


class TestStageContextAliases:
    def test_direct_import_returns_stage_context(self) -> None:
        src = "from file_organizer.interfaces.pipeline import StageContext"
        tree = ast.parse(src)
        aliases = _stage_context_aliases(tree)
        assert aliases == {"StageContext"}

    def test_aliased_import_returns_alias(self) -> None:
        src = "from file_organizer.interfaces.pipeline import StageContext as SC"
        tree = ast.parse(src)
        aliases = _stage_context_aliases(tree)
        assert aliases == {"SC"}

    def test_no_import_returns_empty(self) -> None:
        tree = ast.parse("import os")
        aliases = _stage_context_aliases(tree)
        assert aliases == set()

    def test_import_from_other_module_not_included(self) -> None:
        src = "from some.other.module import StageContext"
        tree = ast.parse(src)
        aliases = _stage_context_aliases(tree)
        assert aliases == set()

    def test_function_local_import_excluded(self) -> None:
        src = (
            "def f():\n"
            "    from file_organizer.interfaces.pipeline import StageContext as SC\n"
            "    pass\n"
        )
        tree = ast.parse(src)
        aliases = _stage_context_aliases(tree)
        assert "SC" not in aliases
        assert aliases == set()

    def test_multiple_imports_collected(self) -> None:
        src = (
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "from file_organizer.interfaces.pipeline import StageContext as SC\n"
        )
        tree = ast.parse(src)
        aliases = _stage_context_aliases(tree)
        assert "StageContext" in aliases
        assert "SC" in aliases


# ---------------------------------------------------------------------------
# _is_name_annotation
# ---------------------------------------------------------------------------


class TestIsNameAnnotation:
    def test_name_in_set_returns_true(self) -> None:
        node = ast.Name(id="StageContext", ctx=ast.Load())
        assert _is_name_annotation(node, {"StageContext"}) is True

    def test_name_not_in_set_returns_false(self) -> None:
        node = ast.Name(id="SomeOther", ctx=ast.Load())
        assert _is_name_annotation(node, {"StageContext"}) is False

    def test_non_name_node_returns_false(self) -> None:
        node = ast.Constant(value="StageContext")
        assert _is_name_annotation(node, {"StageContext"}) is False

    def test_empty_set_always_returns_false(self) -> None:
        node = ast.Name(id="StageContext", ctx=ast.Load())
        assert _is_name_annotation(node, set()) is False


# ---------------------------------------------------------------------------
# _is_stage_context_annotation
# ---------------------------------------------------------------------------


class TestIsStageContextAnnotation:
    def test_name_node_matching_alias_returns_true(self) -> None:
        node = ast.Name(id="StageContext", ctx=ast.Load())
        assert _is_stage_context_annotation(node, {"StageContext"}) is True

    def test_constant_string_matching_alias_returns_true(self) -> None:
        node = ast.Constant(value="StageContext")
        assert _is_stage_context_annotation(node, {"StageContext"}) is True

    def test_none_node_returns_false(self) -> None:
        assert _is_stage_context_annotation(None, {"StageContext"}) is False

    def test_constant_string_not_in_aliases_returns_false(self) -> None:
        node = ast.Constant(value="OtherContext")
        assert _is_stage_context_annotation(node, {"StageContext"}) is False

    def test_non_matching_name_returns_false(self) -> None:
        node = ast.Name(id="str", ctx=ast.Load())
        assert _is_stage_context_annotation(node, {"StageContext"}) is False

    def test_integer_constant_returns_false(self) -> None:
        node = ast.Constant(value=42)
        assert _is_stage_context_annotation(node, {"StageContext"}) is False


# ---------------------------------------------------------------------------
# _is_stage_context_constructor
# ---------------------------------------------------------------------------


class TestIsStageContextConstructor:
    def test_call_with_matching_name_returns_true(self) -> None:
        src = "StageContext()"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_stage_context_constructor(call, {"StageContext"}) is True

    def test_call_with_non_matching_name_returns_false(self) -> None:
        src = "SomeOther()"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_stage_context_constructor(call, {"StageContext"}) is False

    def test_non_call_node_returns_false(self) -> None:
        node = ast.Name(id="StageContext", ctx=ast.Load())
        assert _is_stage_context_constructor(node, {"StageContext"}) is False

    def test_aliased_constructor_matches(self) -> None:
        src = "SC()"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_stage_context_constructor(call, {"SC"}) is True


# ---------------------------------------------------------------------------
# _stage_context_names
# ---------------------------------------------------------------------------


class TestStageContextNames:
    def test_function_arg_with_annotation_is_collected(self) -> None:
        src = "def f(ctx: StageContext): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _stage_context_names(func, {"StageContext"})
        assert "ctx" in names

    def test_ann_assign_with_annotation_is_collected(self) -> None:
        src = "def f():\n    ctx: StageContext = None\n    pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _stage_context_names(func, {"StageContext"})
        assert "ctx" in names

    def test_assign_from_constructor_is_collected(self) -> None:
        src = "def f():\n    ctx = StageContext()\n    pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _stage_context_names(func, {"StageContext"})
        assert "ctx" in names

    def test_unrelated_arg_not_in_names(self) -> None:
        src = "def f(x: int, ctx: StageContext): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _stage_context_names(func, {"StageContext"})
        assert "x" not in names
        assert "ctx" in names

    def test_empty_aliases_returns_empty_set(self) -> None:
        src = "def f(ctx: StageContext): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _stage_context_names(func, set())
        assert names == set()

    def test_module_scope_ann_assign_collected(self) -> None:
        src = "ctx: StageContext\n"
        tree = ast.parse(src)
        names = _stage_context_names(tree, {"StageContext"})
        assert "ctx" in names


# ---------------------------------------------------------------------------
# _stage_field_name
# ---------------------------------------------------------------------------


class TestStageFieldName:
    def test_second_arg_constant_string_returned(self) -> None:
        src = "object.__setattr__(ctx, 'category', val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _stage_field_name(call) == "category"

    def test_filename_field_returned(self) -> None:
        src = "object.__setattr__(ctx, 'filename', val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _stage_field_name(call) == "filename"

    def test_too_few_args_returns_none(self) -> None:
        src = "object.__setattr__(ctx)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _stage_field_name(call) is None

    def test_non_constant_second_arg_returns_none(self) -> None:
        src = "object.__setattr__(ctx, field_name, val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _stage_field_name(call) is None

    def test_integer_second_arg_returns_none(self) -> None:
        src = "object.__setattr__(ctx, 42, val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _stage_field_name(call) is None


# ---------------------------------------------------------------------------
# _setattr_target_name
# ---------------------------------------------------------------------------


class TestSetattrTargetName:
    def test_name_first_arg_returns_id(self) -> None:
        src = "object.__setattr__(ctx, 'category', val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _setattr_target_name(call) == "ctx"

    def test_no_args_returns_none(self) -> None:
        src = "object.__setattr__()"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _setattr_target_name(call) is None

    def test_non_name_first_arg_returns_none(self) -> None:
        src = "object.__setattr__(get_ctx(), 'category', val)"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _setattr_target_name(call) is None


# ---------------------------------------------------------------------------
# _iter_correctness_python_files
# ---------------------------------------------------------------------------


class TestIterCorrectnessPythonFiles:
    def test_src_subdir_used_when_present(self, tmp_path: Path) -> None:
        subdir = tmp_path / "src" / "file_organizer"
        subdir.mkdir(parents=True)
        (subdir / "module.py").write_text("x = 1\n")
        files = _iter_correctness_python_files(tmp_path)
        file_names = [Path(f).name for f in files]
        assert "module.py" in file_names

    def test_root_used_when_src_subdir_absent(self, tmp_path: Path) -> None:
        (tmp_path / "standalone.py").write_text("x = 1\n")
        files = _iter_correctness_python_files(tmp_path)
        file_names = [Path(f).name for f in files]
        assert "standalone.py" in file_names

    def test_returns_list_for_empty_dir(self, tmp_path: Path) -> None:
        files = _iter_correctness_python_files(tmp_path)
        assert files == []

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        files = _iter_correctness_python_files(tmp_path)
        assert files == []


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

    def test_every_non_root_node_has_parent(self) -> None:
        tree = ast.parse("def f(a):\n    return a + 1")
        parents = _parent_map(tree)
        all_nodes = list(ast.walk(tree))
        for node in all_nodes[1:]:
            assert node in parents


# ---------------------------------------------------------------------------
# _is_active_models_target
# ---------------------------------------------------------------------------


class TestIsActiveModelsTarget:
    def test_self_active_models_subscript_matches(self) -> None:
        src = "self._active_models[key] = val"
        tree = ast.parse(src)
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        assert _is_active_models_target(assign.targets[0]) is True

    def test_other_attr_subscript_does_not_match(self) -> None:
        src = "self._other_dict[key] = val"
        tree = ast.parse(src)
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        assert _is_active_models_target(assign.targets[0]) is False

    def test_non_self_receiver_does_not_match(self) -> None:
        src = "other._active_models[key] = val"
        tree = ast.parse(src)
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        assert _is_active_models_target(assign.targets[0]) is False

    def test_plain_name_does_not_match(self) -> None:
        node = ast.Name(id="_active_models", ctx=ast.Store())
        assert _is_active_models_target(node) is False


# ---------------------------------------------------------------------------
# _annotation_contains_primitive
# ---------------------------------------------------------------------------


class TestAnnotationContainsPrimitive:
    def test_none_returns_false(self) -> None:
        assert _annotation_contains_primitive(None) is False

    def test_str_name_returns_true(self) -> None:
        node = ast.Name(id="str", ctx=ast.Load())
        assert _annotation_contains_primitive(node) is True

    def test_int_name_returns_true(self) -> None:
        node = ast.Name(id="int", ctx=ast.Load())
        assert _annotation_contains_primitive(node) is True

    def test_bool_name_returns_true(self) -> None:
        node = ast.Name(id="bool", ctx=ast.Load())
        assert _annotation_contains_primitive(node) is True

    def test_float_name_returns_true(self) -> None:
        node = ast.Name(id="float", ctx=ast.Load())
        assert _annotation_contains_primitive(node) is True

    def test_custom_type_name_returns_false(self) -> None:
        node = ast.Name(id="MyModel", ctx=ast.Load())
        assert _annotation_contains_primitive(node) is False

    def test_constant_string_str_returns_true(self) -> None:
        node = ast.Constant(value="str")
        assert _annotation_contains_primitive(node) is True

    def test_constant_string_non_primitive_returns_false(self) -> None:
        node = ast.Constant(value="MyModel")
        assert _annotation_contains_primitive(node) is False

    def test_union_with_str_returns_true(self) -> None:
        src = "def f(x: str | None): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        annotation = func.args.args[0].annotation
        assert _annotation_contains_primitive(annotation) is True

    def test_union_without_primitive_returns_false(self) -> None:
        src = "x: MyModel | None"
        tree = ast.parse(src)
        ann_assign = tree.body[0]
        assert isinstance(ann_assign, ast.AnnAssign)
        assert _annotation_contains_primitive(ann_assign.annotation) is False

    def test_subscript_optional_str_returns_true(self) -> None:
        src = "x: Optional[str]"
        tree = ast.parse(src)
        ann_assign = tree.body[0]
        assert isinstance(ann_assign, ast.AnnAssign)
        assert _annotation_contains_primitive(ann_assign.annotation) is True

    def test_subscript_optional_model_returns_false(self) -> None:
        src = "x: Optional[MyModel]"
        tree = ast.parse(src)
        ann_assign = tree.body[0]
        assert isinstance(ann_assign, ast.AnnAssign)
        assert _annotation_contains_primitive(ann_assign.annotation) is False


# ---------------------------------------------------------------------------
# _is_primitive_constant
# ---------------------------------------------------------------------------


class TestIsPrimitiveConstant:
    def test_string_constant_returns_true(self) -> None:
        node = ast.Constant(value="hello")
        assert _is_primitive_constant(node) is True

    def test_int_constant_returns_true(self) -> None:
        node = ast.Constant(value=42)
        assert _is_primitive_constant(node) is True

    def test_float_constant_returns_true(self) -> None:
        node = ast.Constant(value=3.14)
        assert _is_primitive_constant(node) is True

    def test_bool_constant_returns_true(self) -> None:
        node = ast.Constant(value=True)
        assert _is_primitive_constant(node) is True

    def test_none_constant_returns_false(self) -> None:
        node = ast.Constant(value=None)
        assert _is_primitive_constant(node) is False

    def test_name_node_returns_false(self) -> None:
        node = ast.Name(id="x", ctx=ast.Load())
        assert _is_primitive_constant(node) is False


# ---------------------------------------------------------------------------
# _is_primitive_model_assignment
# ---------------------------------------------------------------------------


class TestIsPrimitiveModelAssignment:
    def test_string_constant_is_primitive(self) -> None:
        node = ast.Constant(value="some_string")
        assert _is_primitive_model_assignment(node, set()) is True

    def test_int_constant_is_primitive(self) -> None:
        node = ast.Constant(value=42)
        assert _is_primitive_model_assignment(node, set()) is True

    def test_name_in_primitive_names_is_primitive(self) -> None:
        node = ast.Name(id="my_str", ctx=ast.Load())
        assert _is_primitive_model_assignment(node, {"my_str"}) is True

    def test_name_not_in_primitive_names_is_not_primitive(self) -> None:
        node = ast.Name(id="model_instance", ctx=ast.Load())
        assert _is_primitive_model_assignment(node, set()) is False

    def test_none_constant_is_not_primitive(self) -> None:
        node = ast.Constant(value=None)
        assert _is_primitive_model_assignment(node, set()) is False

    def test_call_node_is_not_primitive(self) -> None:
        src = "SomeModel()"
        tree = ast.parse(src)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_primitive_model_assignment(call, set()) is False


# ---------------------------------------------------------------------------
# _iter_scope_nodes
# ---------------------------------------------------------------------------


class TestIterScopeNodes:
    def test_function_body_nodes_returned(self) -> None:
        src = "def f():\n    x = 1\n    y = 2"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        nodes = list(_iter_scope_nodes(func))
        node_types = {type(n).__name__ for n in nodes}
        assert "Assign" in node_types

    def test_module_body_nodes_returned(self) -> None:
        src = "x = 1\ny = 2"
        tree = ast.parse(src)
        nodes = list(_iter_scope_nodes(tree))
        assigns = [n for n in nodes if isinstance(n, ast.Assign)]
        assert len(assigns) == 2

    def test_does_not_descend_into_nested_function(self) -> None:
        src = "def f():\n    def g():\n        secret = 42\n    x = 1"
        tree = ast.parse(src)
        func = tree.body[0]
        nodes = list(_iter_scope_nodes(func))
        assigns = [n for n in nodes if isinstance(n, ast.Assign)]
        assign_names = [a.targets[0].id for a in assigns if isinstance(a.targets[0], ast.Name)]
        assert "secret" not in assign_names
        assert "x" in assign_names

    def test_non_function_non_module_returns_empty(self) -> None:
        node = ast.ClassDef(
            name="Foo",
            bases=[],
            keywords=[],
            body=[ast.Pass()],
            decorator_list=[],
        )
        result = list(_iter_scope_nodes(node))
        assert result == []

    def test_async_function_body_nodes_returned(self) -> None:
        src = "async def f():\n    x = 1"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.AsyncFunctionDef)
        nodes = list(_iter_scope_nodes(func))
        assert any(isinstance(n, ast.Assign) for n in nodes)


# ---------------------------------------------------------------------------
# _primitive_like_names
# ---------------------------------------------------------------------------


class TestPrimitiveLikeNames:
    def test_annotated_str_arg_is_collected(self) -> None:
        src = "def f(x: str): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _primitive_like_names(func)
        assert "x" in names

    def test_annotated_int_arg_is_collected(self) -> None:
        src = "def f(count: int): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _primitive_like_names(func)
        assert "count" in names

    def test_model_typed_arg_not_collected(self) -> None:
        src = "def f(model: MyModel): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _primitive_like_names(func)
        assert "model" not in names

    def test_local_string_literal_assignment_propagated(self) -> None:
        src = "def f():\n    x = 'hello'\n    y = x"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _primitive_like_names(func)
        assert "x" in names
        assert "y" in names

    def test_empty_function_returns_empty_set(self) -> None:
        src = "def f(): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        names = _primitive_like_names(func)
        assert names == set()


# ---------------------------------------------------------------------------
# _enclosing_scope
# ---------------------------------------------------------------------------


class TestEnclosingScope:
    def test_node_inside_function_returns_function(self) -> None:
        src = "def f():\n    x = 1"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        func = tree.body[0]
        assert isinstance(func, ast.FunctionDef)
        assign = func.body[0]
        scope = _enclosing_scope(assign, parents)
        assert scope is func

    def test_node_at_module_level_returns_module(self) -> None:
        src = "x = 1"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        assign = tree.body[0]
        scope = _enclosing_scope(assign, parents)
        assert scope is tree

    def test_nested_function_returns_outer_function_for_outer_assign(self) -> None:
        src = "def outer():\n    x = 1\n    def inner():\n        y = 2"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        outer = tree.body[0]
        assert isinstance(outer, ast.FunctionDef)
        assign = outer.body[0]
        scope = _enclosing_scope(assign, parents)
        assert scope is outer


# ---------------------------------------------------------------------------
# _enclosing_class_name
# ---------------------------------------------------------------------------


class TestEnclosingClassName:
    def test_node_inside_class_returns_class_name(self) -> None:
        src = "class Foo:\n    def method(self):\n        x = 1"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        class_def = tree.body[0]
        assert isinstance(class_def, ast.ClassDef)
        method = class_def.body[0]
        assert isinstance(method, ast.FunctionDef)
        assign = method.body[0]
        name = _enclosing_class_name(assign, parents)
        assert name == "Foo"

    def test_node_at_module_level_returns_none(self) -> None:
        src = "x = 1"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        assign = tree.body[0]
        name = _enclosing_class_name(assign, parents)
        assert name is None

    def test_method_returns_enclosing_class_name(self) -> None:
        src = "class ModelManager:\n    def load(self):\n        pass"
        tree = ast.parse(src)
        parents = _parent_map(tree)
        class_def = tree.body[0]
        assert isinstance(class_def, ast.ClassDef)
        method = class_def.body[0]
        name = _enclosing_class_name(method, parents)
        assert name == "ModelManager"


# ---------------------------------------------------------------------------
# StageContextValidationBypassDetector.find_violations
# ---------------------------------------------------------------------------


class TestStageContextValidationBypassDetector:
    def _make_src_dir(self, tmp_path: Path) -> Path:
        src_dir = tmp_path / "src" / "file_organizer"
        src_dir.mkdir(parents=True, exist_ok=True)
        return src_dir

    def test_empty_directory_produces_no_violations(self, tmp_path: Path) -> None:
        self._make_src_dir(tmp_path)
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_clean_code_produces_no_violations(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "module.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    ctx.category = 'docs'\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_object_setattr_on_stage_context_produces_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "bypass.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'category', 'docs')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].rule_class == "correctness"
        assert violations[0].detector_id == "correctness.stage-context-validation-bypass"

    def test_violation_message_mentions_field_name(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "bypass.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'filename', 'data.txt')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert "filename" in violations[0].message

    def test_object_setattr_unvalidated_field_produces_no_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "safe.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'some_other_field', 'value')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_object_setattr_on_non_stage_context_var_produces_no_violation(
        self, tmp_path: Path
    ) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "safe.py").write_text(
            "def process(other_obj):\n    object.__setattr__(other_obj, 'category', 'docs')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_violation_has_positive_line_number(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "bypass.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'category', 'docs')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].line is not None
        assert violations[0].line > 0

    def test_violation_rule_id_is_correct(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "bypass.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def process(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'category', 'docs')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].rule_id == "validated-field-setattr-bypass"

    def test_violations_are_sorted(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "a_module.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def f(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'category', 'docs')\n"
        )
        (src_dir / "b_module.py").write_text(
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def g(ctx: StageContext):\n"
            "    object.__setattr__(ctx, 'filename', 'data.txt')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        sort_keys = [v.sort_key() for v in violations]
        assert sort_keys == sorted(sort_keys)

    def test_function_local_import_alias_not_treated_as_stage_context(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "local_import.py").write_text(
            "def process(ctx):\n"
            "    from file_organizer.interfaces.pipeline import StageContext as SC\n"
            "    object.__setattr__(ctx, 'category', 'docs')\n"
        )
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# ActiveModelPrimitiveStoreDetector.find_violations
# ---------------------------------------------------------------------------


class TestActiveModelPrimitiveStoreDetector:
    def _make_src_dir(self, tmp_path: Path) -> Path:
        src_dir = tmp_path / "src" / "file_organizer"
        src_dir.mkdir(parents=True, exist_ok=True)
        return src_dir

    def test_empty_directory_produces_no_violations(self, tmp_path: Path) -> None:
        self._make_src_dir(tmp_path)
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_storing_model_instance_produces_no_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n"
            "    def load(self, key, model):\n"
            "        self._active_models[key] = model\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_storing_string_literal_produces_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n"
            "    def load(self, key):\n"
            "        self._active_models[key] = 'model_name'\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].rule_class == "correctness"
        assert violations[0].detector_id == "correctness.active-model-primitive-store"

    def test_storing_int_literal_produces_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n    def load(self, key):\n        self._active_models[key] = 42\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].rule_id == "primitive-active-model-store"

    def test_violation_message_contains_stored_value(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n"
            "    def load(self, key):\n"
            "        self._active_models[key] = 'bad_value'\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert "'bad_value'" in violations[0].message

    def test_outside_model_manager_class_no_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "other.py").write_text(
            "class OtherClass:\n"
            "    def load(self, key):\n"
            "        self._active_models[key] = 'value'\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_violation_has_positive_line_number(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n"
            "    def load(self, key):\n"
            "        self._active_models[key] = 'bad'\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1
        assert violations[0].line is not None
        assert violations[0].line > 0

    def test_violations_are_sorted(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "a_manager.py").write_text(
            "class ModelManager:\n"
            "    def load_a(self, key):\n"
            "        self._active_models[key] = 'bad_a'\n"
        )
        (src_dir / "b_manager.py").write_text(
            "class ModelManager:\n"
            "    def load_b(self, key):\n"
            "        self._active_models[key] = 'bad_b'\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        sort_keys = [v.sort_key() for v in violations]
        assert sort_keys == sorted(sort_keys)

    def test_propagated_primitive_variable_produces_violation(self, tmp_path: Path) -> None:
        src_dir = self._make_src_dir(tmp_path)
        (src_dir / "manager.py").write_text(
            "class ModelManager:\n"
            "    def load(self, key):\n"
            "        name: str = 'model_name'\n"
            "        self._active_models[key] = name\n"
        )
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# CORRECTNESS_DETECTORS
# ---------------------------------------------------------------------------


class TestCorrectnessDetectors:
    def test_has_at_least_two_detectors(self) -> None:
        assert len(CORRECTNESS_DETECTORS) >= 2

    def test_has_two_detectors(self) -> None:
        assert len(CORRECTNESS_DETECTORS) == 2

    def test_contains_stage_context_detector(self) -> None:
        ids = {d.detector_id for d in CORRECTNESS_DETECTORS}
        assert "correctness.stage-context-validation-bypass" in ids

    def test_contains_active_model_detector(self) -> None:
        ids = {d.detector_id for d in CORRECTNESS_DETECTORS}
        assert "correctness.active-model-primitive-store" in ids

    def test_all_detectors_have_find_violations_callable(self) -> None:
        for detector in CORRECTNESS_DETECTORS:
            assert callable(getattr(detector, "find_violations", None))

    def test_all_detectors_have_rule_class_correctness(self) -> None:
        for detector in CORRECTNESS_DETECTORS:
            assert detector.rule_class == "correctness"

    def test_all_detectors_have_non_empty_description(self) -> None:
        for detector in CORRECTNESS_DETECTORS:
            assert isinstance(detector.description, str)
            assert len(detector.description) > 0

    def test_detector_ids_are_unique(self) -> None:
        ids = [d.detector_id for d in CORRECTNESS_DETECTORS]
        assert len(ids) == len(set(ids))
