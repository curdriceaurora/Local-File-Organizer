"""
Video Organization Service

Generates organized folder structures for video files based on their
metadata. Supports screen recording detection, short clip routing,
and date-based organization. No AI model dependencies required.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .metadata_extractor import VideoMetadata, resolution_label

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Screen recording filename patterns
# ---------------------------------------------------------------------------

# macOS QuickTime: "Screen Recording 2025-01-15 at 3.45.22 PM"
_MACOS_SCREEN_RE = re.compile(
    r"^Screen Recording \d{4}-\d{2}-\d{2} at \d{1,2}\.\d{2}\.\d{2}",
    re.IGNORECASE,
)

# Windows Snipping Tool: "Screen Recording 2025-01-15 143022"
_WIN_SNIP_RE = re.compile(
    r"^Screen Recording \d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)

# OBS Studio: pure timestamp "2025-01-15 14-05-32" (no other text)
_OBS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}$")

# Xbox Game Bar: "{AppName} 2025-01-15 14-05-32"
_XBOX_RE = re.compile(r"^.+ \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}$")

# Camtasia: "Capture05", "Rec 2025-01-15"
_CAMTASIA_RE = re.compile(r"^(Capture\d+|Rec \d{4}-\d{2}-\d{2})", re.IGNORECASE)

# Generic keywords in filename
_GENERIC_KEYWORDS = re.compile(
    r"(screen.?recording|screencast|screen.?capture|rec_\d)",
    re.IGNORECASE,
)

# Short clip duration threshold (seconds)
SHORT_CLIP_THRESHOLD = 60.0


def is_screen_recording(filename: str) -> bool:
    """Detect if a filename matches common screen recording patterns.

    Args:
        filename: The filename (without extension) to check.

    Returns:
        True if the filename matches a known screen recording pattern.
    """
    name = Path(filename).stem  # strip extension if present

    if _MACOS_SCREEN_RE.search(name):
        return True
    if _WIN_SNIP_RE.search(name):
        return True
    if _OBS_RE.match(name):
        return True
    if _XBOX_RE.match(name):
        return True
    if _CAMTASIA_RE.match(name):
        return True
    if _GENERIC_KEYWORDS.search(name):
        return True

    return False


class VideoOrganizer:
    """
    Organizes video files into directory structures based on metadata.

    Organization priority (title/date primary, not resolution):
    1. Screen recordings → Screen_Recordings/{Year}/
    2. Short clips (<60s) → Short_Clips/
    3. Videos with creation date → Videos/{Year}/
    4. Fallback → Videos/Unsorted/

    Example:
        >>> organizer = VideoOrganizer()
        >>> folder, name = organizer.generate_path(metadata)
        >>> print(f"{folder}/{name}")
    """

    def generate_path(self, metadata: VideoMetadata) -> tuple[str, str]:
        """Generate an organized folder and filename for a video file.

        Args:
            metadata: Video file metadata.

        Returns:
            Tuple of (folder_name, filename_without_extension).
        """
        original_stem = metadata.file_path.stem
        year = self._get_year(metadata)

        # 1. Screen recordings
        if is_screen_recording(metadata.file_path.name):
            folder = f"Screen_Recordings/{year}" if year else "Screen_Recordings"
            return folder, original_stem

        # 2. Short clips
        if metadata.duration is not None and metadata.duration < SHORT_CLIP_THRESHOLD:
            return "Short_Clips", original_stem

        # 3. Videos with a known year
        if year:
            return f"Videos/{year}", original_stem

        # 4. Fallback
        return "Videos/Unsorted", original_stem

    def generate_description(self, metadata: VideoMetadata) -> str:
        """Generate a human-readable description for a video file.

        Args:
            metadata: Video file metadata.

        Returns:
            Description string.
        """
        parts = ["Video"]

        res = resolution_label(metadata.width, metadata.height)
        if res != "unknown":
            parts.append(res)

        if metadata.duration is not None:
            if metadata.duration >= 3600:
                hours = int(metadata.duration // 3600)
                mins = int((metadata.duration % 3600) // 60)
                parts.append(f"{hours}h{mins}m")
            elif metadata.duration >= 60:
                mins = int(metadata.duration // 60)
                secs = int(metadata.duration % 60)
                parts.append(f"{mins}m{secs}s")
            else:
                parts.append(f"{int(metadata.duration)}s")

        if metadata.codec:
            parts.append(metadata.codec)

        return ": ".join(parts[:1]) + " " + " ".join(parts[1:]) if len(parts) > 1 else parts[0]

    def _get_year(self, metadata: VideoMetadata) -> str | None:
        """Extract year string from metadata or filename.

        Tries creation_date first, then falls back to filename pattern matching.
        """
        if metadata.creation_date:
            return str(metadata.creation_date.year)

        # Try to extract year from filename (e.g. "2025-01-15" or "20250115")
        stem = metadata.file_path.stem
        match = re.search(r"(20\d{2})-?\d{2}-?\d{2}", stem)
        if match:
            return match.group(1)

        return None
