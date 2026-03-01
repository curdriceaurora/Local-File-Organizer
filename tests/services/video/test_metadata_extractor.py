"""Tests for VideoMetadataExtractor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.video.metadata_extractor import (
    VideoMetadata,
    VideoMetadataExtractor,
    _parse_datetime,
    resolution_label,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def extractor() -> VideoMetadataExtractor:
    return VideoMetadataExtractor()


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Create a dummy video file for testing."""
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"\x00" * 1024)
    return video


def _ffprobe_output(
    width: int = 1920,
    height: int = 1080,
    fps: str = "30/1",
    codec: str = "h264",
    duration: str = "120.5",
    bitrate: str = "5000000",
    creation_time: str | None = "2025-06-15T10:30:00Z",
) -> str:
    """Build a mock ffprobe JSON output."""
    tags = {}
    if creation_time:
        tags["creation_time"] = creation_time

    data = {
        "streams": [
            {
                "codec_type": "video",
                "width": width,
                "height": height,
                "r_frame_rate": fps,
                "codec_name": codec,
                "duration": duration,
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {
            "duration": duration,
            "bit_rate": bitrate,
            "tags": tags,
        },
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# resolution_label tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolutionLabel:
    def test_4k(self) -> None:
        assert resolution_label(3840, 2160) == "4k"

    def test_1080p(self) -> None:
        assert resolution_label(1920, 1080) == "1080p"

    def test_720p(self) -> None:
        assert resolution_label(1280, 720) == "720p"

    def test_480p(self) -> None:
        assert resolution_label(854, 480) == "480p"

    def test_sd(self) -> None:
        assert resolution_label(640, 480) == "480p"
        assert resolution_label(320, 240) == "sd"

    def test_unknown_when_none(self) -> None:
        assert resolution_label(None, None) == "unknown"
        assert resolution_label(1920, None) == "unknown"

    def test_portrait_video(self) -> None:
        # 1080x1920 portrait should still classify as 1080p
        assert resolution_label(1080, 1920) == "1080p"


# ---------------------------------------------------------------------------
# ffprobe extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFfprobeExtraction:
    @patch("subprocess.run")
    def test_extracts_all_fields(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(),
        )
        metadata = extractor.extract(sample_video)

        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.fps == 30.0
        assert metadata.codec == "h264"
        assert metadata.duration == 120.5
        assert metadata.bitrate == 5000000
        assert metadata.creation_date == datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
        assert metadata.file_size == 1024
        assert metadata.format == "mp4"

    @patch("subprocess.run")
    def test_fractional_fps(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(fps="30000/1001"),
        )
        metadata = extractor.extract(sample_video)
        assert metadata.fps is not None
        assert abs(metadata.fps - 29.97) < 0.01

    @patch("subprocess.run")
    def test_no_creation_date(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(creation_time=None),
        )
        metadata = extractor.extract(sample_video)
        assert metadata.creation_date is None

    @patch("subprocess.run")
    def test_4k_video(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(width=3840, height=2160),
        )
        metadata = extractor.extract(sample_video)
        assert resolution_label(metadata.width, metadata.height) == "4k"


# ---------------------------------------------------------------------------
# OpenCV fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpencvFallback:
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_falls_back_to_opencv(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            3: 1280.0,   # CAP_PROP_FRAME_WIDTH
            4: 720.0,    # CAP_PROP_FRAME_HEIGHT
            5: 24.0,     # CAP_PROP_FPS
            7: 2400.0,   # CAP_PROP_FRAME_COUNT
        }.get(prop, 0.0)
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            metadata = extractor.extract(sample_video)

        assert metadata.width == 1280
        assert metadata.height == 720
        assert metadata.fps == 24.0
        assert metadata.duration == 100.0  # 2400 / 24


# ---------------------------------------------------------------------------
# Filesystem-only fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilesystemFallback:
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_filesystem_only_when_no_deps(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        # Ensure cv2 import fails
        with patch.dict("sys.modules", {"cv2": None}):
            metadata = extractor.extract(sample_video)

        assert metadata.file_size == 1024
        assert metadata.format == "mp4"
        assert metadata.width is None
        assert metadata.height is None
        assert metadata.duration is None

    def test_file_not_found_raises(self, extractor: VideoMetadataExtractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("/nonexistent/video.mp4"))


# ---------------------------------------------------------------------------
# Batch extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBatchExtraction:
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_batch_returns_list(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, tmp_path: Path
    ) -> None:
        videos = []
        for i in range(3):
            v = tmp_path / f"video_{i}.mp4"
            v.write_bytes(b"\x00" * (100 * (i + 1)))
            videos.append(v)

        with patch.dict("sys.modules", {"cv2": None}):
            results = extractor.extract_batch(videos)

        assert len(results) == 3
        assert all(isinstance(r, VideoMetadata) for r in results)
        assert results[0].file_size == 100
        assert results[2].file_size == 300


# ---------------------------------------------------------------------------
# Datetime parsing tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00Z")
        assert result == datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)

    def test_iso_with_microseconds(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00.123456Z")
        assert result is not None
        assert result.year == 2025

    def test_date_only(self) -> None:
        result = _parse_datetime("2025-06-15")
        assert result == datetime(2025, 6, 15, tzinfo=UTC)

    def test_year_only(self) -> None:
        result = _parse_datetime("2025")
        assert result is not None
        assert result.year == 2025

    def test_unparseable(self) -> None:
        assert _parse_datetime("not-a-date") is None
