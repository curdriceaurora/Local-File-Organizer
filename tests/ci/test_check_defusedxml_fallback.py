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


def test_flags_alias_import(tmp_path: Path) -> None:
    src = tmp_path / "alias.py"
    src.write_text("import xml.etree.ElementTree as apparently_safe\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "xml.etree.ElementTree" in violations[0][1]


def test_flags_local_stdlib_xml_import(tmp_path: Path) -> None:
    src = tmp_path / "local_import.py"
    src.write_text(
        "def parse(data):\n"
        "    import xml.etree.ElementTree as ET\n"
        "    return ET.fromstring(data)\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) >= 1
    assert "xml.etree.ElementTree" in violations[0][1]


def test_flags_defusedxml_importerror_fallback_to_stdlib_xml(tmp_path: Path) -> None:
    src = tmp_path / "fallback.py"
    src.write_text(
        "try:\n"
        "    from defusedxml import ElementTree as ET\n"
        "except ImportError:\n"
        "    import xml.etree.ElementTree as ET\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert violations[0][0] == 4
    assert "xml.etree.ElementTree" in violations[0][1]


def test_flags_dynamic_importlib_stdlib_xml_import(tmp_path: Path) -> None:
    src = tmp_path / "dynamic_import.py"
    src.write_text(
        "import importlib as imports\nET = imports.import_module('xml.etree.ElementTree')\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "dynamic standard library import 'xml.etree.ElementTree'" in violations[0][1]


def test_flags_aliased_import_module_stdlib_xml_import(tmp_path: Path) -> None:
    src = tmp_path / "dynamic_import_alias.py"
    src.write_text(
        "from importlib import import_module as load_module\n"
        "ET = load_module('xml.etree.ElementTree')\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "dynamic standard library import 'xml.etree.ElementTree'" in violations[0][1]


def test_flags_dunder_import_stdlib_xml_import(tmp_path: Path) -> None:
    src = tmp_path / "dunder_import.py"
    src.write_text("ET = __import__('xml.etree.ElementTree')\n", encoding="utf-8")
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "dynamic standard library import 'xml.etree.ElementTree'" in violations[0][1]


def test_flags_parser_construction_through_resolved_alias(tmp_path: Path) -> None:
    src = tmp_path / "parser_alias.py"
    src.write_text(
        "import importlib\n"
        "ET = importlib.import_module('xml.etree.ElementTree')\n"
        "parser = ET.XMLParser()\n",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 2
    assert "XML parser constructed through alias" in violations[1][1]


def test_allows_defusedxml_import(tmp_path: Path) -> None:
    src = tmp_path / "safe.py"
    src.write_text("from defusedxml import ElementTree as ET\n", encoding="utf-8")
    assert checker.check_file(src) == []


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


def test_unrelated_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "unrelated.py"
    src.write_text(
        "import xml.etree.ElementTree as ET  # noqa: some-other-rail\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "string_literal.py"
    src.write_text(
        "msg = 'noqa: defusedxml-fallback'\nimport xml.etree.ElementTree as ET\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_broad_suppression_text_in_string_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "broad_string.py"
    src.write_text(
        "def reason():\n"
        "    return '# noqa: defusedxml-fallback'\n"
        "import xml.etree.ElementTree as ET\n",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1
