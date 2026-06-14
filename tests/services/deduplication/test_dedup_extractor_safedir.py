"""SafeDir symlink hardening for the dedup text extractor (WP-2.1, #1261).

``DocumentExtractor`` now opens every format through ``_open_binary``, which on
POSIX uses ``SafeDir.open_root(parent).open_for_reader(name)`` (``O_NOFOLLOW``),
so a symlinked leaf swapped in between dedup enumeration and extraction is
refused (``SymlinkRejected`` → handled → "") instead of dereferenced.

Marked ``ci`` so the SafeDir read path gets diff-coverage credit; lib-gated
formats use ``importorskip`` (pypdf/striprtf live in the dedup extra, docx in
parsers).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from file_organizer.services.deduplication.extractor import DocumentExtractor

pytestmark = [pytest.mark.unit, pytest.mark.ci]

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")


def _make_symlinked_leaf(tmp_path: Path) -> Path:
    """Create inside/doc.txt as a symlink to outside/secret.txt; skip if unsupported."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("attacker secret")
    inside = tmp_path / "inside"
    inside.mkdir()
    try:
        (inside / "doc.txt").symlink_to(outside / "secret.txt")
    except OSError:
        pytest.skip("symlink creation not supported")
    return inside / "doc.txt"


class TestOpenBinaryFallback:
    def test_falls_back_to_legacy_open_when_safedir_unsupported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When SafeDir raises NotImplementedError, ``_open_binary`` falls back
        to a plain ``open(..., 'rb')`` so extraction still works."""
        import file_organizer.services.deduplication.extractor as ext

        def _raise(*_a: object, **_k: object) -> object:
            raise NotImplementedError

        monkeypatch.setattr(ext.SafeDir, "open_root", _raise)

        p = tmp_path / "legacy.txt"
        p.write_bytes(b"legacy bytes")
        with DocumentExtractor._open_binary(p) as f:
            assert f.read() == b"legacy bytes"


class TestTxtSafeDir:
    def test_reads_real_text_file(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.txt"
        p.write_text("hello dedup safedir")
        assert "hello dedup safedir" in DocumentExtractor().extract_text(p)

    @posix_only
    def test_symlinked_leaf_is_refused(self, tmp_path: Path) -> None:
        victim = _make_symlinked_leaf(tmp_path)
        # SafeDir refuses the symlink (SymlinkRejected → OSError → "");
        # the attacker's target content must not be read.
        assert DocumentExtractor().extract_text(victim) == ""


class TestOdtSafeDir:
    @staticmethod
    def _write_real_odt(path: Path, body: str) -> None:
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(
                "content.xml",
                '<?xml version="1.0"?><office:document-content '
                'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                f"<office:body><text:p>{body}</text:p></office:body></office:document-content>",
            )

    def test_reads_real_odt(self, tmp_path: Path) -> None:
        odt = tmp_path / "real.odt"
        self._write_real_odt(odt, "odt safedir body")
        assert "odt safedir body" in DocumentExtractor()._extract_odt(odt)

    @posix_only
    def test_symlinked_odt_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        real_odt = outside / "real.odt"
        with zipfile.ZipFile(real_odt, "w") as z:
            z.writestr(
                "content.xml",
                '<?xml version="1.0"?><office:document-content '
                'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                "<office:body><text:p>secret</text:p></office:body></office:document-content>",
            )
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.odt").symlink_to(real_odt)
        except OSError:
            pytest.skip("symlink creation not supported")
        assert DocumentExtractor()._extract_odt(inside / "doc.odt") == ""


class TestDocxSafeDir:
    def test_reads_real_docx(self, tmp_path: Path) -> None:
        docx = pytest.importorskip("docx")
        p = tmp_path / "doc.docx"
        doc = docx.Document()
        doc.add_paragraph("docx safedir body")
        doc.save(str(p))
        assert "docx safedir body" in DocumentExtractor()._extract_docx(p)

    @posix_only
    def test_symlinked_docx_is_refused(self, tmp_path: Path) -> None:
        docx = pytest.importorskip("docx")
        outside = tmp_path / "outside"
        outside.mkdir()
        real = outside / "real.docx"
        doc = docx.Document()
        doc.add_paragraph("attacker docx")
        doc.save(str(real))
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.docx").symlink_to(real)
        except OSError:
            pytest.skip("symlink creation not supported")
        assert DocumentExtractor()._extract_docx(inside / "doc.docx") == ""


class TestPdfSafeDir:
    @posix_only
    def test_symlinked_pdf_is_refused(self, tmp_path: Path) -> None:
        pytest.importorskip("pypdf")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "real.pdf").write_bytes(b"%PDF-1.4 minimal")
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.pdf").symlink_to(outside / "real.pdf")
        except OSError:
            pytest.skip("symlink creation not supported")
        # SafeDir refuses the symlink before pypdf ever opens it.
        assert DocumentExtractor()._extract_pdf(inside / "doc.pdf") == ""


class TestRtfSafeDir:
    def test_reads_real_rtf(self, tmp_path: Path) -> None:
        pytest.importorskip("striprtf")
        p = tmp_path / "doc.rtf"
        p.write_text(r"{\rtf1\ansi rtf safedir body}")
        assert "rtf safedir body" in DocumentExtractor()._extract_rtf(p)

    @posix_only
    def test_symlinked_rtf_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "real.rtf").write_text(r"{\rtf1\ansi attacker rtf}")
        inside = tmp_path / "inside"
        inside.mkdir()
        try:
            (inside / "doc.rtf").symlink_to(outside / "real.rtf")
        except OSError:
            pytest.skip("symlink creation not supported")
        # SafeDir refuses the symlinked leaf before any RTF parsing.
        assert DocumentExtractor()._extract_rtf(inside / "doc.rtf") == ""
