"""Regression tests for SafeDir-routed reads in
``utils/epub_enhanced.py`` (PR3g #282).

Verifies that ``EnhancedEPUBReader.read_epub`` and ``get_epub_metadata``
refuse a symlinked EPUB rather than dereferencing it. The hardening
landed alongside the rail bare-open detection in PR3g; without this
regression, a future refactor that silently reverts to
``epub.read_epub(file_path)`` would only show up in a security audit.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.utils.safedir import SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only"),
]


def _make_minimal_epub(path: Path) -> None:
    """Build a smallest-possible EPUB so ebooklib can parse it.

    Matches the structure used in PR3a's reader tests — just enough to
    pass ebooklib's container/manifest checks.
    """
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            (
                '<?xml version="1.0"?>'
                '<container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                "<rootfiles>"
                '<rootfile full-path="content.opf" '
                'media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>"
            ),
        )
        zf.writestr(
            "content.opf",
            (
                '<?xml version="1.0"?>'
                '<package version="2.0" xmlns="http://www.idpf.org/2007/opf" '
                'unique-identifier="bookid">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:title>Reg Test Book</dc:title>"
                '<dc:identifier id="bookid">test</dc:identifier>'
                "<dc:language>en</dc:language></metadata>"
                '<manifest><item id="ch1" href="ch1.xhtml" '
                'media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="ch1"/></spine></package>'
            ),
        )
        zf.writestr(
            "ch1.xhtml",
            "<html><body><p>regression test chapter</p></body></html>",
        )


class TestEnhancedReaderRefusesSymlink:
    """``EnhancedEPUBReader.read_epub`` must refuse a symlinked EPUB."""

    def test_read_epub_refuses_symlinked_file(self, tmp_path: Path) -> None:
        pytest.importorskip("ebooklib")
        pytest.importorskip("bs4")
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        real = tmp_path / "secret.epub"
        _make_minimal_epub(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.epub").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        reader = EnhancedEPUBReader()
        # The security-specific OSError subclass propagates — callers
        # can distinguish symlink rejection from a malformed EPUB.
        with pytest.raises(SymlinkRejected):
            reader.read_epub(organize / "decoy.epub")

    def test_get_epub_metadata_refuses_symlinked_file(self, tmp_path: Path) -> None:
        pytest.importorskip("ebooklib")
        pytest.importorskip("bs4")
        from file_organizer.utils.epub_enhanced import get_epub_metadata

        real = tmp_path / "real.epub"
        _make_minimal_epub(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "link.epub").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        with pytest.raises(SymlinkRejected):
            get_epub_metadata(organize / "link.epub")

    def test_read_epub_does_not_invoke_path_based_read_on_symlink(self, tmp_path: Path) -> None:
        """Belt-and-suspenders: even if the read fails some other way,
        verify ``epub.read_epub`` is never called with the symlink
        path. Patches the underlying library binding to detect the
        unsafe call.
        """
        pytest.importorskip("ebooklib")
        pytest.importorskip("bs4")
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        real = tmp_path / "real.epub"
        _make_minimal_epub(real)
        organize = tmp_path / "organize"
        organize.mkdir()
        try:
            (organize / "decoy.epub").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")

        reader = EnhancedEPUBReader()
        with patch("file_organizer.utils.epub_enhanced.epub.read_epub") as spy:
            # SymlinkRejected fires before epub.read_epub gets called.
            with pytest.raises(SymlinkRejected):
                reader.read_epub(organize / "decoy.epub")
            # Lock in: epub.read_epub was never invoked with the
            # symlinked path (or anything else).
            assert spy.call_count == 0

    def test_read_epub_still_works_for_real_file(self, tmp_path: Path) -> None:
        """Sanity check: the hardening doesn't break the happy path."""
        pytest.importorskip("ebooklib")
        pytest.importorskip("bs4")
        from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

        target = tmp_path / "book.epub"
        _make_minimal_epub(target)

        reader = EnhancedEPUBReader()
        content = reader.read_epub(target)
        assert content.metadata.title == "Reg Test Book"
