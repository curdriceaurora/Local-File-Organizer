from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.review_regressions import (
    TEMPLATE_JS_DETECTORS,
    TemplateJavaScriptInterpolationDetector,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _write_template(root: Path, rel_path: str, source: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def test_template_js_detector_flags_unsafe_inline_js_variants(tmp_path: Path) -> None:
    detector = TemplateJavaScriptInterpolationDetector()

    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_single_quote.html",
        """<button onclick="openFile('{{ file_name }}')">Open</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_double_quote.html",
        """<button onclick='openFile("{{ file_name }}")'>Open</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_backtick.html",
        """<script>const path = `{{ file_name }}`;</script>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_tojson_in_quotes.html",
        """<button onclick="openFile('{{ file_name|tojson }}')">Open</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_include.html",
        """<button onclick="{% include 'handlers/open_file.html' %}">Open</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_non_path_name.html",
        """<script>const user = {{ display_name }};</script>""",
    )

    findings = detector.find_violations(tmp_path)

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        ("src/file_organizer/web/templates/unsafe_backtick.html", 1, "unsafe-js-interpolation"),
        ("src/file_organizer/web/templates/unsafe_double_quote.html", 1, "unsafe-js-interpolation"),
        ("src/file_organizer/web/templates/unsafe_include.html", 1, "unsafe-js-interpolation"),
        (
            "src/file_organizer/web/templates/unsafe_non_path_name.html",
            1,
            "unsafe-js-interpolation",
        ),
        ("src/file_organizer/web/templates/unsafe_single_quote.html", 1, "unsafe-js-interpolation"),
        (
            "src/file_organizer/web/templates/unsafe_tojson_in_quotes.html",
            1,
            "unsafe-js-interpolation",
        ),
    ]


def test_template_js_detector_allows_safe_tojson_and_data_attribute_patterns(
    tmp_path: Path,
) -> None:
    detector = TemplateJavaScriptInterpolationDetector()

    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/safe_tojson_script.html",
        """<script>const payload = {{ payload|tojson }}; window.render(payload);</script>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/safe_tojson_handler.html",
        """<button onclick="showFile({{ file_name|tojson }})">Open</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/safe_data_attribute.html",
        """<button data-open-path="{{ entry.path }}" onclick="window.desktopOpenPath(this.dataset.openPath)">Reveal</button>""",
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/safe_static_handler.html",
        """<button onclick="window.desktopOpenPath(this.dataset.openPath)">Reveal</button>""",
    )

    assert detector.find_violations(tmp_path) == []


def test_template_js_detector_flags_script_with_nonstandard_closing_tag(
    tmp_path: Path,
) -> None:
    """Detector must catch script blocks closed by browser-accepted non-standard tags."""
    detector = TemplateJavaScriptInterpolationDetector()

    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/nonstandard_close.html",
        "<script>\nconst x = {{ value }};\n</script\t\n bar>",
    )

    findings = detector.find_violations(tmp_path)

    assert [(finding.path, finding.rule_id) for finding in findings] == [
        ("src/file_organizer/web/templates/nonstandard_close.html", "unsafe-js-interpolation"),
    ]


def test_template_js_detector_pack_exports_expected_detector() -> None:
    assert [detector.detector_id for detector in TEMPLATE_JS_DETECTORS] == [
        "template-js.unsafe-inline-interpolation",
    ]


def test_template_js_detector_ignores_inert_script_types(tmp_path: Path) -> None:
    """Detector must not flag inert script containers such as application/json."""
    detector = TemplateJavaScriptInterpolationDetector()

    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/inert_json.html",
        '<script type="application/json">{"key": "{{ value }}"}</script>',
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/inert_ld_json.html",
        '<script type="application/ld+json">{"@context": "{{ value }}"}</script>',
    )
    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/inert_x_template.html",
        '<script type="text/x-template">{{ template_content }}</script>',
    )

    assert detector.find_violations(tmp_path) == []


def test_template_js_detector_still_scans_module_and_text_js_types(tmp_path: Path) -> None:
    """type=module and type=text/javascript must still be scanned."""
    detector = TemplateJavaScriptInterpolationDetector()

    _write_template(
        tmp_path,
        "src/file_organizer/web/templates/unsafe_module.html",
        '<script type="module">const x = {{ value }};</script>',
    )

    findings = detector.find_violations(tmp_path)

    assert [(finding.path, finding.rule_id) for finding in findings] == [
        ("src/file_organizer/web/templates/unsafe_module.html", "unsafe-js-interpolation"),
    ]
