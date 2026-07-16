"""Unit tests for the shared web form helpers (issue #1545)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.web._forms import (
    TRUE_FORM_VALUES,
    coerce_bool,
    form_bool,
    update_form_section,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestFormBool:
    def test_truthy_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE", "  Yes  "):
            assert form_bool(value) is True, value

    def test_falsy_values(self) -> None:
        for value in (None, "", "0", "false", "no", "off", "banana"):
            assert form_bool(value) is False, value


class TestCoerceBool:
    def test_bool_passthrough(self) -> None:
        assert coerce_bool(True, default=False) is True
        assert coerce_bool(False, default=True) is False

    def test_string_coercion(self) -> None:
        assert coerce_bool("yes", default=False) is True
        assert coerce_bool("nope", default=True) is False

    def test_non_string_falls_back_to_default(self) -> None:
        assert coerce_bool(1, default=False) is False
        assert coerce_bool(None, default=True) is True
        assert coerce_bool([], default=True) is True


class TestTrueFormValues:
    def test_is_single_canonical_set(self) -> None:
        from file_organizer.web import _helpers

        assert _helpers.TRUE_VALUES is TRUE_FORM_VALUES

    def test_expected_members(self) -> None:
        assert TRUE_FORM_VALUES == {"1", "true", "yes", "on"}


class TestUpdateFormSection:
    def test_success_flow_runs_load_apply_save_render(self) -> None:
        state = {"value": 0}
        calls: list[str] = []
        success_response = MagicMock()

        def apply(s: dict) -> None:
            calls.append("apply")
            s["value"] = 1

        result = update_form_section(
            load=lambda: (calls.append("load"), state)[1],
            apply=apply,
            save=lambda s: calls.append("save"),
            render_success=lambda s: (calls.append("render"), success_response)[1],
            render_error=lambda msg: pytest.fail(f"unexpected error render: {msg}"),
            error_prefix="Failed",
        )

        assert result is success_response
        assert calls == ["load", "apply", "save", "render"]
        assert state["value"] == 1

    @pytest.mark.parametrize("failing_step", ["load", "apply", "save"])
    def test_failure_renders_error_with_prefix(self, failing_step: str) -> None:
        error_response = MagicMock()
        seen: list[str] = []

        def maybe_fail(step: str) -> None:
            if step == failing_step:
                raise RuntimeError("boom")

        result = update_form_section(
            load=lambda: (maybe_fail("load"), {})[1],
            apply=lambda s: maybe_fail("apply"),
            save=lambda s: maybe_fail("save"),
            render_success=lambda s: pytest.fail("success render on failure path"),
            render_error=lambda msg: (seen.append(msg), error_response)[1],
            error_prefix="Failed to save settings",
        )

        assert result is error_response
        assert seen == ["Failed to save settings: boom"]
