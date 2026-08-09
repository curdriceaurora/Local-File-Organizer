"""Tests for the raw-filesystem-traversal CI rail (issue #1736)."""

from __future__ import annotations

from textwrap import dedent

import pytest

from scripts.ci.guardrails import check_raw_filesystem_traversal as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _find(source: str) -> list[checker.TraversalSite]:
    return checker.find_traversals(dedent(source), path="sample.py")


@pytest.mark.parametrize(
    ("expression", "api"),
    [
        ("root.iterdir()", "Path.iterdir"),
        ("root.glob('*.txt')", "Path.glob"),
        ("root.rglob('*.txt')", "Path.rglob"),
        ("os.walk(root)", "os.walk"),
        ("os.scandir(root)", "os.scandir"),
        ("os.listdir(root)", "os.listdir"),
        ("os.fwalk(root)", "os.fwalk"),
        ("glob.glob('*.txt')", "glob.glob"),
        ("glob.iglob('*.txt')", "glob.iglob"),
    ],
)
def test_detects_supported_raw_traversal_apis(expression: str, api: str) -> None:
    sites = _find(
        f"""
        import glob
        import os

        def scan(root):
            {expression}
        """
    )
    assert [(site.function, site.api) for site in sites] == [("scan", api)]


def test_distinguishes_ast_walk_from_filesystem_walk_in_same_module() -> None:
    sites = _find(
        """
        import ast
        import os

        def inspect(tree, root):
            ast.walk(tree)
            os.walk(root)
        """
    )
    assert [(site.line, site.api) for site in sites] == [(7, "os.walk")]


def test_resolves_import_aliases_and_direct_imports() -> None:
    sites = _find(
        """
        import os as operating_system
        from glob import iglob as iter_matches
        from os import scandir as scan_entries

        def scan(root):
            operating_system.walk(root)
            iter_matches('*.py')
            scan_entries(root)
        """
    )
    assert [site.api for site in sites] == ["os.walk", "glob.iglob", "os.scandir"]


def test_does_not_flag_safedir_scandir_method() -> None:
    sites = _find(
        """
        def scan(safe_dir):
            safe_dir.scandir()
        """
    )
    assert sites == []


def test_records_qualified_class_function() -> None:
    sites = _find(
        """
        class Scanner:
            def scan(self, root):
                return list(root.iterdir())
        """
    )
    assert sites[0].function == "Scanner.scan"


def test_audit_rejects_unexpected_site() -> None:
    site = checker.TraversalSite("new.py", "scan", "Path.rglob", 9)
    unexpected, stale = checker.audit_sites([site], {})
    assert unexpected == [site]
    assert stale == []


def test_audit_rejects_stale_or_changed_exemption_count() -> None:
    key = ("legacy.py", "scan", "Path.glob")
    exemption = checker.TraversalExemption(count=2, reason="app-owned directory")
    site = checker.TraversalSite(*key, line=4)

    unexpected, stale = checker.audit_sites([site], {key: exemption})

    assert unexpected == []
    assert stale == [(key, 2, 1)]


def test_repository_inventory_matches_executable_scope_note() -> None:
    sites = checker.scan_package()
    unexpected, stale = checker.audit_sites(sites, checker._EXEMPTIONS)

    assert unexpected == []
    assert stale == []
    assert len(sites) == 21
    assert sum(exemption.count for exemption in checker._EXEMPTIONS.values()) == 21
