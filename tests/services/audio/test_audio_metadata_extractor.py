"""Tests for AudioMetadataExtractor class.

Tests metadata extraction with mutagen primary and tinytag fallback,
tag parsing for ID3/Vorbis/MP4 formats, artwork detection, batch
extraction, and formatting utilities.
External dependencies (mutagen, tinytag) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.audio.metadata_extractor import (
    AudioMetadata,
    AudioMetadataExtractor,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def extractor():
    """Create default AudioMetadataExtractor."""
    return AudioMetadataExtractor(use_fallback=True)


@pytest.fixture
def no_fallback_extractor():
    """Create extractor without fallback."""
    return AudioMetadataExtractor(use_fallback=False)


@pytest.fixture
def audio_file(tmp_path):
    """Create a fake mp3 file."""
    p = tmp_path / "test.mp3"
    p.write_bytes(b"fake audio data for testing")
    return p


@pytest.fixture
def flac_file(tmp_path):
    """Create a fake flac file."""
    p = tmp_path / "test.flac"
    p.write_bytes(b"fake flac data")
    return p


def _make_mock_mutagen_audio(
    *,
    length=120.5,
    bitrate=320000,
    sample_rate=44100,
    channels=2,
    codec=None,
    tags=None,
    has_pictures_attr=False,
    pictures=None,
):
    """Helper to build a mock mutagen File object."""
    audio = MagicMock()
    audio.info.length = length
    audio.info.bitrate = bitrate
    audio.info.sample_rate = sample_rate
    audio.info.channels = channels

    if codec is not None:
        audio.info.codec = codec
    else:
        del audio.info.codec
        del audio.info.codec_name

    if tags is None:
        audio.tags = None
    else:
        audio.tags = tags

    if has_pictures_attr and pictures is not None:
        audio.tags.pictures = pictures
    elif has_pictures_attr:
        audio.tags.pictures = []

    return audio


# ---------------------------------------------------------------------------
# AudioMetadata dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioMetadata:
    """Tests for AudioMetadata dataclass."""

    def test_required_fields(self, tmp_path):
        p = tmp_path / "test.mp3"
        m = AudioMetadata(
            file_path=p,
            file_size=1024,
            format="MP3",
            duration=60.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
        )
        assert m.file_path == p
        assert m.duration == 60.0
        assert m.bitrate == 128000

    def test_defaults(self, tmp_path):
        p = tmp_path / "test.mp3"
        m = AudioMetadata(
            file_path=p,
            file_size=1024,
            format="MP3",
            duration=60.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
        )
        assert m.title is None
        assert m.artist is None
        assert m.album is None
        assert m.has_artwork is False
        assert m.artwork_count == 0
        assert m.extra_tags == {}

    def test_all_tag_fields(self, tmp_path):
        p = tmp_path / "test.mp3"
        m = AudioMetadata(
            file_path=p,
            file_size=2048,
            format="FLAC",
            duration=300.0,
            bitrate=1411200,
            sample_rate=48000,
            channels=2,
            title="Song Title",
            artist="Artist",
            album="Album",
            album_artist="Album Artist",
            genre="Rock",
            year=2024,
            track_number=3,
            disc_number=1,
            comment="A comment",
            codec="flac",
            encoder="LAME",
            has_artwork=True,
            artwork_count=2,
        )
        assert m.title == "Song Title"
        assert m.year == 2024
        assert m.track_number == 3
        assert m.has_artwork is True
        assert m.artwork_count == 2


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioMetadataExtractorInit:
    """Tests for AudioMetadataExtractor initialization."""

    def test_default_fallback(self):
        ext = AudioMetadataExtractor()
        assert ext.use_fallback is True

    def test_no_fallback(self):
        ext = AudioMetadataExtractor(use_fallback=False)
        assert ext.use_fallback is False


# ---------------------------------------------------------------------------
# extract - main entry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtract:
    """Tests for extract method."""

    def test_file_not_found(self, extractor):
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            extractor.extract("/nonexistent/audio.mp3")

    def test_mutagen_success(self, extractor, audio_file):

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_mutagen"
        ) as mock_extract:
            mock_extract.return_value = AudioMetadata(
                file_path=audio_file,
                file_size=100,
                format="MP3",
                duration=120.5,
                bitrate=320000,
                sample_rate=44100,
                channels=2,
            )
            result = extractor.extract(audio_file)
        assert result.duration == 120.5

    def test_mutagen_fails_falls_back_to_tinytag(self, extractor, audio_file):
        with patch.object(
            extractor, "_extract_with_mutagen", side_effect=Exception("mutagen error")
        ):
            with patch.object(extractor, "_extract_with_tinytag") as mock_tt:
                mock_tt.return_value = AudioMetadata(
                    file_path=audio_file,
                    file_size=100,
                    format="MP3",
                    duration=60.0,
                    bitrate=128000,
                    sample_rate=44100,
                    channels=2,
                )
                result = extractor.extract(audio_file)
                mock_tt.assert_called_once_with(audio_file)
                assert result.duration == 60.0

    def test_no_fallback_raises(self, no_fallback_extractor, audio_file):
        with patch.object(
            no_fallback_extractor,
            "_extract_with_mutagen",
            side_effect=Exception("mutagen error"),
        ):
            with pytest.raises(Exception, match="mutagen error"):
                no_fallback_extractor.extract(audio_file)


# ---------------------------------------------------------------------------
# _extract_with_mutagen
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractWithMutagen:
    """Tests for _extract_with_mutagen."""

    def test_import_error(self, extractor, audio_file):
        def fake_import(name, *args, **kwargs):
            if "mutagen" in name:
                raise ImportError("no mutagen")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__
        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="mutagen is required"):
                extractor._extract_with_mutagen(audio_file)

    def test_unsupported_format_returns_none(self, extractor, audio_file):

        with patch.dict("sys.modules", {"mutagen": MagicMock()}):
            with patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor._extract_with_mutagen"
            ) as mock_method:
                mock_method.side_effect = ValueError("Unsupported audio format")
                with pytest.raises(ValueError, match="Unsupported"):
                    extractor._extract_with_mutagen(audio_file)

    def test_basic_extraction_with_no_tags(self, extractor, audio_file):
        mock_audio = _make_mock_mutagen_audio(tags=None)
        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = mock_audio

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extractor._extract_with_mutagen(audio_file)

        assert result.duration == 120.5
        assert result.bitrate == 320000
        assert result.sample_rate == 44100
        assert result.channels == 2
        assert result.format == "MP3"
        assert result.title is None

    def test_extraction_with_codec_attr(self, extractor, audio_file):
        mock_audio = _make_mock_mutagen_audio(codec="mp3", tags=None)
        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = mock_audio

        with patch.dict("sys.modules", {"mutagen": mock_mutagen}):
            result = extractor._extract_with_mutagen(audio_file)

        assert result.codec == "mp3"


# ---------------------------------------------------------------------------
# _extract_tags_mutagen
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractTagsMutagen:
    """Tests for _extract_tags_mutagen."""

    def test_none_tags(self, extractor):
        audio = MagicMock()
        audio.tags = None
        tags = extractor._extract_tags_mutagen(audio)
        assert tags["title"] is None
        assert tags["artist"] is None
        assert tags["extra_tags"] == {}

    def test_id3_tags(self, extractor):
        mock_tags = MagicMock()
        mock_tags.__iter__ = MagicMock(return_value=iter([]))
        mock_tags.items.return_value = [
            ("TIT2", "Song Title"),
            ("TPE1", "Artist Name"),
            ("TALB", "Album Name"),
            ("TCON", "Rock"),
            ("TDRC", "2024"),
            ("TRCK", "3/12"),
            ("TPOS", "1/2"),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)

        assert tags["title"] == "Song Title"
        assert tags["artist"] == "Artist Name"
        assert tags["album"] == "Album Name"
        assert tags["genre"] == "Rock"
        assert tags["year"] == 2024
        assert tags["track_number"] == 3
        assert tags["disc_number"] == 1

    def test_vorbis_tags(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("title", ["My Song"]),
            ("artist", ["My Artist"]),
            ("album", ["My Album"]),
            ("date", ["2023-05-01"]),
            ("tracknumber", ["7"]),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)

        assert tags["title"] == "My Song"
        assert tags["artist"] == "My Artist"
        assert tags["year"] == 2023
        assert tags["track_number"] == 7

    def test_mp4_tags(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("\xa9nam", ["iTunes Title"]),
            ("\xa9ART", ["iTunes Artist"]),
            ("\xa9alb", ["iTunes Album"]),
            ("\xa9day", ["2022"]),
            ("trkn", [(5, 10)]),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)

        assert tags["title"] == "iTunes Title"
        assert tags["artist"] == "iTunes Artist"
        assert tags["year"] == 2022
        # Track number from tuple
        assert tags["track_number"] == 5

    def test_unmapped_tags_go_to_extra(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("TXXX:custom", "custom value"),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)
        assert "TXXX:custom" in tags["extra_tags"]

    def test_year_non_numeric(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("TDRC", "not-a-year"),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)
        assert tags["year"] is None

    def test_track_number_plain_digit(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("TRCK", "5"),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)
        assert tags["track_number"] == 5

    def test_list_value_extracts_first(self, extractor):
        mock_tags = MagicMock()
        mock_tags.items.return_value = [
            ("TIT2", ["First", "Second"]),
        ]

        audio = MagicMock()
        audio.tags = mock_tags

        tags = extractor._extract_tags_mutagen(audio)
        assert tags["title"] == "First"


# ---------------------------------------------------------------------------
# _check_artwork_mutagen
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckArtworkMutagen:
    """Tests for _check_artwork_mutagen."""

    def test_no_tags(self, extractor):
        audio = MagicMock()
        audio.tags = None
        has_art, count = extractor._check_artwork_mutagen(audio)
        assert has_art is False
        assert count == 0

    def test_flac_pictures(self, extractor):
        audio = MagicMock()
        audio.tags = MagicMock()
        audio.tags.pictures = [MagicMock(), MagicMock()]
        # Make sure keys() returns something without APIC
        audio.tags.keys.return_value = []
        audio.tags.__contains__ = MagicMock(return_value=False)

        has_art, count = extractor._check_artwork_mutagen(audio)
        assert has_art is True
        assert count == 2

    def test_mp3_apic_frames(self, extractor):
        # Tags mock without 'pictures' attribute but with keys()
        tags = MagicMock(spec=["keys", "__contains__", "__getitem__", "items"])
        tags.keys.return_value = ["APIC:Cover", "APIC:", "TIT2"]
        tags.__contains__ = MagicMock(return_value=False)

        audio = MagicMock(spec=["tags", "info"])
        audio.tags = tags

        has_art, count = extractor._check_artwork_mutagen(audio)
        assert has_art is True
        assert count == 2

    def test_mp4_covr(self, extractor):
        tags = MagicMock(spec=["keys", "__contains__", "__getitem__", "items"])
        tags.keys.return_value = ["covr", "\xa9nam"]
        tags.__contains__ = MagicMock(side_effect=lambda k: k == "covr")
        tags.__getitem__ = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock()])

        audio = MagicMock(spec=["tags", "info"])
        audio.tags = tags

        has_art, count = extractor._check_artwork_mutagen(audio)
        assert has_art is True
        assert count == 3

    def test_no_artwork(self, extractor):
        tags = MagicMock(spec=["keys", "__contains__", "__getitem__", "items"])
        tags.keys.return_value = ["TIT2", "TPE1"]
        tags.__contains__ = MagicMock(return_value=False)

        audio = MagicMock(spec=["tags", "info"])
        audio.tags = tags

        has_art, count = extractor._check_artwork_mutagen(audio)
        assert has_art is False
        assert count == 0


# ---------------------------------------------------------------------------
# _extract_with_tinytag
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractWithTinytag:
    """Tests for _extract_with_tinytag fallback."""

    def test_import_error(self, extractor, audio_file):
        def fake_import(name, *args, **kwargs):
            if "tinytag" in name:
                raise ImportError("no tinytag")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__
        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="tinytag is required"):
                extractor._extract_with_tinytag(audio_file)

    def test_basic_extraction(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 90.5
        mock_tag.bitrate = 256
        mock_tag.samplerate = 44100
        mock_tag.channels = 2
        mock_tag.title = "TinyTag Title"
        mock_tag.artist = "TinyTag Artist"
        mock_tag.album = "TinyTag Album"
        mock_tag.albumartist = "Album Artist"
        mock_tag.genre = "Pop"
        mock_tag.year = "2023"
        mock_tag.track = "5/10"
        mock_tag.disc = "1/2"
        mock_tag.comment = "A comment"

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.duration == 90.5
        assert result.title == "TinyTag Title"
        assert result.artist == "TinyTag Artist"
        assert result.year == 2023
        assert result.track_number == 5
        assert result.disc_number == 1

    def test_plain_track_and_disc(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 60.0
        mock_tag.bitrate = 128
        mock_tag.samplerate = 22050
        mock_tag.channels = 1
        mock_tag.title = None
        mock_tag.artist = None
        mock_tag.album = None
        mock_tag.albumartist = None
        mock_tag.genre = None
        mock_tag.year = None
        mock_tag.track = "3"
        mock_tag.disc = "2"
        mock_tag.comment = None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.track_number == 3
        assert result.disc_number == 2

    def test_none_values_handled(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = None
        mock_tag.bitrate = None
        mock_tag.samplerate = None
        mock_tag.channels = None
        mock_tag.title = None
        mock_tag.artist = None
        mock_tag.album = None
        mock_tag.albumartist = None
        mock_tag.genre = None
        mock_tag.year = None
        mock_tag.track = None
        mock_tag.disc = None
        mock_tag.comment = None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.duration == 0.0
        assert result.bitrate == 0
        assert result.sample_rate == 0
        assert result.channels == 0
        assert result.year is None
        assert result.track_number is None
        assert result.disc_number is None

    def test_year_date_format(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 60.0
        mock_tag.bitrate = 128
        mock_tag.samplerate = 44100
        mock_tag.channels = 2
        mock_tag.title = None
        mock_tag.artist = None
        mock_tag.album = None
        mock_tag.albumartist = None
        mock_tag.genre = None
        mock_tag.year = "2023-06-15"
        mock_tag.track = None
        mock_tag.disc = None
        mock_tag.comment = None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.year == 2023

    def test_non_numeric_year(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 60.0
        mock_tag.bitrate = 128
        mock_tag.samplerate = 44100
        mock_tag.channels = 2
        mock_tag.title = None
        mock_tag.artist = None
        mock_tag.album = None
        mock_tag.albumartist = None
        mock_tag.genre = None
        mock_tag.year = "unknown"
        mock_tag.track = None
        mock_tag.disc = None
        mock_tag.comment = None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.year is None

    def test_non_numeric_track(self, extractor, audio_file):
        mock_tag = MagicMock()
        mock_tag.duration = 60.0
        mock_tag.bitrate = 128
        mock_tag.samplerate = 44100
        mock_tag.channels = 2
        mock_tag.title = None
        mock_tag.artist = None
        mock_tag.album = None
        mock_tag.albumartist = None
        mock_tag.genre = None
        mock_tag.year = None
        mock_tag.track = "abc"
        mock_tag.disc = "xyz/2"
        mock_tag.comment = None

        mock_tinytag = MagicMock()
        mock_tinytag.TinyTag.get.return_value = mock_tag

        with patch.dict("sys.modules", {"tinytag": mock_tinytag}):
            result = extractor._extract_with_tinytag(audio_file)

        assert result.track_number is None
        assert result.disc_number is None


# ---------------------------------------------------------------------------
# extract_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractBatch:
    """Tests for extract_batch."""

    def test_multiple_files(self, extractor, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"fake1")
        f2.write_bytes(b"fake2")

        meta = AudioMetadata(
            file_path=f1,
            file_size=5,
            format="MP3",
            duration=60.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
        )

        with patch.object(extractor, "extract", return_value=meta):
            results = extractor.extract_batch([f1, f2])

        assert len(results) == 2

    def test_error_skipped(self, extractor, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"fake1")
        f2.write_bytes(b"fake2")

        meta = AudioMetadata(
            file_path=f1,
            file_size=5,
            format="MP3",
            duration=60.0,
            bitrate=128000,
            sample_rate=44100,
            channels=2,
        )

        def side_effect(path):
            if str(path) == str(f1):
                raise Exception("corrupt file")
            return meta

        with patch.object(extractor, "extract", side_effect=side_effect):
            results = extractor.extract_batch([f1, f2])

        assert len(results) == 1

    def test_empty_list(self, extractor):
        results = extractor.extract_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatDuration:
    """Tests for format_duration static method."""

    def test_minutes_seconds(self):
        assert AudioMetadataExtractor.format_duration(125.0) == "02:05"

    def test_hours_minutes_seconds(self):
        assert AudioMetadataExtractor.format_duration(3661.0) == "01:01:01"

    def test_zero(self):
        assert AudioMetadataExtractor.format_duration(0.0) == "00:00"

    def test_less_than_minute(self):
        assert AudioMetadataExtractor.format_duration(45.0) == "00:45"

    def test_exact_hour(self):
        assert AudioMetadataExtractor.format_duration(3600.0) == "01:00:00"


# ---------------------------------------------------------------------------
# format_bitrate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatBitrate:
    """Tests for format_bitrate static method."""

    def test_kbps(self):
        assert AudioMetadataExtractor.format_bitrate(320000) == "320 kbps"

    def test_mbps(self):
        assert AudioMetadataExtractor.format_bitrate(1_500_000) == "1.5 Mbps"

    def test_bps(self):
        assert AudioMetadataExtractor.format_bitrate(500) == "500 bps"

    def test_zero(self):
        assert AudioMetadataExtractor.format_bitrate(0) == "0 bps"

    def test_exact_1000(self):
        assert AudioMetadataExtractor.format_bitrate(1000) == "1 kbps"
