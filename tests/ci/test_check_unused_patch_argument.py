"""Tests for the unused-patch-argument CI rail (issue #1682, epic #1678).

The rail flags test-function parameters injected by ``@patch`` /
``@patch.object`` decorators that are never referenced in the function
body — the copy-paste decay pattern from #1678 (a decorator stack is
copied, the primary assertion updated, and the secondary mocks ignored).

Injection semantics pinned here (verified against unittest.mock):

- ``@patch("t")`` injects; ``@patch("t", sentinel)`` / ``new=...`` do not.
- ``@patch.object(obj, "attr")`` injects; a positional third arg does not.
- ``new_callable=`` and ``autospec=`` still inject.
- Class-level ``@patch`` injects into EVERY ``test_*`` method.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.ci.guardrails import check_unused_patch_argument as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _check(tmp_path: Path, source: str) -> list[tuple[int, str]]:
    src = tmp_path / "test_sample.py"
    src.write_text(dedent(source), encoding="utf-8")
    return checker.check_file(src)


def test_flags_unused_injected_params(tmp_path: Path) -> None:
    """The test_release.py decay pattern: stack copied, extras ignored."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.update_init")
        @patch("mod.update_ver")
        @patch("mod.read_version")
        def test_bump(mock_read, mock_update_ver, mock_update_init):
            mock_read.return_value = "2.0.5"
            assert bump("minor") == "2.1.0"
        """,
    )
    assert len(violations) == 2
    messages = " ".join(msg for _, msg in violations)
    assert "mock_update_ver" in messages
    assert "mock_update_init" in messages
    assert "mock_read" not in messages


def test_no_violation_when_all_params_used(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.update")
        @patch("mod.read_version")
        def test_bump(mock_read, mock_update):
            mock_read.return_value = "2.0.5"
            bump("minor")
            mock_update.assert_called_once()
        """,
    )
    assert violations == []


def test_explicit_new_injects_nothing(tmp_path: Path) -> None:
    """@patch with a positional or keyword `new` injects no parameter."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.CONST", "sentinel")
        @patch("mod.FLAG", new=False)
        def test_consts():
            assert do_thing() == "ok"
        """,
    )
    assert violations == []


def test_mixed_injecting_and_non_injecting_stack(tmp_path: Path) -> None:
    """Only injecting decorators map to trailing params."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        @patch("mod.CONST", "sentinel")
        @patch("mod.reader")
        def test_mixed(mock_reader, mock_helper):
            mock_reader.return_value = "x"
            assert entry() == "x"
        """,
    )
    assert len(violations) == 1
    assert "mock_helper" in violations[0][1]


def test_patch_object_two_arg_injects(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch
        import mod

        @patch.object(mod.Thing, "method")
        def test_thing(mock_method):
            assert mod.entry() == "ok"
        """,
    )
    assert len(violations) == 1
    assert "mock_method" in violations[0][1]


def test_patch_object_with_positional_new_injects_nothing(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch
        import mod

        @patch.object(mod.Thing, "method", lambda self: "stub")
        def test_thing():
            assert mod.entry() == "stub"
        """,
    )
    assert violations == []


def test_new_callable_still_injects(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch, PropertyMock

        @patch("mod.Thing.prop", new_callable=PropertyMock)
        def test_prop(mock_prop):
            assert mod.entry() == "ok"
        """,
    )
    assert len(violations) == 1
    assert "mock_prop" in violations[0][1]


def test_autospec_still_injects(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper", autospec=True)
        def test_helper(mock_helper):
            assert entry() == "ok"
        """,
    )
    assert len(violations) == 1


def test_class_level_patch_injects_into_every_test_method(tmp_path: Path) -> None:
    """Class-level @patch decorates each test_* method and injects its mock."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        class TestThing:
            def test_uses_it(self, mock_helper):
                mock_helper.return_value = "x"
                assert entry() == "x"

            def test_ignores_it(self, mock_helper):
                assert entry() == "x"

            def helper_method(self):
                return 42
        """,
    )
    assert len(violations) == 1
    assert "test_ignores_it" in violations[0][1] or "mock_helper" in violations[0][1]


def test_self_and_cls_are_never_flagged(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        class TestThing:
            @patch("mod.helper")
            def test_method(self, mock_helper):
                mock_helper.assert_not_called()
                assert entry() == "ok"
        """,
    )
    assert violations == []


def test_usage_in_nested_scope_counts(tmp_path: Path) -> None:
    """References inside closures, lambdas, or with-blocks are usage."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        def test_nested(mock_helper):
            def side_effect():
                return mock_helper.call_count
            assert run(side_effect) == 0
        """,
    )
    assert violations == []


def test_usage_as_call_argument_counts(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        def test_passed_on(mock_helper):
            configure(mock_helper)
            assert entry() == "ok"
        """,
    )
    assert violations == []


def test_non_test_functions_are_ignored(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        def _make_harness(mock_helper):
            return "harness"
        """,
    )
    assert violations == []


def test_noqa_suppresses_violation(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        def test_intentional(mock_helper):  # noqa: unused-patch-argument
            assert entry() == "ok"
        """,
    )
    assert violations == []


def test_bare_noqa_does_not_suppress(tmp_path: Path) -> None:
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        @patch("mod.helper")
        def test_intentional(mock_helper):  # noqa
            assert entry() == "ok"
        """,
    )
    assert len(violations) == 1


def test_mocks_map_to_first_params_before_fixtures(tmp_path: Path) -> None:
    """@patch injects into the FIRST free positional slots (after self);
    pytest fixtures are passed by keyword and come after. A test taking
    (mock_x, some_fixture) must flag mock_x, never the fixture."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        class TestThing:
            @patch("mod.helper")
            def test_uses_fixture_only(self, mock_helper, tmp_path):
                assert tmp_path.exists()
        """,
    )
    assert len(violations) == 1
    assert "mock_helper" in violations[0][1]
    assert "tmp_path" not in violations[0][1]


def test_write_only_reassignment_does_not_mask_an_unused_mock(tmp_path: Path) -> None:
    """Rebinding the injected param is not a reference to it.

    ``mock_helper = MagicMock()`` shadows the injection without ever reading
    it, so the patch is still unasserted. Counting Store contexts as
    references let this slip through — a real hole once the rail enforces.
    """
    violations = _check(
        tmp_path,
        """
        from unittest.mock import MagicMock, patch

        class TestThing:
            @patch("mod.helper")
            def test_shadows_the_mock(self, mock_helper):
                mock_helper = MagicMock()
                assert True
        """,
    )
    assert len(violations) == 1
    assert "mock_helper" in violations[0][1]


def test_reading_the_mock_still_counts_as_referenced(tmp_path: Path) -> None:
    """Ordinary use is a Load on the Name, so it must stay clean."""
    violations = _check(
        tmp_path,
        """
        from unittest.mock import patch

        class TestThing:
            @patch("mod.helper")
            def test_asserts_the_mock(self, mock_helper):
                mock_helper.assert_not_called()
        """,
    )
    assert violations == []


def _decorator_of(source: str):
    import ast

    tree = ast.parse(dedent(source))
    return tree.body[0].decorator_list[0]


def test_injects_parameter_semantics_directly() -> None:
    """Pin _injects_parameter itself — signature-level tests can't always
    distinguish an over-counted k (the empty-params fallback masks it)."""
    inj = checker._injects_parameter

    assert inj(_decorator_of('@patch("t")\ndef test_a(): ...'), False) is True
    assert inj(_decorator_of('@patch("t", "explicit")\ndef test_a(): ...'), False) is False
    assert inj(_decorator_of('@patch("t", new=1)\ndef test_a(): ...'), False) is False
    assert inj(_decorator_of('@patch("t", new_callable=X)\ndef test_a(): ...'), False) is True
    assert inj(_decorator_of('@patch("t", autospec=True)\ndef test_a(): ...'), False) is True
    assert inj(_decorator_of('@patch.object(o, "a")\ndef test_a(): ...'), True) is True
    assert inj(_decorator_of('@patch.object(o, "a", stub)\ndef test_a(): ...'), True) is False
    assert inj(_decorator_of('@patch.object(o, "a", new=stub)\ndef test_a(): ...'), True) is False


def test_mock_dot_patch_spelling_is_recognized(tmp_path: Path) -> None:
    """`@mock.patch(...)` and `@unittest.mock.patch(...)` count too."""
    violations = _check(
        tmp_path,
        """
        from unittest import mock
        import unittest.mock

        @mock.patch("mod.a")
        @unittest.mock.patch("mod.b")
        def test_spellings(mock_b, mock_a):
            assert entry() == "ok"
        """,
    )
    assert len(violations) == 2
