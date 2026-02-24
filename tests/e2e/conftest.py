"""E2E test fixtures: complex nested folder tree + mock AI processors.

The ``complex_file_tree`` fixture builds a realistic ~60-file tree in a
temporary directory.  It is session-scoped so benchmarks can reuse the same
tree across multiple test functions without rebuilding it each time.

File sourcing strategy
----------------------
- **Real committed samples** in ``tests/fixtures/e2e_samples/`` (DOCX, XLSX,
  JPG, PNG, WAV) for authentic binary format validity.
- **Minimal magic-byte stubs** for PDF / MP3 / MP4 / AVI (format validity is
  not critical for the organizer logic under test).
- **``faker``-generated text** (deterministic with ``Faker.seed(42)``) for all
  ``.txt``, ``.md``, and ``.csv`` content.

Processor routing in FileOrganizer
-----------------------------------
- Text/document files  → ``TextProcessor``  (mocked here)
- Image files          → ``VisionProcessor`` (mocked here)
- Audio files          → ``_process_audio_files`` — metadata-only, no AI model
- Video files          → ``_process_video_files`` — metadata-only, no AI model

Audio and video files will fail metadata extraction on stub content and fall
back to "Audio/Unsorted" / "Video/Unsorted" respectively.  This is expected
and does not require additional mocks.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from faker import Faker

from file_organizer.services import ProcessedFile

# ---------------------------------------------------------------------------
# Seeded Faker for deterministic content generation
# ---------------------------------------------------------------------------
Faker.seed(42)
_fake = Faker()

# ---------------------------------------------------------------------------
# Sample binary files committed to the repo
# ---------------------------------------------------------------------------
_SAMPLES_DIR = Path(__file__).parent.parent / "fixtures" / "e2e_samples"

# ---------------------------------------------------------------------------
# Minimal magic-byte stubs for types where exact format validity is not needed
# ---------------------------------------------------------------------------
_PDF_STUB = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n%%EOF"
_MP3_STUB = b"ID3\x03\x00\x00\x00\x00\x00\x00"
_MP4_STUB = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"
_AVI_STUB = b"RIFF\x00\x00\x00\x00AVI "


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_text(path: Path, content: str | None = None) -> None:
    """Write a text file, generating faker content if none provided."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or _fake.text(max_nb_chars=200), encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    """Write a binary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _copy_sample(name: str, dest: Path) -> None:
    """Copy a committed sample file to *dest*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_SAMPLES_DIR / name, dest)


def _csv_content(rows: int = 5) -> str:
    """Generate a simple CSV string with faker data."""
    header = "name,value,date"
    lines = [header]
    for _ in range(rows):
        lines.append(f"{_fake.name()},{_fake.random_int(1, 10000)},{_fake.date()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Complex file tree fixture (~60 files, 15+ dirs, 3-4 levels deep)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def complex_file_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a realistic ~60-file nested folder tree.

    Session-scoped so benchmark tests can reuse the same tree without
    rebuilding it for each test function.

    Approximate structure (61 files across 16 leaf directories):
        complex_tree/
        ├── Root           (5 files)
        ├── Work/
        │   ├── Projects/2024   (7 files)
        │   ├── Projects/2023   (4 files)
        │   ├── Finance         (5 files)
        │   ├── Reports         (5 files)
        │   └── Clients         (3 files)
        ├── Personal/
        │   ├── Finance         (5 files)
        │   ├── Health          (4 files)
        │   └── Travel          (5 files)
        ├── Media/
        │   ├── Photos          (5 files)
        │   ├── Audio           (3 files)
        │   └── Video           (3 files)
        └── Archive/
            ├── 2022            (3 files)
            └── Misc            (3 files)
    """
    root = tmp_path_factory.mktemp("e2e_tree")

    # -- Root level (5 files) ------------------------------------------------
    _write_text(root / "document.txt")
    _write_text(root / "readme.md", "# Project Readme\n\n" + _fake.paragraph())
    _copy_sample("sample.xlsx", root / "budget_draft.xlsx")
    _copy_sample("sample.docx", root / "project_plan.docx")
    _write_text(root / "changelog.txt", _fake.text(max_nb_chars=300))

    # -- Work/ ---------------------------------------------------------------
    work = root / "Work"

    # Work/Projects/2024/ (7 files)
    p2024 = work / "Projects" / "2024"
    _copy_sample("sample.docx", p2024 / "spec_v1.docx")
    _copy_sample("sample.docx", p2024 / "spec_v2.docx")
    _write_text(p2024 / "architecture.md", "# Architecture\n\n" + _fake.paragraph(nb_sentences=4))
    _write_text(p2024 / "data_export.csv", _csv_content())
    _write_text(p2024 / "meeting_notes.txt", _fake.text(max_nb_chars=400))
    _write_text(p2024 / "timeline.md", "# Timeline\n\n" + _fake.text(max_nb_chars=200))
    _copy_sample("sample.xlsx", p2024 / "budget.xlsx")

    # Work/Projects/2023/ (4 files)
    p2023 = work / "Projects" / "2023"
    _write_bytes(p2023 / "old_spec.pdf", _PDF_STUB)
    _write_text(p2023 / "notes.txt")
    _copy_sample("sample.docx", p2023 / "report.docx")
    _write_text(p2023 / "data.csv", _csv_content(rows=3))

    # Work/Finance/ (5 files)
    wfin = work / "Finance"
    _write_bytes(wfin / "invoice_001.pdf", _PDF_STUB)
    _write_bytes(wfin / "invoice_002.pdf", _PDF_STUB)
    _write_text(wfin / "expenses_q1.csv", _csv_content())
    _write_text(wfin / "expenses_q2.csv", _csv_content())
    _write_bytes(wfin / "report_summary.pdf", _PDF_STUB)

    # Work/Reports/ (5 files)
    wrep = work / "Reports"
    _copy_sample("sample.docx", wrep / "Q1_summary.docx")
    _copy_sample("sample.docx", wrep / "Q2_summary.docx")
    _copy_sample("sample.docx", wrep / "Q3_summary.docx")
    _copy_sample("sample.docx", wrep / "Q4_summary.docx")
    _write_bytes(wrep / "annual_review.pdf", _PDF_STUB)

    # Work/Clients/ (3 files)
    wclients = work / "Clients"
    _write_text(wclients / "client_a_notes.txt", _fake.text(max_nb_chars=300))
    _write_bytes(wclients / "contract_draft.pdf", _PDF_STUB)
    _copy_sample("sample.docx", wclients / "proposal.docx")

    # -- Personal/ ------------------------------------------------------------
    personal = root / "Personal"

    # Personal/Finance/ (5 files)
    pfin = personal / "Finance"
    _write_bytes(pfin / "tax_2023.pdf", _PDF_STUB)
    _write_bytes(pfin / "tax_2024.pdf", _PDF_STUB)
    _copy_sample("sample.xlsx", pfin / "budget.xlsx")
    _write_text(pfin / "receipts.csv", _csv_content(rows=3))
    _write_bytes(pfin / "savings_plan.pdf", _PDF_STUB)

    # Personal/Health/ (4 files)
    phealth = personal / "Health"
    _write_bytes(phealth / "medical_record.pdf", _PDF_STUB)
    _write_text(phealth / "fitness_log.csv", _csv_content())
    _write_bytes(phealth / "prescriptions.pdf", _PDF_STUB)
    _write_bytes(phealth / "insurance.pdf", _PDF_STUB)

    # Personal/Travel/ (5 files)
    ptravel = personal / "Travel"
    _write_text(ptravel / "itinerary_paris.txt", _fake.text(max_nb_chars=400))
    _write_bytes(ptravel / "hotel_booking.pdf", _PDF_STUB)
    _write_text(ptravel / "packing_list.md", "# Packing List\n\n" + _fake.text(max_nb_chars=200))
    _write_text(ptravel / "photo_notes.md", "# Photo Notes\n\n" + _fake.paragraph())
    _write_bytes(ptravel / "booking_london.pdf", _PDF_STUB)

    # -- Media/ ---------------------------------------------------------------
    media = root / "Media"

    # Media/Photos/ (5 files)
    photos = media / "Photos"
    _copy_sample("sample.jpg", photos / "vacation_001.jpg")
    _copy_sample("sample.jpg", photos / "vacation_002.jpg")
    _copy_sample("sample.png", photos / "portrait.png")
    _copy_sample("sample.jpg", photos / "birthday.jpg")
    _copy_sample("sample.png", photos / "sunset.png")

    # Media/Audio/ (3 files) — processed via metadata pipeline, no AI mock needed
    audio = media / "Audio"
    _write_bytes(audio / "recording_001.mp3", _MP3_STUB)
    _copy_sample("sample.wav", audio / "voice_note.wav")
    _write_bytes(audio / "podcast_ep01.mp3", _MP3_STUB)

    # Media/Video/ (3 files) — processed via metadata pipeline, no AI mock needed
    video = media / "Video"
    _write_bytes(video / "demo_recording.mp4", _MP4_STUB)
    _write_bytes(video / "tutorial.avi", _AVI_STUB)
    _write_bytes(video / "review_clip.mp4", _MP4_STUB)

    # -- Archive/ -------------------------------------------------------------
    archive = root / "Archive"

    # Archive/2022/ (3 files)
    a2022 = archive / "2022"
    _write_text(a2022 / "archived_docs.txt")
    _write_text(a2022 / "old_notes.csv", _csv_content(rows=3))
    _write_bytes(a2022 / "summary_2022.pdf", _PDF_STUB)

    # Archive/Misc/ (3 files)
    amisc = archive / "Misc"
    _write_text(amisc / "random_file.txt")
    _write_text(amisc / "backup.csv", _csv_content(rows=3))
    _write_text(amisc / "temp_notes.md", "# Temp Notes\n\n" + _fake.paragraph())

    return root


# ---------------------------------------------------------------------------
# Mock AI processor fixtures
# ---------------------------------------------------------------------------

def _make_mock_process_file(
    folder_map: dict[str, str],
) -> Callable[[Path], ProcessedFile]:
    """Return a deterministic ``process_file`` side_effect for a given extension→folder map."""

    def _process_file(file_path: Path) -> ProcessedFile:
        ext = file_path.suffix.lower()
        folder = folder_map.get(ext, "general")
        return ProcessedFile(
            file_path=file_path,
            description=f"Mock description for {file_path.name}",
            folder_name=folder,
            filename=file_path.stem,
        )

    return _process_file


_TEXT_FOLDER_MAP: dict[str, str] = {
    ".txt": "documents",
    ".md": "documents",
    ".pdf": "documents",
    ".docx": "documents",
    ".doc": "documents",
    ".csv": "spreadsheets",
    ".xlsx": "spreadsheets",
    ".xls": "spreadsheets",
}

# Images only — audio/video bypass VisionProcessor and use metadata-only pipelines.
_IMAGE_FOLDER_MAP: dict[str, str] = {
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".gif": "images",
    ".bmp": "images",
    ".tiff": "images",
}


@pytest.fixture
def mock_text_processor() -> Generator[MagicMock, None, None]:
    """Patch TextProcessor so no Ollama is required."""
    with patch("file_organizer.core.organizer.TextProcessor") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.process_file.side_effect = _make_mock_process_file(_TEXT_FOLDER_MAP)
        yield mock_instance


@pytest.fixture
def mock_vision_processor() -> Generator[MagicMock, None, None]:
    """Patch VisionProcessor so no Ollama is required.

    Note: only image extensions are mapped here.  Audio and video files are
    routed through ``_process_audio_files`` / ``_process_video_files`` in the
    organizer, which use metadata-only pipelines and never call this mock.
    """
    with patch("file_organizer.core.organizer.VisionProcessor") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.process_file.side_effect = _make_mock_process_file(_IMAGE_FOLDER_MAP)
        yield mock_instance
