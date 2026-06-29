"""Tests for the WP-6.1 defusedxml-fallback CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_defusedxml_fallback as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_stdlib_xml_import(tmp_path: Path) -> None:
    src = tmp_path / "bad.py"
    src.write_text("import xml.etree.ElementTree as ET\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "xml.etree" in violations[0][1]


def test_targeted_noqa_suppresses_violation(tmp_path: Path) -> None:
    src = tmp_path / "exempt.py"
    src.write_text(
        "import xml.etree.ElementTree as ET  # noqa: defusedxml-fallback\n",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "bare.py"
    src.write_text("import xml.etree.ElementTree as ET  # noqa\n", encoding="utf-8")
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "msg = 'noqa: defusedxml-fallback'\nimport xml.etree.ElementTree as ET\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1
