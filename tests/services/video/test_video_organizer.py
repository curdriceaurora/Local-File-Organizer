"""Tests for VideoOrganizer and is_screen_recording."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.services.video.metadata_extractor import VideoMetadata
from file_organizer.services.video.organizer import (
    SHORT_CLIP_THRESHOLD,
    VideoOrganizer,
    is_screen_recording,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def organizer() -> VideoOrganizer:
    return VideoOrganizer()


def _make_metadata(
    filename: str = "vacation.mp4",
    duration: float | None = 120.0,
    width: int | None = 1920,
    height: int | None = 1080,
    codec: str | None = "h264",
    creation_date: datetime | None = None,
    file_size: int = 1024,
) -> VideoMetadata:
    """Build a VideoMetadata with sensible defaults."""
    path = Path(f"/tmp/{filename}")
    return VideoMetadata(
        file_path=path,
        file_size=file_size,
        format=path.suffix.lstrip(".").lower(),
        duration=duration,
        width=width,
        height=height,
        codec=codec,
        creation_date=creation_date,
    )


# ---------------------------------------------------------------------------
# is_screen_recording tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsScreenRecording:
    def test_macos_quicktime(self) -> None:
        assert is_screen_recording("Screen Recording 2025-01-15 at 3.45.22 PM.mov")

    def test_macos_quicktime_lowercase(self) -> None:
        assert is_screen_recording("screen recording 2025-01-15 at 3.45.22 PM.mov")

    def test_windows_snipping_tool(self) -> None:
        assert is_screen_recording("Screen Recording 2025-01-15 143022.mp4")

    def test_obs_timestamp(self) -> None:
        assert is_screen_recording("2025-01-15 14-05-32.mkv")

    def test_xbox_game_bar(self) -> None:
        assert is_screen_recording("Minecraft 2025-01-15 14-05-32.mp4")

    def test_camtasia_capture(self) -> None:
        assert is_screen_recording("Capture05.mp4")

    def test_camtasia_rec(self) -> None:
        assert is_screen_recording("Rec 2025-01-15.mp4")

    def test_generic_screencast(self) -> None:
        assert is_screen_recording("my_screencast_tutorial.mp4")

    def test_generic_screen_capture(self) -> None:
        assert is_screen_recording("screen-capture-2025.mp4")

    def test_generic_rec_pattern(self) -> None:
        assert is_screen_recording("rec_1.mp4")

    # Negative cases
    def test_normal_video(self) -> None:
        assert not is_screen_recording("vacation_2025.mp4")

    def test_birthday_video(self) -> None:
        assert not is_screen_recording("birthday_party.mov")

    def test_project_recording(self) -> None:
        # "recording" alone doesn't match — needs "screen" prefix or "rec_" pattern
        assert not is_screen_recording("recording_interview.mp4")

    def test_empty_string(self) -> None:
        assert not is_screen_recording("")


# ---------------------------------------------------------------------------
# VideoOrganizer.generate_path tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeneratePath:
    def test_screen_recording_with_date(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            filename="Screen Recording 2025-01-15 at 3.45.22 PM.mov",
            creation_date=datetime(2025, 1, 15, tzinfo=UTC),
        )
        folder, name = organizer.generate_path(metadata)
        assert folder == "Screen_Recordings/2025"
        assert name == "Screen Recording 2025-01-15 at 3.45.22 PM"

    def test_screen_recording_without_date(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            filename="Capture05.mp4",
            creation_date=None,
        )
        folder, name = organizer.generate_path(metadata)
        assert folder == "Screen_Recordings"
        assert name == "Capture05"

    def test_short_clip(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(duration=30.0)
        assert metadata.duration is not None
        assert metadata.duration < SHORT_CLIP_THRESHOLD
        folder, name = organizer.generate_path(metadata)
        assert folder == "Short_Clips"
        assert name == "vacation"

    def test_short_clip_boundary(self, organizer: VideoOrganizer) -> None:
        # Exactly at threshold should NOT be a short clip
        metadata = _make_metadata(duration=60.0)
        folder, _name = organizer.generate_path(metadata)
        assert folder != "Short_Clips"

    def test_date_based_routing(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            creation_date=datetime(2024, 7, 4, tzinfo=UTC),
            duration=120.0,
        )
        folder, name = organizer.generate_path(metadata)
        assert folder == "Videos/2024"
        assert name == "vacation"

    def test_date_from_filename(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            filename="2024-07-04_fireworks.mp4",
            creation_date=None,
            duration=120.0,
        )
        folder, name = organizer.generate_path(metadata)
        assert folder == "Videos/2024"
        assert name == "2024-07-04_fireworks"

    def test_fallback_unsorted(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            filename="random_clip.avi",
            creation_date=None,
            duration=120.0,
        )
        folder, name = organizer.generate_path(metadata)
        assert folder == "Videos/Unsorted"
        assert name == "random_clip"

    def test_no_duration_not_short_clip(self, organizer: VideoOrganizer) -> None:
        # When duration is None, should not route to Short_Clips
        metadata = _make_metadata(
            duration=None,
            creation_date=datetime(2025, 3, 1, tzinfo=UTC),
        )
        folder, _name = organizer.generate_path(metadata)
        assert folder == "Videos/2025"

    def test_screen_recording_priority_over_short_clip(self, organizer: VideoOrganizer) -> None:
        # Short screen recording should go to Screen_Recordings, not Short_Clips
        metadata = _make_metadata(
            filename="Screen Recording 2025-01-15 at 3.45.22 PM.mov",
            duration=10.0,
            creation_date=datetime(2025, 1, 15, tzinfo=UTC),
        )
        folder, _name = organizer.generate_path(metadata)
        assert folder.startswith("Screen_Recordings")


# ---------------------------------------------------------------------------
# VideoOrganizer.generate_description tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateDescription:
    def test_full_description(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(
            duration=120.5,
            width=1920,
            height=1080,
            codec="h264",
        )
        desc = organizer.generate_description(metadata)
        assert "Video" in desc
        assert "1080p" in desc
        assert "h264" in desc
        assert "2m0s" in desc

    def test_long_video_hours(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(duration=7200.0)
        desc = organizer.generate_description(metadata)
        assert "2h0m" in desc

    def test_short_video_seconds(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(duration=30.0)
        desc = organizer.generate_description(metadata)
        assert "30s" in desc

    def test_unknown_resolution(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(width=None, height=None)
        desc = organizer.generate_description(metadata)
        assert "Video" in desc
        # Should not contain resolution label when unknown
        assert "unknown" not in desc.lower() or "unknown" not in desc

    def test_no_duration(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(duration=None)
        desc = organizer.generate_description(metadata)
        assert "Video" in desc

    def test_no_codec(self, organizer: VideoOrganizer) -> None:
        metadata = _make_metadata(codec=None)
        desc = organizer.generate_description(metadata)
        assert "Video" in desc
        assert "h264" not in desc
