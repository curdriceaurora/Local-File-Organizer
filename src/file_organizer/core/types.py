"""Shared type definitions for the file organizer core.

Contains the ``OrganizationResult`` dataclass and extension-set constants
used across core modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrganizationResult:
    """Result of organizing files.

    Attributes:
        total_files: Total number of files found
        processed_files: Number of files successfully processed
        skipped_files: Number of files skipped (unsupported types)
        failed_files: Number of files that failed processing
        deduplicated_files: Number of duplicate files removed by content-hash dedup
        processing_time: Total time taken in seconds
        organized_structure: Dictionary mapping folder names to file lists
        errors: List of (file_path, error_message) tuples

    Invariant:
        processed_files + skipped_files + failed_files + deduplicated_files == total_files
    """

    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    deduplicated_files: int = 0
    processing_time: float = 0.0
    organized_structure: dict[str, list[str]] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (file, error)


# ---------------------------------------------------------------------------
# Extension constants
# ---------------------------------------------------------------------------

TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".docx",
        ".doc",
        ".pdf",
        ".csv",
        ".xlsx",
        ".xls",
        ".ppt",
        ".pptx",
        ".epub",
    }
)
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
    }
)
VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
    }
)
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".flac",
        ".m4a",
        ".ogg",
    }
)
CAD_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".dwg",
        ".dxf",
        ".step",
        ".stp",
        ".iges",
        ".igs",
    }
)

# Extension -> folder name mapping used when Ollama is unavailable
TEXT_FALLBACK_MAP: dict[str, str] = {
    ".pdf": "PDFs",
    ".doc": "Documents",
    ".docx": "Documents",
    ".txt": "Documents",
    ".md": "Documents",
    ".csv": "Spreadsheets",
    ".xlsx": "Spreadsheets",
    ".xls": "Spreadsheets",
    ".ppt": "Presentations",
    ".pptx": "Presentations",
    ".epub": "eBooks",
    ".dwg": "CAD",
    ".dxf": "CAD",
    ".step": "CAD",
    ".stp": "CAD",
    ".iges": "CAD",
    ".igs": "CAD",
}

IMAGE_FALLBACK_FOLDER: str = "Images"
AUDIO_FALLBACK_FOLDER: str = "Audio/Unsorted"
VIDEO_FALLBACK_FOLDER: str = "Videos/Unsorted"
ERROR_FALLBACK_FOLDER: str = "errors"
