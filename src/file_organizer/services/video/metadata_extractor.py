"""Video Metadata Extraction Service.

Extracts metadata from video files using ffprobe (primary),
OpenCV (fallback), or filesystem-only (final fallback).
No AI model dependencies required.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Comprehensive video file metadata."""

    # File information
    file_path: Path
    file_size: int  # bytes
    format: str  # container format (mp4, mkv, etc.)

    # Video properties (None if extraction failed)
    duration: float | None = None  # seconds
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    bitrate: int | None = None  # bits per second
    creation_date: datetime | None = None


def resolution_label(width: int | None, height: int | None) -> str:
    """Classify resolution into a human-readable label.

    Args:
        width: Video width in pixels.
        height: Video height in pixels.

    Returns:
        One of "4k", "1080p", "720p", "480p", "sd", or "unknown".
    """
    if width is None or height is None:
        return "unknown"

    # Use the shorter dimension to classify (handles portrait videos)
    short = min(width, height)
    long = max(width, height)

    if long >= 3840 or short >= 2160:
        return "4k"
    if long >= 1920 or short >= 1080:
        return "1080p"
    if long >= 1280 or short >= 720:
        return "720p"
    if long >= 854 or short >= 480:
        return "480p"
    return "sd"


class VideoMetadataExtractor:
    """Video metadata extraction service.

    Uses a fallback chain:
    1. ffprobe (via ffmpeg-python / subprocess) — richest metadata
    2. OpenCV cv2.VideoCapture — resolution, fps, frame count
    3. Filesystem only — file_size and format from extension

    Example:
        >>> extractor = VideoMetadataExtractor()
        >>> metadata = extractor.extract(Path("video.mp4"))
        >>> print(metadata.width, metadata.height, metadata.duration)
    """

    def extract(self, video_path: Path) -> VideoMetadata:
        """Extract metadata from a single video file.

        Args:
            video_path: Path to the video file.

        Returns:
            VideoMetadata with as many fields populated as possible.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Start with filesystem-only baseline
        metadata = VideoMetadata(
            file_path=video_path,
            file_size=video_path.stat().st_size,
            format=video_path.suffix.lstrip(".").lower(),
        )

        # Try ffprobe first (richest metadata)
        if self._try_ffprobe(video_path, metadata):
            return metadata

        # Fallback to OpenCV
        if self._try_opencv(video_path, metadata):
            return metadata

        # Filesystem-only fallback (metadata already has file_size and format)
        logger.warning(
            f"Could not extract video metadata for {video_path.name}; "
            "install ffmpeg or opencv-python for rich metadata"
        )
        return metadata

    def extract_batch(self, paths: list[Path]) -> list[VideoMetadata]:
        """Extract metadata from multiple video files.

        Args:
            paths: List of video file paths.

        Returns:
            List of VideoMetadata, one per input path.
        """
        return [self.extract(p) for p in paths]

    def _try_ffprobe(self, video_path: Path, metadata: VideoMetadata) -> bool:
        """Attempt metadata extraction via ffprobe.

        Returns True if successful, False if ffprobe is unavailable or fails.
        Populates fields on the metadata object in-place.
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False

            probe = json.loads(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            # ffprobe not installed, timed out, or bad output
            return False

        # Find the video stream
        video_stream = None
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if video_stream:
            metadata.width = _safe_int(video_stream.get("width"))
            metadata.height = _safe_int(video_stream.get("height"))
            metadata.codec = video_stream.get("codec_name")

            # FPS from r_frame_rate (e.g. "30/1" or "30000/1001")
            r_frame_rate = video_stream.get("r_frame_rate", "")
            if "/" in r_frame_rate:
                parts = r_frame_rate.split("/")
                num, den = _safe_int(parts[0]), _safe_int(parts[1])
                if num and den and den != 0:
                    metadata.fps = round(num / den, 3)

            # Duration from stream or format
            dur = video_stream.get("duration")
            if dur is None:
                dur = probe.get("format", {}).get("duration")
            if dur is not None:
                metadata.duration = _safe_float(dur)

        # Format-level metadata
        fmt = probe.get("format", {})
        metadata.bitrate = _safe_int(fmt.get("bit_rate"))

        # Duration fallback from format
        if metadata.duration is None:
            metadata.duration = _safe_float(fmt.get("duration"))

        # Creation date from format tags
        tags = fmt.get("tags", {})
        creation_time = tags.get("creation_time") or tags.get("date")
        if creation_time:
            metadata.creation_date = _parse_datetime(creation_time)

        return True

    def _try_opencv(self, video_path: Path, metadata: VideoMetadata) -> bool:
        """Attempt metadata extraction via OpenCV.

        Returns True if successful, False if OpenCV is unavailable or fails.
        """
        try:
            import cv2
        except ImportError:
            return False

        cap = cv2.VideoCapture(str(video_path))
        try:
            if not cap.isOpened():
                return False

            metadata.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            metadata.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            metadata.fps = cap.get(cv2.CAP_PROP_FPS) or None

            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if metadata.fps and frame_count and metadata.fps > 0:
                metadata.duration = frame_count / metadata.fps

            return True
        except Exception:
            logger.debug(f"OpenCV extraction failed for {video_path.name}", exc_info=True)
            return False
        finally:
            cap.release()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: str | int | None) -> int | None:
    """Convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: str | float | None) -> float | None:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: str) -> datetime | None:
    """Parse a datetime string from ffprobe tags.

    Handles common formats:
    - ISO 8601: 2024-01-15T14:30:45Z
    - Date only: 2024-01-15
    - With timezone offset: 2024-01-15T14:30:45+00:00
    """
    stripped = value.strip()

    # Try datetime.fromisoformat first — handles Z and ±HH:MM offsets (Python 3.11+)
    try:
        dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        # Return naive datetime (strip tzinfo) for consistency with rest of codebase
        return dt.replace(tzinfo=None)
    except ValueError:
        pass

    # Fallback: strptime for formats fromisoformat can't handle
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    return None
