"""XXE / entity-expansion hardening for the dedup ODT extractor (WP-2.1).

``DocumentExtractor._extract_odt`` parses an untrusted ``content.xml`` pulled
from an ODT (ZIP) file. It now uses ``defusedxml.ElementTree.fromstring`` instead
of the stdlib parser, so internal-entity / external-entity payloads are refused
rather than processed.

Marked ``ci`` so the changed parse line gets diff-coverage credit. Only depends
on defusedxml (a core dependency), not the heavier dedup extras.
"""

from __future__ import annotations

import builtins
import zipfile
from pathlib import Path

import pytest

from file_organizer.services.deduplication.extractor import DocumentExtractor

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
)


def _write_odt(path: Path, content_xml: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.xml", content_xml)


def test_extract_odt_reads_clean_document(tmp_path: Path) -> None:
    """A normal ODT still extracts paragraph text through the defused parser."""
    odt = tmp_path / "clean.odt"
    _write_odt(
        odt,
        f'<?xml version="1.0"?><office:document-content {_NS}>'
        "<office:body><office:text>"
        "<text:p>Hello defused world</text:p>"
        "</office:text></office:body></office:document-content>",
    )
    assert "Hello defused world" in DocumentExtractor()._extract_odt(odt)


def test_extract_odt_refuses_internal_entity_expansion(tmp_path: Path) -> None:
    """An internal-entity payload is refused by defusedxml (EntitiesForbidden,
    a ValueError subclass caught by the reader) — the entity is never expanded.

    defusedxml is a core dependency, so this security regression must fail loudly
    if it's missing/mispackaged rather than silently skipping.
    """
    odt = tmp_path / "evil.odt"
    _write_odt(
        odt,
        '<?xml version="1.0"?>'
        '<!DOCTYPE doc [<!ENTITY pwn "EXPANDED_SECRET">]>'
        f"<office:document-content {_NS}>"
        "<office:body><office:text><text:p>&pwn;</text:p></office:text></office:body>"
        "</office:document-content>",
    )
    result = DocumentExtractor()._extract_odt(odt)
    # defusedxml refuses the entity → no expansion, no crash.
    assert "EXPANDED_SECRET" not in result


def test_extract_odt_handles_malformed_xml(tmp_path: Path) -> None:
    """A malformed ``content.xml`` raises ``ParseError`` (a SyntaxError); it must
    be caught and degrade to "" rather than escaping and crashing the dedup flow.
    """
    odt = tmp_path / "malformed.odt"
    _write_odt(odt, f"<office:document-content {_NS}><office:body><text:p>oops")
    assert DocumentExtractor()._extract_odt(odt) == ""


def test_extract_odt_fails_closed_when_defusedxml_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing ``defusedxml`` must not silently downgrade to stdlib XML."""
    odt = tmp_path / "clean.odt"
    _write_odt(
        odt,
        f'<?xml version="1.0"?><office:document-content {_NS}>'
        "<office:body><office:text>"
        "<text:p>Hello without defusedxml</text:p>"
        "</office:text></office:body></office:document-content>",
    )

    original_import = builtins.__import__

    def fail_defusedxml_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("defusedxml"):
            raise ImportError("defusedxml intentionally unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_defusedxml_import)

    assert DocumentExtractor()._extract_odt(odt) == ""
