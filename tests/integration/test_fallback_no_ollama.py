"""Integration tests for graceful degradation when Ollama is unavailable.

Verifies that FileOrganizer organizes files by extension (fallback mode)
instead of crashing when Ollama cannot be reached.

Run with: pytest -m no_ollama -x -q
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.services.text_processor import ProcessedFile

pytestmark = [pytest.mark.no_ollama, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def source_dir(tmp_path: Path) -> Path:
    """Source directory with one file of each fallback-supported type."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "report.txt").write_text("quarterly earnings", encoding="utf-8")
    (src / "invoice.pdf").write_bytes(b"%PDF-1.4 mock")
    (src / "budget.xlsx").write_bytes(b"PK mock xlsx")
    (src / "slides.pptx").write_bytes(b"PK mock pptx")
    (src / "data.csv").write_text("a,b\n1,2", encoding="utf-8")
    (src / "book.epub").write_bytes(b"PK mock epub")
    (src / "photo.jpg").write_bytes(b"\xff\xd8\xff mock")
    (src / "part.dwg").write_bytes(b"AC1015 mock")
    return src


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Empty output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture()
def organizer() -> FileOrganizer:
    """FileOrganizer in dry-run mode."""
    return FileOrganizer(dry_run=True)


# ---------------------------------------------------------------------------
# Context manager: simulate Ollama being down
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests: fallback does not crash
# ---------------------------------------------------------------------------


class TestFallbackDoesNotCrash:
    """FileOrganizer must complete successfully when Ollama is unreachable."""

    def test_all_files_accounted_for(
        self, organizer: FileOrganizer, source_dir: Path, output_dir: Path
    ) -> None:
        """total_files in result matches files on disk — none silently dropped."""
        expected = len(list(source_dir.iterdir()))
        with (
            patch(
                "file_organizer.services.text_processor.TextProcessor.initialize",
                side_effect=ConnectionRefusedError("down"),
            ),
            patch(
                "file_organizer.services.vision_processor.VisionProcessor.initialize",
                side_effect=ConnectionRefusedError("down"),
            ),
        ):
            result = organizer.organize(source_dir, output_dir)

        assert result.total_files == expected
        assert result.failed_files == 0

    def test_ollama_recovery_between_calls(
        self, organizer: FileOrganizer, source_dir: Path, output_dir: Path
    ) -> None:
        """_ollama_available resets to True on each organize() call.

        A second call after Ollama recovers must not be stuck in fallback mode.
        """
        # First call: Ollama is down
        with (
            patch(
                "file_organizer.services.text_processor.TextProcessor.initialize",
                side_effect=ConnectionRefusedError("down"),
            ),
            patch(
                "file_organizer.services.vision_processor.VisionProcessor.initialize",
                side_effect=ConnectionRefusedError("down"),
            ),
        ):
            organizer.organize(source_dir, output_dir)

        # Flag was set False during first call
        assert organizer._ollama_available is False

        # Second call: Ollama has recovered — patches removed, initialize succeeds
        # We patch initialize to succeed (no-op) and verify the flag resets
        with (
            patch(
                "file_organizer.services.text_processor.TextProcessor.initialize",
                return_value=None,
            ),
            patch(
                "file_organizer.services.vision_processor.VisionProcessor.initialize",
                return_value=None,
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer._process_text_files",
                return_value=[],
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer._process_image_files",
                return_value=[],
            ),
        ):
            organizer.organize(source_dir, output_dir)

        # Flag must be reset True — Ollama is available again
        assert organizer._ollama_available is True


# ---------------------------------------------------------------------------
# Tests: correct folder assignment per extension
# ---------------------------------------------------------------------------


class TestFallbackFolderAssignment:
    """_fallback_by_extension assigns the correct folder for each extension."""

    def _fallback_result(
        self, organizer: FileOrganizer, tmp_path: Path, filename: str
    ) -> ProcessedFile:
        """Create a temp file and run _fallback_by_extension on it."""
        f = tmp_path / filename
        f.write_bytes(b"mock content")
        results = organizer._fallback_by_extension([f])
        assert len(results) == 1
        return results[0]

    def test_pdf_goes_to_pdfs(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "invoice.pdf")
        assert r.folder_name == "PDFs"
        assert r.error is None

    def test_txt_goes_to_documents(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "notes.txt")
        assert r.folder_name == "Documents"

    def test_md_goes_to_documents(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "readme.md")
        assert r.folder_name == "Documents"

    def test_xlsx_goes_to_spreadsheets(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "budget.xlsx")
        assert r.folder_name == "Spreadsheets"

    def test_csv_goes_to_spreadsheets(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "data.csv")
        assert r.folder_name == "Spreadsheets"

    def test_pptx_goes_to_presentations(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "deck.pptx")
        assert r.folder_name == "Presentations"

    def test_epub_goes_to_ebooks(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "book.epub")
        assert r.folder_name == "eBooks"

    def test_dwg_goes_to_cad(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "part.dwg")
        assert r.folder_name == "CAD"

    def test_dxf_goes_to_cad(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        r = self._fallback_result(organizer, tmp_path, "drawing.dxf")
        assert r.folder_name == "CAD"

    def test_result_preserves_original_filename(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """filename field matches the original stem, not a generated name."""
        r = self._fallback_result(organizer, tmp_path, "my-report.pdf")
        assert r.filename == "my-report"

    def test_description_mentions_ollama_unavailable(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """description field communicates why extension fallback was used."""
        r = self._fallback_result(organizer, tmp_path, "doc.txt")
        assert "Ollama unavailable" in r.description


# ---------------------------------------------------------------------------
# Tests: image folder uses mtime year
# ---------------------------------------------------------------------------


class TestFallbackImageYearFolder:
    """Images fallback to Images/<year> derived from mtime."""

    def test_image_folder_contains_year(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff mock")

        results = organizer._fallback_by_extension([img])

        assert len(results) == 1
        folder = results[0].folder_name
        assert folder.startswith("Images/"), f"Expected Images/<year>, got: {folder!r}"
        year_str = folder.split("/")[1]
        assert year_str.isdigit(), f"Expected numeric year, got: {year_str!r}"
        assert 2000 <= int(year_str) <= 2100

    def test_image_folder_unknown_on_stat_failure(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        img = tmp_path / "ghost.jpg"
        img.write_bytes(b"\xff\xd8\xff mock")

        with patch.object(Path, "stat", side_effect=OSError("no access")):
            results = organizer._fallback_by_extension([img])

        assert results[0].folder_name == "Images/Unknown"


# ---------------------------------------------------------------------------
# Tests: fallback map coverage (integrity check)
# ---------------------------------------------------------------------------


class TestFallbackMapCoverage:
    """_TEXT_FALLBACK_MAP must cover all TEXT_EXTENSIONS and CAD_EXTENSIONS."""

    def test_all_text_extensions_mapped(self) -> None:
        missing = FileOrganizer.TEXT_EXTENSIONS - FileOrganizer._TEXT_FALLBACK_MAP.keys()
        assert not missing, (
            f"These TEXT_EXTENSIONS have no fallback folder: {missing}. "
            "Add them to FileOrganizer._TEXT_FALLBACK_MAP."
        )

    def test_all_cad_extensions_mapped(self) -> None:
        missing = FileOrganizer.CAD_EXTENSIONS - FileOrganizer._TEXT_FALLBACK_MAP.keys()
        assert not missing, (
            f"These CAD_EXTENSIONS have no fallback folder: {missing}. "
            "Add them to FileOrganizer._TEXT_FALLBACK_MAP."
        )


# ---------------------------------------------------------------------------
# Tests: health response capabilities
# ---------------------------------------------------------------------------


class TestHealthResponseWhenDegraded:
    """health_check() capabilities dict is accurate when Ollama is down."""

    @pytest.mark.asyncio
    async def test_degraded_capabilities_lists_rule_based_types(self) -> None:
        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        with patch.object(facade, "_check_ollama", new=AsyncMock(return_value=False)):
            health = await facade.health_check()

        assert health["status"] == "degraded"
        caps = health["capabilities"]
        # audio and video always work via metadata
        assert "audio" in caps["rule_based"]
        assert "video" in caps["rule_based"]
        # text and images degrade to extension-based, not broken
        assert "text" in caps["extension_fallback"]
        assert "images" in caps["extension_fallback"]

    @pytest.mark.asyncio
    async def test_ok_status_has_no_capabilities_key(self) -> None:
        from file_organizer.api.service_facade import ServiceFacade

        facade = ServiceFacade()
        with patch.object(facade, "_check_ollama", new=AsyncMock(return_value=True)):
            health = await facade.health_check()

        assert health["status"] == "ok"
        assert "capabilities" not in health, "capabilities key should only appear in degraded state"
