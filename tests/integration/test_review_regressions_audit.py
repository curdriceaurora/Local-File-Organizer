"""Integration tests for review_regressions/audit.py.

Covers:
- _is_detector: type rejection, missing find_violations, empty string attrs, valid instance
- _coerce_detectors: single detector, iterable of detectors, mixed iterable raises TypeError,
  non-iterable raises TypeError
- load_detectors: invalid spec (no colon, empty module, empty attr), module not found,
  attribute not found, success via class factory, success via instance
- build_parser: argument structure
- main: no detectors returns 0, --fail-on-findings with no findings returns 0
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_detector(
    detector_id: str = "test.detector",
    rule_class: str = "T1",
    description: str = "A test detector",
) -> MagicMock:
    """Build a mock object that satisfies the detector protocol."""
    d = MagicMock(spec=[])
    d.detector_id = detector_id
    d.rule_class = rule_class
    d.description = description
    d.find_violations = MagicMock(return_value=[])
    return d


# ---------------------------------------------------------------------------
# _is_detector
# ---------------------------------------------------------------------------


class TestIsDetector:
    def test_returns_false_for_class(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        class Fake:
            detector_id = "x"
            rule_class = "R"
            description = "d"

            def find_violations(self, _root: Path):  # type: ignore[override]
                return []

        assert _is_detector(Fake) is False

    def test_returns_false_when_no_find_violations(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        obj = SimpleNamespace(detector_id="x", rule_class="R", description="d")
        assert _is_detector(obj) is False

    def test_returns_false_when_find_violations_not_callable(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        obj = SimpleNamespace(
            detector_id="x", rule_class="R", description="d", find_violations="bad"
        )
        assert _is_detector(obj) is False

    def test_returns_false_when_detector_id_empty(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        d = _make_detector(detector_id="")
        assert _is_detector(d) is False

    def test_returns_false_when_rule_class_empty(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        d = _make_detector(rule_class="")
        assert _is_detector(d) is False

    def test_returns_false_when_description_empty(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        d = _make_detector(description="")
        assert _is_detector(d) is False

    def test_returns_false_when_detector_id_not_string(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        d = _make_detector()
        d.detector_id = 123  # type: ignore[assignment]
        assert _is_detector(d) is False

    def test_returns_true_for_valid_detector(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        assert _is_detector(_make_detector()) is True

    def test_returns_false_for_none(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        assert _is_detector(None) is False

    def test_returns_false_for_plain_string(self) -> None:
        from file_organizer.review_regressions.audit import _is_detector

        assert _is_detector("not_a_detector") is False


# ---------------------------------------------------------------------------
# _coerce_detectors
# ---------------------------------------------------------------------------


class TestCoerceDetectors:
    def test_single_detector_returns_list_of_one(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        d = _make_detector()
        result = _coerce_detectors(d)
        assert result == [d]

    def test_list_of_detectors(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        d1 = _make_detector(detector_id="a.b")
        d2 = _make_detector(detector_id="c.d")
        result = _coerce_detectors([d1, d2])
        assert result == [d1, d2]

    def test_empty_iterable_returns_empty(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        result = _coerce_detectors([])
        assert result == []

    def test_mixed_iterable_raises_type_error(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        d = _make_detector()
        with pytest.raises(TypeError):
            _coerce_detectors([d, "not_a_detector"])

    def test_non_iterable_non_detector_raises_type_error(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        with pytest.raises(TypeError):
            _coerce_detectors(42)

    def test_string_raises_type_error(self) -> None:
        from file_organizer.review_regressions.audit import _coerce_detectors

        with pytest.raises(TypeError):
            _coerce_detectors("module:attr")


# ---------------------------------------------------------------------------
# load_detectors
# ---------------------------------------------------------------------------


class TestLoadDetectors:
    def test_invalid_spec_no_colon_raises_value_error(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        with pytest.raises(ValueError, match="Invalid detector spec"):
            load_detectors(["no_colon_here"])

    def test_invalid_spec_empty_module_raises_value_error(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        with pytest.raises(ValueError, match="Invalid detector spec"):
            load_detectors([":attr"])

    def test_invalid_spec_empty_attr_raises_value_error(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        with pytest.raises(ValueError, match="Invalid detector spec"):
            load_detectors(["module:"])

    def test_module_not_found_raises_value_error(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        with pytest.raises(ValueError, match="Invalid detector spec"):
            load_detectors(["file_organizer.does_not_exist_xyzzy:attr"])

    def test_attribute_not_found_raises_value_error(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        with pytest.raises(ValueError, match="Invalid detector spec"):
            load_detectors(["file_organizer.review_regressions.audit:_does_not_exist_xyzzy"])

    def test_empty_spec_list_returns_empty(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        assert load_detectors([]) == []

    def test_load_via_class_factory(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        detectors = load_detectors(
            ["file_organizer.review_regressions.test_quality:WeakMockCallCountAssertionDetector"]
        )
        assert len(detectors) == 1
        assert detectors[0].detector_id == "test-quality.weak-mock-call-count-lower-bound"

    def test_load_multiple_specs(self) -> None:
        from file_organizer.review_regressions.audit import load_detectors

        spec = "file_organizer.review_regressions.test_quality:WeakMockCallCountAssertionDetector"
        detectors = load_detectors([spec, spec])
        assert len(detectors) == 2

    def test_load_existing_instance_attribute(self) -> None:
        """load_detectors can also load a pre-built instance attribute."""
        import file_organizer.review_regressions.test_quality as tq
        from file_organizer.review_regressions.audit import _is_detector, load_detectors

        instance = tq.WeakMockCallCountAssertionDetector()
        module_mock = MagicMock()
        module_mock.my_detector = instance

        with patch("importlib.import_module", return_value=module_mock):
            detectors = load_detectors(["fake_module:my_detector"])
        assert len(detectors) == 1
        assert _is_detector(detectors[0]) is True


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_returns_argument_parser(self) -> None:
        import argparse

        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_has_root_argument(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.root == "."

    def test_root_accepts_custom_value(self, tmp_path: Path) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args(["--root", str(tmp_path)])
        assert args.root == str(tmp_path)

    def test_has_detector_argument(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args(["--detector", "a:b", "--detector", "c:d"])
        assert args.detectors == ["a:b", "c:d"]

    def test_detector_defaults_to_empty_list(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.detectors == []

    def test_has_fail_on_findings_flag(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args(["--fail-on-findings"])
        assert args.fail_on_findings is True

    def test_fail_on_findings_default_false(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.fail_on_findings is False

    def test_has_compact_flag(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args(["--compact"])
        assert args.compact is True

    def test_compact_default_false(self) -> None:
        from file_organizer.review_regressions.audit import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.compact is False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_no_detectors_returns_zero(self, tmp_path: Path) -> None:
        from file_organizer.review_regressions.audit import main

        result = main(["--root", str(tmp_path)])
        assert result == 0

    def test_main_returns_zero_when_no_findings(self, tmp_path: Path) -> None:
        from file_organizer.review_regressions.audit import main

        result = main(["--root", str(tmp_path), "--fail-on-findings"])
        assert result == 0

    def test_main_compact_flag_emits_json(self, tmp_path: Path, capsys) -> None:
        from file_organizer.review_regressions.audit import main

        main(["--root", str(tmp_path), "--compact"])
        out = capsys.readouterr().out
        import json

        parsed = json.loads(out)
        assert isinstance(parsed, dict)
        assert "\n" not in out.strip()  # compact = single line

    def test_main_indented_json_by_default(self, tmp_path: Path, capsys) -> None:
        from file_organizer.review_regressions.audit import main

        main(["--root", str(tmp_path)])
        out = capsys.readouterr().out
        import json

        parsed = json.loads(out)
        assert isinstance(parsed, dict)
        assert "\n" in out

    def test_main_with_real_detector_no_findings(self, tmp_path: Path) -> None:
        from file_organizer.review_regressions.audit import main

        spec = "file_organizer.review_regressions.test_quality:WeakMockCallCountAssertionDetector"
        result = main(["--root", str(tmp_path), "--detector", spec])
        assert result == 0

    def test_main_returns_one_when_findings_and_fail_on_findings(self, tmp_path: Path) -> None:
        from file_organizer.review_regressions.audit import main
        from file_organizer.review_regressions.framework import AuditReport, Violation

        mock_finding = MagicMock(spec=Violation)
        mock_report = MagicMock(spec=AuditReport)
        mock_report.findings = [mock_finding]

        with patch("file_organizer.review_regressions.audit.run_audit", return_value=mock_report):
            with patch(
                "file_organizer.review_regressions.audit.render_report_json", return_value="{}"
            ):
                result = main(["--root", str(tmp_path), "--fail-on-findings"])
        assert result == 1
