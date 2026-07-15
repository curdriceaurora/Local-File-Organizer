"""Candidate coverage-gap tests for review_regressions.correctness.

These target branches that the existing ``test_correctness_detectors.py``
does not exercise:

- ``_annotation_contains_primitive`` — the union (``int | None``), subscript
  (``list[int]``), tuple, and forward-reference-string recursion branches.
  The current suite only reaches the bare-``ast.Name`` path via fixtures.
- ``_primitive_like_names`` — the transitive fix-point (a primitive flows
  through an intermediate local before landing in ``_active_models``).
- ``_is_stage_context_annotation`` — the forward-ref *string* annotation
  returning ``True`` (existing predicate tests only cover the ``False`` cases).
- ``ActiveModelPrimitiveStoreDetector`` — the ``_enclosing_class_name !=
  "ModelManager"`` guard (a primitive stored into ``_active_models`` outside
  ModelManager must NOT be flagged).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from file_organizer.review_regressions.correctness import (
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
    _annotation_contains_primitive,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _ann(expr: str) -> ast.AST:
    """Parse a type-annotation expression into its AST node."""
    return ast.parse(expr, mode="eval").body


def _write_module(root: Path, rel_path: str, source: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


# ── _annotation_contains_primitive: recursion branches ───────────────────────


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("int | None", True),  # BinOp/BitOr, primitive on the left
        ("None | str", True),  # BinOp/BitOr, primitive on the right
        ("Foo | Bar", False),  # BinOp/BitOr, neither side primitive
        ("list[int]", True),  # Subscript recurses into the element type
        ("list[Foo]", False),  # Subscript with a non-primitive element
        ("tuple[Foo, int]", True),  # Subscript -> Tuple, any() short-circuits True
        ("dict[str, Foo]", True),  # primitive appears as a Tuple element (key type)
        ("'int'", True),  # forward-ref string that names a primitive
        ("'Foo'", False),  # forward-ref string that names a model
        ("Foo", False),  # bare non-primitive Name
    ],
)
def test_annotation_contains_primitive_recursion(annotation: str, expected: bool) -> None:
    assert _annotation_contains_primitive(_ann(annotation)) is expected


def test_annotation_contains_primitive_none_returns_false() -> None:
    """A missing annotation (``None``) is not primitive-like."""
    assert _annotation_contains_primitive(None) is False


# ── ActiveModelPrimitiveStoreDetector: transitive primitive fix-point ─────────


def test_active_model_detector_flags_transitive_primitive(tmp_path: Path) -> None:
    """A primitive that reaches ``_active_models`` through an intermediate
    local must still be flagged — exercises the ``while changed`` fix-point in
    ``_primitive_like_names`` (two levels of indirection).
    """
    detector = ActiveModelPrimitiveStoreDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/models/mm_transitive.py",
        (
            "class ModelManager:\n"
            "    def load(self, key) -> None:\n"
            "        x = 1\n"
            "        y = x\n"  # y transitively primitive via x
            "        self._active_models[key] = y\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert [(f.path, f.line, f.rule_id) for f in findings] == [
        ("src/file_organizer/models/mm_transitive.py", 5, "primitive-active-model-store"),
    ]


def test_active_model_detector_ignores_non_model_manager_class(tmp_path: Path) -> None:
    """The same primitive store outside a ``ModelManager`` class must NOT be
    flagged — exercises the ``_enclosing_class_name != 'ModelManager'`` guard.
    """
    detector = ActiveModelPrimitiveStoreDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/models/not_model_manager.py",
        (
            "class SomethingElse:\n"
            "    def load(self, key) -> None:\n"
            "        self._active_models[key] = 1\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == []


# ── StageContextValidationBypassDetector: forward-ref annotation (True path) ──


def test_stage_context_detector_flags_forward_ref_annotation(tmp_path: Path) -> None:
    """A ``ctx: 'StageContext'`` forward-reference annotation is still a
    StageContext binding — the ``__setattr__`` bypass on it must be flagged.
    Exercises the ``ast.Constant`` (string) branch of
    ``_is_stage_context_annotation`` returning True.
    """
    detector = StageContextValidationBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/pipeline/forward_ref.py",
        (
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def f(ctx: 'StageContext') -> None:\n"
            "    object.__setattr__(ctx, 'category', 'x')\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert [(f.line, f.rule_id) for f in findings] == [(3, "validated-field-setattr-bypass")]
