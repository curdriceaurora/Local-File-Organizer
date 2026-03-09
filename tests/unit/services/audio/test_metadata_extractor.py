from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.audio.metadata_extractor import (
    AudioMetadata,
    AudioMetadataExtractor,
)


@pytest.fixture
def mock_audio_path(tmp_path):
    audio = tmp_path / "test_audio.mp3"
    audio.write_bytes(b"dummy audio data")
    return audio


class TestAudioMetadataExtractor:
    def test_init(self):
        extractor = AudioMetadataExtractor()
        assert extractor.use_fallback is True

        extractor = AudioMetadataExtractor(use_fallback=False)
        assert extractor.use_fallback is False

    def test_extract_file_not_found(self):
        extractor = AudioMetadataExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract("non_existent_file.mp3")

    @patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_mutagen"
    )
    def test_extract_uses_mutagen_success(self, mock_mutagen, mock_audio_path):
        extractor = AudioMetadataExtractor()
        mock_metadata = MagicMock(spec=AudioMetadata)
        mock_mutagen.return_value = mock_metadata

        result = extractor.extract(mock_audio_path)
        assert result is mock_metadata
        mock_mutagen.assert_called_once_with(mock_audio_path)

    @patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_tinytag"
    )
    @patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_mutagen"
    )
    def test_extract_fallback_to_tinytag(self, mock_mutagen, mock_tinytag, mock_audio_path):
        extractor = AudioMetadataExtractor(use_fallback=True)
        # Force mutagen to fail
        mock_mutagen.side_effect = Exception("Mutagen failed")

        mock_metadata = MagicMock(spec=AudioMetadata)
        mock_tinytag.return_value = mock_metadata

        result = extractor.extract(mock_audio_path)
        assert result is mock_metadata
        mock_mutagen.assert_called_once_with(mock_audio_path)
        mock_tinytag.assert_called_once_with(mock_audio_path)

    @patch(
        "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_mutagen"
    )
    def test_extract_no_fallback_raises(self, mock_mutagen, mock_audio_path):
        extractor = AudioMetadataExtractor(use_fallback=False)
        # Force mutagen to fail
        mock_mutagen.side_effect = Exception("Mutagen failed")

        with pytest.raises(Exception, match="Mutagen failed"):
            extractor.extract(mock_audio_path)

    @patch("file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor.extract")
    def test_extract_batch(self, mock_extract, mock_audio_path):
        extractor = AudioMetadataExtractor()
        mock_metadata = MagicMock(spec=AudioMetadata)
        mock_extract.side_effect = [mock_metadata, Exception("Test Error")]

        results = extractor.extract_batch([mock_audio_path, mock_audio_path])
        assert len(results) == 1
        assert results[0] is mock_metadata

    def test_format_duration(self):
        assert AudioMetadataExtractor.format_duration(45.5) == "00:45"
        assert AudioMetadataExtractor.format_duration(125.0) == "02:05"
        assert AudioMetadataExtractor.format_duration(3665.0) == "01:01:05"

    def test_format_bitrate(self):
        assert AudioMetadataExtractor.format_bitrate(500) == "500 bps"
        assert AudioMetadataExtractor.format_bitrate(128000) == "128 kbps"
        assert AudioMetadataExtractor.format_bitrate(1500000) == "1.5 Mbps"

    def test_extract_with_mutagen(self, mock_audio_path):
        extractor = AudioMetadataExtractor()
        mock_file = MagicMock()
        mock_audio = MagicMock()
        mock_file.return_value = mock_audio

        # Setup mock properties
        mock_audio.info.length = 120.5
        mock_audio.info.bitrate = 320000
        mock_audio.info.sample_rate = 44100
        mock_audio.info.channels = 2
        mock_audio.info.codec = "mp3"

        # Setup mock tags
        mock_audio.tags = {
            "TIT2": "Test Song",
            "TPE1": ["Test Artist"],
            "TDRC": "2023",
            "TRCK": "1/10",
            "UNMAP": "extra",
        }

        # Simulate mutagen import
        mock_mutagen = MagicMock()
        mock_mutagen.File = mock_file
        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extractor._extract_with_mutagen(mock_audio_path)

        assert result.duration == 120.5
        assert result.bitrate == 320000
        assert result.sample_rate == 44100
        assert result.channels == 2
        assert result.codec == "mp3"
        assert result.title == "Test Song"
        assert result.artist == "Test Artist"
        assert result.year == 2023
        assert result.track_number == 1
        assert result.extra_tags["UNMAP"] == "extra"
        assert result.has_artwork is False

    def test_extract_with_tinytag(self, mock_audio_path):
        extractor = AudioMetadataExtractor()
        mock_tag = MagicMock()
        mock_tinytag_get = MagicMock(return_value=mock_tag)

        mock_tag.duration = 150.0
        mock_tag.bitrate = 128000
        mock_tag.samplerate = 48000
        mock_tag.channels = 2
        mock_tag.title = "Tiny Song"
        mock_tag.artist = "Tiny Artist"
        mock_tag.year = "2024"
        mock_tag.track = "2/12"
        mock_tag.disc = "1"

        # Simulate tinytag import
        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get = mock_tinytag_get
        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(mock_audio_path)

        assert result.duration == 150.0
        assert result.title == "Tiny Song"
        assert result.artist == "Tiny Artist"
        assert result.year == 2024
        assert result.track_number == 2
        assert result.disc_number == 1
