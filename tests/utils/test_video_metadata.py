"""Tests for video metadata extraction - Phase 3."""

from __future__ import annotations

import pytest

# Phase 3 placeholder tests for video metadata


@pytest.mark.unit
class TestVideoMetadataPlaceholder:
    """Test video metadata extraction Phase 3 functionality."""

    def test_video_metadata_module_exists(self):
        """Test that video metadata module exists."""
        try:
            from file_organizer.services.video import scene_detector

            assert scene_detector is not None
        except ImportError:
            pytest.skip("Video metadata extraction not yet implemented (Phase 3)")

    @pytest.mark.skip(reason="See #1073 - Requires real video file; fake bytes cause decode failure")
    def test_extract_mp4_metadata(self, tmp_path):
        """Test extracting metadata from MP4 file."""
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake mp4")

        extractor = VideoMetadataExtractor()
        metadata = extractor.extract(video_file)

        assert metadata.duration is not None
        assert metadata.width is not None

    @pytest.mark.skip(reason="See #1073 - Requires real video file; fake bytes cause decode failure")
    def test_extract_resolution(self, tmp_path):
        """Test extracting video resolution."""
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        video_file = tmp_path / "test.avi"
        video_file.write_bytes(b"fake avi")

        extractor = VideoMetadataExtractor()
        metadata = extractor.extract(video_file)

        assert metadata.width is not None
        assert metadata.height is not None

    @pytest.mark.skip(reason="See #1073 - Requires real video file; fake bytes cause decode failure")
    def test_detect_codec(self, tmp_path):
        """Test detecting video codec."""
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        video_file = tmp_path / "test.mkv"
        video_file.write_bytes(b"fake mkv")

        extractor = VideoMetadataExtractor()
        metadata = extractor.extract(video_file)

        assert metadata.codec is not None
