"""Tests for VideoMetadataExtractor."""

from __future__ import annotations

import json
import subprocess
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
            3: 1280.0,  # CAP_PROP_FRAME_WIDTH
            4: 720.0,  # CAP_PROP_FRAME_HEIGHT
            5: 24.0,  # CAP_PROP_FPS
            7: 2400.0,  # CAP_PROP_FRAME_COUNT
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
@pytest.mark.ci
class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00Z")
        assert result == datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)

    def test_iso_with_microseconds(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00.123456Z")
        assert result is not None
        assert result.year == 2025
        assert result.month == 6
        assert result.microsecond == 123456
        assert result.tzinfo == UTC

    def test_date_only(self) -> None:
        result = _parse_datetime("2025-06-15")
        assert result == datetime(2025, 6, 15, tzinfo=UTC)

    def test_year_only(self) -> None:
        result = _parse_datetime("2025")
        assert result is not None
        assert result.year == 2025
        assert result.tzinfo is not None  # implementation normalises naive → UTC

    def test_unparseable(self) -> None:
        assert _parse_datetime("not-a-date") is None

    def test_timezone_offset(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00+05:30")
        assert result is not None
        # Normalised to UTC: 10:30 IST (+05:30) = 05:00 UTC
        assert result == datetime(2025, 6, 15, 5, 0, 0, tzinfo=UTC)

    def test_datetime_with_microseconds_no_z(self) -> None:
        result = _parse_datetime("2025-06-15T10:30:00.123456")
        assert result == datetime(2025, 6, 15, 10, 30, 0, 123456, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ffprobe error-handling tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestFfprobeErrorHandling:
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 10))
    def test_timeout_falls_back(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """ffprobe timeout must fall through to the next fallback."""
        with patch.dict("sys.modules", {"cv2": None}):
            metadata = extractor.extract(sample_video)
        assert metadata.width is None
        assert metadata.duration is None
        assert metadata.file_size == 1024  # filesystem baseline preserved

    @patch("subprocess.run")
    def test_nonzero_return_code_falls_back(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """Non-zero ffprobe exit code must fall through to the next fallback."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with patch.dict("sys.modules", {"cv2": None}):
            metadata = extractor.extract(sample_video)
        assert metadata.width is None

    @patch("subprocess.run")
    def test_bad_json_falls_back(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """Malformed JSON from ffprobe must fall through to the next fallback."""
        mock_run.return_value = MagicMock(returncode=0, stdout="NOT_JSON{{{")
        with patch.dict("sys.modules", {"cv2": None}):
            metadata = extractor.extract(sample_video)
        assert metadata.width is None

    @patch("subprocess.run")
    def test_audio_only_file_no_video_stream(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """Audio-only file (no video stream) should leave video fields as None."""
        probe = {
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
            "format": {"duration": "180.0", "bit_rate": "128000", "tags": {}},
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(probe))
        metadata = extractor.extract(sample_video)
        assert metadata.width is None
        assert metadata.height is None
        assert metadata.codec is None
        assert metadata.fps is None
        # Duration and bitrate come from format section even without a video stream
        assert metadata.duration == 180.0
        assert metadata.bitrate == 128000


# ---------------------------------------------------------------------------
# ffprobe fps / duration edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestFfprobeFpsEdgeCases:
    @patch("subprocess.run")
    def test_zero_denominator_fps_not_set(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """r_frame_rate '30/0' must NOT cause a ZeroDivisionError; fps stays None."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(
                width=1280,
                height=720,
                fps="30/0",
                duration="60.0",
                bitrate="2000000",
                creation_time=None,
            ),
        )
        metadata = extractor.extract(sample_video)
        assert metadata.fps is None  # zero denominator → skipped
        assert metadata.width == 1280

    @patch("subprocess.run")
    def test_no_slash_fps_not_set(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """r_frame_rate without '/' means fps is left as None."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_ffprobe_output(
                width=640,
                height=480,
                fps="25",
                duration="10.0",
                bitrate="500000",
                creation_time=None,
            ),
        )
        metadata = extractor.extract(sample_video)
        assert metadata.fps is None
        # Confirm ffprobe path was taken — other fields from the stream are populated
        assert metadata.width == 640
        assert metadata.height == 480
        assert metadata.codec == "h264"
        assert metadata.duration == 10.0

    @patch("subprocess.run")
    def test_duration_falls_back_to_format_section(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """When the video stream has no duration field, format duration is used."""
        probe = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "24/1",
                    "codec_name": "h264",
                    # no "duration" key in stream
                }
            ],
            "format": {"duration": "90.0", "bit_rate": "8000000", "tags": {}},
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(probe))
        metadata = extractor.extract(sample_video)
        assert metadata.duration == 90.0


# ---------------------------------------------------------------------------
# OpenCV edge-case tests
# ---------------------------------------------------------------------------


def _make_mock_cv2(
    opened: bool = True,
    width: float = 1280.0,
    height: float = 720.0,
    fps: float = 24.0,
    frame_count: float = 2400.0,
) -> MagicMock:
    """Return a mock cv2 module with a pre-configured VideoCapture."""
    mock_cv2 = MagicMock()
    mock_cv2.CAP_PROP_FRAME_WIDTH = 3
    mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_FRAME_COUNT = 7
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = opened
    mock_cap.get.side_effect = lambda prop: {
        3: width,  # CAP_PROP_FRAME_WIDTH
        4: height,  # CAP_PROP_FRAME_HEIGHT
        5: fps,  # CAP_PROP_FPS
        7: frame_count,  # CAP_PROP_FRAME_COUNT
    }.get(prop, 0.0)
    mock_cv2.VideoCapture.return_value = mock_cap
    return mock_cv2


@pytest.mark.unit
@pytest.mark.ci
class TestOpencvEdgeCases:
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_cap_not_opened_falls_through(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """When cap.isOpened() returns False, OpenCV path returns False and
        falls through to the filesystem-only baseline."""
        with patch.dict("sys.modules", {"cv2": _make_mock_cv2(opened=False)}):
            metadata = extractor.extract(sample_video)

        assert metadata.width is None
        assert metadata.height is None
        assert metadata.fps is None
        assert metadata.file_size == 1024  # filesystem baseline

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_zero_fps_does_not_set_duration(
        self, mock_run: MagicMock, extractor: VideoMetadataExtractor, sample_video: Path
    ) -> None:
        """fps=0 from OpenCV must not cause division-by-zero when computing duration."""
        with patch.dict("sys.modules", {"cv2": _make_mock_cv2(fps=0.0, frame_count=1000.0)}):
            metadata = extractor.extract(sample_video)

        assert metadata.fps is None  # 0.0 → falsy → or None
        assert metadata.duration is None  # no valid fps → duration not computed


# ---------------------------------------------------------------------------
# Batch edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.ci
class TestBatchEdgeCases:
    def test_empty_batch_returns_empty_list(self, extractor: VideoMetadataExtractor) -> None:
        results = extractor.extract_batch([])
        assert results == []
