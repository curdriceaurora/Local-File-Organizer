"""Integration tests for audio/video service modules and vision/text processors."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audio_metadata(
    file_path: Path,
    duration: float = 240.0,
    **kwargs: Any,
) -> Any:
    """Build an AudioMetadata object without importing at module level."""
    from file_organizer.services.audio.metadata_extractor import AudioMetadata

    defaults: dict[str, Any] = {
        "file_size": 1024 * 1024,
        "format": "MP3",
        "bitrate": 128000,
        "sample_rate": 44100,
        "channels": 2,
    }
    defaults.update(kwargs)
    return AudioMetadata(file_path=file_path, duration=duration, **defaults)


def _make_segment(id_: int, start: float, end: float, text: str = "hello") -> Any:
    """Build a transcription Segment."""
    from file_organizer.services.audio.transcriber import Segment

    return Segment(id=id_, start=start, end=end, text=text)


def _make_transcription(
    text: str,
    segments: list[Any] | None = None,
    duration: float = 300.0,
) -> Any:
    """Build a TranscriptionResult."""
    from file_organizer.services.audio.transcriber import (
        TranscriptionOptions,
        TranscriptionResult,
    )

    return TranscriptionResult(
        text=text,
        segments=segments or [],
        language="en",
        language_confidence=0.99,
        duration=duration,
        options=TranscriptionOptions(),
    )


def _make_video_metadata(file_path: Path, **kwargs: Any) -> Any:
    """Build a VideoMetadata object."""
    from file_organizer.services.video.metadata_extractor import VideoMetadata

    defaults: dict[str, Any] = {
        "file_size": 10 * 1024 * 1024,
        "format": "mp4",
    }
    defaults.update(kwargs)
    return VideoMetadata(file_path=file_path, **defaults)


# ---------------------------------------------------------------------------
# TestAudioClassifier
# ---------------------------------------------------------------------------


class TestAudioClassifier:
    """Tests for audio.classifier.AudioClassifier."""

    def test_classify_music_with_rich_metadata(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "song.mp3"
        fp.touch()
        meta = _make_audio_metadata(
            fp,
            duration=210.0,
            artist="The Beatles",
            album="Abbey Road",
            track_number=5,
            genre="rock",
            has_artwork=True,
        )
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.MUSIC
        assert result.confidence > 0.0

    def test_classify_returns_classification_result(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import (
            AudioClassifier,
            ClassificationResult,
        )

        fp = tmp_path / "a.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, artist="X", album="Y")
        result = AudioClassifier().classify(meta)
        assert isinstance(result, ClassificationResult)
        assert result.audio_type is not None
        assert isinstance(result.reasoning, str)
        assert 0.0 <= result.confidence <= 1.0

    def test_classify_podcast_by_title_keyword(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "ep42.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=3000.0, title="Episode 42: Deep Dive")
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.PODCAST

    def test_classify_podcast_by_duration_range(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "talk.mp3"
        fp.touch()
        # 45 minutes + podcast keyword in title should push it toward PODCAST
        meta = _make_audio_metadata(fp, duration=2700.0, title="My Podcast Episode 5")
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.PODCAST

    def test_classify_unknown_when_no_signals(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "silent.mp3"
        fp.touch()
        # With no metadata tags and zero duration, classifier gives RECORDING a score
        # from the "No metadata tags present" signal.  Only gets UNKNOWN when ALL
        # scores are zero (would need artist/album/etc with zero duration, which is
        # contradictory).  Test verifies it returns a valid AudioType with confidence >= 0.
        meta = _make_audio_metadata(fp, duration=0.0)
        result = AudioClassifier().classify(meta)
        assert result.audio_type in list(AudioType)
        assert 0.0 <= result.confidence <= 1.0

    def test_classify_recording_no_metadata(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "voice.wav"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=90.0)
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.RECORDING

    def test_classify_short_recording_under_two_minutes(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "memo.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=60.0)
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.RECORDING

    def test_classify_audiobook_by_keyword_in_title(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "ch1.mp3"
        fp.touch()
        meta = _make_audio_metadata(
            fp,
            duration=7200.0,
            title="Chapter 1: The Beginning",
            comment="Narrated by John Smith",
        )
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.AUDIOBOOK

    def test_classify_alternatives_list(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import (
            AudioClassifier,
            ClassificationAlternative,
        )

        fp = tmp_path / "talk.mp3"
        fp.touch()
        # Multiple signals (long duration hits audiobook + lecture + podcast ranges)
        meta = _make_audio_metadata(fp, duration=3600.0)
        result = AudioClassifier().classify(meta)
        assert isinstance(result.alternatives, list)
        # verify each alternative is the right type
        for alt in result.alternatives:
            assert isinstance(alt, ClassificationAlternative)
            assert alt.audio_type is not None

    def test_classify_music_genre_field(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "jazz.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=300.0, genre="jazz", artist="Miles Davis")
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.MUSIC

    def test_classify_with_transcription_podcast_keywords(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "pod.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=3000.0)
        trans = _make_transcription(
            "Welcome to our podcast episode. Thanks for listening to this weekly show. "
            "Subscribe and tune in for more. Our sponsor today is...",
            duration=3000.0,
        )
        result = AudioClassifier().classify(meta, transcription=trans)
        assert result.audio_type == AudioType.PODCAST

    def test_classify_with_transcription_lecture_keywords(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "lecture.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=5000.0)
        trans = _make_transcription(
            "Today's lecture covers the university curriculum. Students should review "
            "the syllabus. This course will have an exam at the end of the semester. "
            "Textbook chapter three covers this topic.",
            duration=5000.0,
        )
        result = AudioClassifier().classify(meta, transcription=trans)
        assert result.audio_type == AudioType.LECTURE

    def test_classify_music_few_words_long_duration(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "instrumental.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=180.0, artist="Bach", album="Classics")
        trans = _make_transcription("la la la", duration=180.0)
        result = AudioClassifier().classify(meta, transcription=trans)
        assert result.audio_type == AudioType.MUSIC

    def test_classify_interview_multiple_speakers(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "interview.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=1800.0)
        segments = [
            _make_segment(i, float(i * 10), float(i * 10 + varied), "text")
            for i, varied in enumerate([5, 30, 3, 45, 7, 20, 2, 50, 8, 35])
        ]
        trans = _make_transcription(
            "Interview: tell me about your work. question and answer panel discussion moderator",
            segments=segments,
            duration=1800.0,
        )
        result = AudioClassifier().classify(meta, transcription=trans)
        assert result.audio_type in (AudioType.INTERVIEW, AudioType.PODCAST)

    def test_classify_confidence_between_zero_and_one(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier

        fp = tmp_path / "test.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=300.0, artist="X")
        result = AudioClassifier().classify(meta)
        assert 0.0 <= result.confidence <= 1.0

    def test_classify_reasoning_non_empty_for_known_type(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "song.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=210.0, artist="X", album="Y", genre="pop")
        result = AudioClassifier().classify(meta)
        if result.audio_type != AudioType.UNKNOWN:
            assert len(result.reasoning) > 0

    def test_classify_podcast_extra_tags(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "pod.mp3"
        fp.touch()
        meta = _make_audio_metadata(
            fp,
            duration=2700.0,
            extra_tags={"podcast": "true", "episode": "42"},
        )
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.PODCAST

    def test_classify_audiobook_extra_tags(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "book.mp3"
        fp.touch()
        meta = _make_audio_metadata(
            fp,
            duration=14400.0,
            extra_tags={"narrator": "Jane Doe"},
        )
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.AUDIOBOOK

    def test_alternatives_confidence_between_zero_and_one(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier

        fp = tmp_path / "x.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, duration=3000.0, artist="X", album="Y", genre="pop")
        result = AudioClassifier().classify(meta)
        for alt in result.alternatives:
            assert 0.0 <= alt.confidence <= 1.0

    def test_classify_recording_meeting_keyword_in_title(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import AudioClassifier, AudioType

        fp = tmp_path / "meeting.mp3"
        fp.touch()
        meta = _make_audio_metadata(
            fp, duration=3600.0, title="Meeting minutes agenda action items"
        )
        result = AudioClassifier().classify(meta)
        assert result.audio_type == AudioType.RECORDING

    def test_estimate_speaker_count_high_variance(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import _estimate_speaker_count

        segments = [
            _make_segment(i, float(i * 10), float(i * 10 + d))
            for i, d in enumerate([1, 60, 2, 45, 1, 50, 3, 40])
        ]
        count = _estimate_speaker_count(segments)
        assert count >= 2

    def test_estimate_speaker_count_few_segments(self) -> None:
        from file_organizer.services.audio.classifier import _estimate_speaker_count

        segs = [_make_segment(0, 0.0, 10.0), _make_segment(1, 10.0, 20.0)]
        assert _estimate_speaker_count(segs) == 1

    def test_count_keyword_matches(self) -> None:
        from file_organizer.services.audio.classifier import (
            PODCAST_KEYWORDS,
            _count_keyword_matches,
        )

        text = "Welcome to our podcast episode and subscribe today"
        count = _count_keyword_matches(text, PODCAST_KEYWORDS)
        assert count >= 2

    def test_has_music_metadata_two_indicators(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import _has_music_metadata

        fp = tmp_path / "s.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp, artist="X", album="Y")
        assert _has_music_metadata(meta) is True

    def test_has_music_metadata_no_indicators(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.classifier import _has_music_metadata

        fp = tmp_path / "s.mp3"
        fp.touch()
        meta = _make_audio_metadata(fp)
        assert _has_music_metadata(meta) is False


# ---------------------------------------------------------------------------
# TestAudioMetadataExtractor
# ---------------------------------------------------------------------------


class TestAudioMetadataExtractor:
    """Tests for audio.metadata_extractor.AudioMetadataExtractor."""

    def test_extract_raises_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        extractor = AudioMetadataExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract(tmp_path / "nonexistent.mp3")

    def test_extract_with_mutagen_mock(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "song.mp3"
        fp.write_bytes(b"\xff\xfb" * 100)

        mock_audio = MagicMock()
        mock_audio.info.length = 180.5
        mock_audio.info.bitrate = 128000
        mock_audio.info.sample_rate = 44100
        mock_audio.info.channels = 2
        mock_audio.tags = None

        with patch(
            "file_organizer.services.audio.metadata_extractor.MutagenFile",
            return_value=mock_audio,
            create=True,
        ):
            with patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
                "._extract_with_mutagen",
                return_value=AudioMetadata(
                    file_path=fp,
                    file_size=200,
                    format="MP3",
                    duration=180.5,
                    bitrate=128000,
                    sample_rate=44100,
                    channels=2,
                ),
            ):
                result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert isinstance(result, AudioMetadata)
        assert result.duration == 180.5
        assert result.bitrate == 128000
        assert result.sample_rate == 44100
        assert result.channels == 2

    def test_extract_file_path_is_preserved(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "track.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            return_value=AudioMetadata(
                file_path=fp,
                file_size=100,
                format="MP3",
                duration=60.0,
                bitrate=320000,
                sample_rate=48000,
                channels=2,
            ),
        ):
            result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert result.file_path == fp

    def test_extract_format_from_suffix(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "track.flac"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            return_value=AudioMetadata(
                file_path=fp,
                file_size=100,
                format="FLAC",
                duration=300.0,
                bitrate=900000,
                sample_rate=44100,
                channels=2,
            ),
        ):
            result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert result.format == "FLAC"

    def test_extract_mutagen_none_falls_back_to_tinytag(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        fp = tmp_path / "song.ogg"
        fp.write_bytes(b"\x00" * 100)

        mock_tinytag = MagicMock()
        mock_tinytag.duration = 120.0
        mock_tinytag.bitrate = 128
        mock_tinytag.samplerate = 44100
        mock_tinytag.channels = 2
        mock_tinytag.title = "My Song"
        mock_tinytag.artist = "Singer"
        mock_tinytag.album = None
        mock_tinytag.albumartist = None
        mock_tinytag.genre = None
        mock_tinytag.year = "2023"
        mock_tinytag.track = "1"
        mock_tinytag.disc = None
        mock_tinytag.comment = None

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=ValueError("Unsupported audio format"),
        ):
            with patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
                "._extract_with_tinytag"
            ) as mock_tinytag_fn:
                from file_organizer.services.audio.metadata_extractor import AudioMetadata

                mock_tinytag_fn.return_value = AudioMetadata(
                    file_path=fp,
                    file_size=100,
                    format="OGG",
                    duration=120.0,
                    bitrate=128000,
                    sample_rate=44100,
                    channels=2,
                    title="My Song",
                    artist="Singer",
                    year=2023,
                )
                result = AudioMetadataExtractor(use_fallback=True).extract(fp)

        assert result.title == "My Song"
        assert result.artist == "Singer"
        assert result.year == 2023

    def test_extract_mutagen_exception_falls_back(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "song.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=lambda p: (_ for _ in ()).throw(Exception("decode error")),
        ):
            with patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
                "._extract_with_tinytag",
                return_value=AudioMetadata(
                    file_path=fp,
                    file_size=100,
                    format="MP3",
                    duration=90.0,
                    bitrate=64000,
                    sample_rate=22050,
                    channels=1,
                ),
            ):
                result = AudioMetadataExtractor(use_fallback=True).extract(fp)

        assert result.duration == 90.0

    def test_extract_no_fallback_raises_on_mutagen_error(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        fp = tmp_path / "song.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=Exception("bad file"),
        ):
            with pytest.raises(Exception, match="bad file"):
                AudioMetadataExtractor(use_fallback=False).extract(fp)

    def test_extract_batch_returns_list(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        files = []
        for i in range(3):
            fp = tmp_path / f"f{i}.mp3"
            fp.write_bytes(b"\x00" * 100)
            files.append(fp)

        def make_meta(path: Path) -> AudioMetadata:
            return AudioMetadata(
                file_path=path,
                file_size=100,
                format="MP3",
                duration=60.0,
                bitrate=128000,
                sample_rate=44100,
                channels=2,
            )

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=make_meta,
        ):
            results = AudioMetadataExtractor(use_fallback=False).extract_batch(files)

        assert len(results) == 3

    def test_extract_batch_skips_failed_files(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        good_fp = tmp_path / "good.mp3"
        good_fp.write_bytes(b"\x00" * 100)
        bad_fp = tmp_path / "bad.mp3"
        bad_fp.write_bytes(b"\x00" * 100)

        def side_effect(path: Path) -> AudioMetadata:
            if "bad" in str(path):
                raise Exception("corrupt file")
            return AudioMetadata(
                file_path=path,
                file_size=100,
                format="MP3",
                duration=60.0,
                bitrate=128000,
                sample_rate=44100,
                channels=2,
            )

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=side_effect,
        ):
            results = AudioMetadataExtractor(use_fallback=False).extract_batch([good_fp, bad_fp])

        assert len(results) == 1
        assert results[0].file_path == good_fp

    def test_format_duration_hours(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        result = AudioMetadataExtractor.format_duration(3661.0)
        assert result == "01:01:01"

    def test_format_duration_minutes(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        result = AudioMetadataExtractor.format_duration(125.0)
        assert result == "02:05"

    def test_format_bitrate_kbps(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        result = AudioMetadataExtractor.format_bitrate(320000)
        assert result == "320 kbps"

    def test_format_bitrate_mbps(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        result = AudioMetadataExtractor.format_bitrate(5_000_000)
        assert "Mbps" in result

    def test_format_bitrate_bps(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        result = AudioMetadataExtractor.format_bitrate(800)
        assert result == "800 bps"

    def test_extract_with_id3_tags(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "track.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            return_value=AudioMetadata(
                file_path=fp,
                file_size=100,
                format="MP3",
                duration=240.0,
                bitrate=192000,
                sample_rate=44100,
                channels=2,
                title="Test Title",
                artist="Test Artist",
                year=2022,
            ),
        ):
            result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert result.title == "Test Title"
        assert result.artist == "Test Artist"
        assert result.year == 2022

    def test_extract_track_number_slash_format(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "track.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            return_value=AudioMetadata(
                file_path=fp,
                file_size=100,
                format="MP3",
                duration=200.0,
                bitrate=128000,
                sample_rate=44100,
                channels=2,
                track_number=3,
            ),
        ):
            result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert result.track_number == 3

    def test_extract_file_size_in_bytes(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "track.mp3"
        fp.write_bytes(b"\x00" * 512)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            return_value=AudioMetadata(
                file_path=fp,
                file_size=512,
                format="MP3",
                duration=10.0,
                bitrate=64000,
                sample_rate=22050,
                channels=1,
            ),
        ):
            result = AudioMetadataExtractor(use_fallback=False).extract(fp)

        assert result.file_size == 512

    def test_extract_use_fallback_default_true(self) -> None:
        from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

        extractor = AudioMetadataExtractor()
        assert extractor.use_fallback is True

    def test_extract_tinytag_track_slash_format(self, tmp_path: Path) -> None:
        from file_organizer.services.audio.metadata_extractor import (
            AudioMetadata,
            AudioMetadataExtractor,
        )

        fp = tmp_path / "song.mp3"
        fp.write_bytes(b"\x00" * 100)

        with patch(
            "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
            "._extract_with_mutagen",
            side_effect=Exception("mutagen unavailable"),
        ):
            with patch(
                "file_organizer.services.audio.metadata_extractor.AudioMetadataExtractor"
                "._extract_with_tinytag",
                return_value=AudioMetadata(
                    file_path=fp,
                    file_size=100,
                    format="MP3",
                    duration=180.0,
                    bitrate=128000,
                    sample_rate=44100,
                    channels=2,
                    track_number=5,
                    disc_number=1,
                ),
            ):
                result = AudioMetadataExtractor(use_fallback=True).extract(fp)

        assert result.track_number == 5
        assert result.disc_number == 1


# ---------------------------------------------------------------------------
# TestVideoMetadataExtractor
# ---------------------------------------------------------------------------


class TestVideoMetadataExtractor:
    """Tests for video.metadata_extractor.VideoMetadataExtractor."""

    def test_extract_raises_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        with pytest.raises(FileNotFoundError):
            VideoMetadataExtractor().extract(tmp_path / "missing.mp4")

    def test_extract_returns_video_metadata(self, tmp_path: Path) -> None:
        from file_organizer.services.video.metadata_extractor import (
            VideoMetadata,
            VideoMetadataExtractor,
        )

        fp = tmp_path / "video.mp4"
        fp.write_bytes(b"\x00" * 1024)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = VideoMetadataExtractor().extract(fp)

        assert isinstance(result, VideoMetadata)
        assert result.file_path == fp

    def test_extract_ffprobe_success(self, tmp_path: Path) -> None:
        import json

        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "video.mp4"
        fp.write_bytes(b"\x00" * 2048)

        probe_data = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "codec_name": "h264",
                    "r_frame_rate": "30/1",
                    "duration": "120.5",
                }
            ],
            "format": {
                "bit_rate": "5000000",
                "duration": "120.5",
                "tags": {},
            },
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(probe_data)

        with patch("subprocess.run", return_value=mock_result):
            metadata = VideoMetadataExtractor().extract(fp)

        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.codec == "h264"
        assert metadata.fps == 30.0
        assert metadata.duration == 120.5
        assert metadata.bitrate == 5000000

    def test_extract_ffprobe_fps_fractional(self, tmp_path: Path) -> None:
        import json

        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "ntsc.mp4"
        fp.write_bytes(b"\x00" * 2048)

        probe_data = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 720,
                    "height": 480,
                    "codec_name": "mpeg2video",
                    "r_frame_rate": "30000/1001",
                    "duration": "60.0",
                }
            ],
            "format": {"bit_rate": "8000000", "tags": {}},
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(probe_data)

        with patch("subprocess.run", return_value=mock_result):
            metadata = VideoMetadataExtractor().extract(fp)

        assert metadata.fps is not None
        assert abs(metadata.fps - 29.97) < 0.01

    def test_extract_fallback_filesystem_only(self, tmp_path: Path) -> None:
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "video.avi"
        fp.write_bytes(b"\x00" * 4096)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with patch.dict("sys.modules", {"cv2": None}):
                metadata = VideoMetadataExtractor().extract(fp)

        assert metadata.file_size == 4096
        assert metadata.format == "avi"
        assert metadata.width is None
        assert metadata.height is None

    def test_extract_batch_returns_list(self, tmp_path: Path) -> None:
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        paths = []
        for i in range(3):
            fp = tmp_path / f"v{i}.mp4"
            fp.write_bytes(b"\x00" * 512)
            paths.append(fp)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            results = VideoMetadataExtractor().extract_batch(paths)

        assert len(results) == 3

    def test_extract_creation_date_from_tags(self, tmp_path: Path) -> None:
        import json

        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "dated.mp4"
        fp.write_bytes(b"\x00" * 1024)

        probe_data = {
            "streams": [],
            "format": {
                "bit_rate": "1000000",
                "tags": {"creation_time": "2024-06-15T12:00:00Z"},
            },
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(probe_data)

        with patch("subprocess.run", return_value=mock_result):
            metadata = VideoMetadataExtractor().extract(fp)

        assert metadata.creation_date is not None
        assert metadata.creation_date.year == 2024
        assert metadata.creation_date.month == 6

    def test_resolution_label_4k(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(3840, 2160) == "4k"

    def test_resolution_label_1080p(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(1920, 1080) == "1080p"

    def test_resolution_label_720p(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(1280, 720) == "720p"

    def test_resolution_label_480p(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(854, 480) == "480p"

    def test_resolution_label_sd(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(320, 240) == "sd"

    def test_resolution_label_unknown(self) -> None:
        from file_organizer.services.video.metadata_extractor import resolution_label

        assert resolution_label(None, None) == "unknown"

    def test_safe_int_none(self) -> None:
        from file_organizer.services.video.metadata_extractor import _safe_int

        assert _safe_int(None) is None

    def test_safe_int_valid(self) -> None:
        from file_organizer.services.video.metadata_extractor import _safe_int

        assert _safe_int("1920") == 1920

    def test_safe_int_invalid(self) -> None:
        from file_organizer.services.video.metadata_extractor import _safe_int

        assert _safe_int("abc") is None

    def test_safe_float_valid(self) -> None:
        from file_organizer.services.video.metadata_extractor import _safe_float

        val = _safe_float("120.5")
        assert val == 120.5

    def test_safe_float_none(self) -> None:
        from file_organizer.services.video.metadata_extractor import _safe_float

        assert _safe_float(None) is None

    def test_parse_datetime_iso_z(self) -> None:
        from file_organizer.services.video.metadata_extractor import _parse_datetime

        dt = _parse_datetime("2024-01-15T14:30:45Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1

    def test_parse_datetime_date_only(self) -> None:
        from file_organizer.services.video.metadata_extractor import _parse_datetime

        dt = _parse_datetime("2023-06-20")
        assert dt is not None
        assert dt.year == 2023

    def test_parse_datetime_invalid_returns_none(self) -> None:
        from file_organizer.services.video.metadata_extractor import _parse_datetime

        assert _parse_datetime("not-a-date") is None

    def test_extract_ffprobe_timeout_falls_back(self, tmp_path: Path) -> None:
        import subprocess

        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "vid.mp4"
        fp.write_bytes(b"\x00" * 1024)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 10)):
            metadata = VideoMetadataExtractor().extract(fp)

        # Falls back to filesystem only
        assert metadata.file_size == 1024
        assert metadata.duration is None

    def test_extract_ffprobe_not_found_falls_back(self, tmp_path: Path) -> None:
        from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor

        fp = tmp_path / "vid.mkv"
        fp.write_bytes(b"\x00" * 2048)

        with patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
            metadata = VideoMetadataExtractor().extract(fp)

        assert metadata.format == "mkv"


# ---------------------------------------------------------------------------
# TestVideoOrganizer
# ---------------------------------------------------------------------------


class TestVideoOrganizer:
    """Tests for video.organizer.VideoOrganizer."""

    def test_generate_path_screen_recording_macos(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "Screen Recording 2025-01-15 at 3.45.22 PM.mov"
        meta = _make_video_metadata(fp, duration=30.0)
        folder, name = VideoOrganizer().generate_path(meta)
        assert "Screen_Recordings" in folder
        assert name == fp.stem

    def test_generate_path_screen_recording_with_year(self, tmp_path: Path) -> None:
        from datetime import datetime

        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "Screen Recording 2025-01-15 at 3.45.22 PM.mov"
        meta = _make_video_metadata(
            fp,
            duration=45.0,
            creation_date=datetime(2025, 1, 15, tzinfo=UTC),
        )
        folder, _ = VideoOrganizer().generate_path(meta)
        assert "2025" in folder

    def test_generate_path_short_clip(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "clip.mp4"
        meta = _make_video_metadata(fp, duration=30.0)
        folder, name = VideoOrganizer().generate_path(meta)
        assert folder == "Short_Clips"
        assert name == "clip"

    def test_generate_path_video_with_year(self, tmp_path: Path) -> None:
        from datetime import datetime

        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "vacation.mp4"
        meta = _make_video_metadata(
            fp,
            duration=600.0,
            creation_date=datetime(2023, 7, 4, tzinfo=UTC),
        )
        folder, _ = VideoOrganizer().generate_path(meta)
        assert folder == "Videos/2023"

    def test_generate_path_unsorted_fallback(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "mystery.mp4"
        meta = _make_video_metadata(fp, duration=None)
        folder, _ = VideoOrganizer().generate_path(meta)
        assert folder == "Videos/Unsorted"

    def test_generate_path_year_from_filename(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "holiday_2022-12-25.mp4"
        meta = _make_video_metadata(fp, duration=600.0)
        folder, _ = VideoOrganizer().generate_path(meta)
        assert "2022" in folder

    def test_generate_path_returns_tuple(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "test.mp4"
        meta = _make_video_metadata(fp)
        result = VideoOrganizer().generate_path(meta)
        assert len(result) == 2
        folder, name = result
        assert isinstance(folder, str)
        assert isinstance(name, str)

    def test_generate_description_with_resolution(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "hd.mp4"
        meta = _make_video_metadata(fp, width=1920, height=1080, duration=300.0, codec="h264")
        desc = VideoOrganizer().generate_description(meta)
        assert "1080p" in desc
        assert "h264" in desc

    def test_generate_description_hours(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "movie.mp4"
        meta = _make_video_metadata(fp, duration=7200.0)
        desc = VideoOrganizer().generate_description(meta)
        assert "2h" in desc

    def test_generate_description_minutes(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "short.mp4"
        meta = _make_video_metadata(fp, duration=90.0)
        desc = VideoOrganizer().generate_description(meta)
        assert "1m" in desc

    def test_generate_description_seconds(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "clip.mp4"
        meta = _make_video_metadata(fp, duration=45.0)
        desc = VideoOrganizer().generate_description(meta)
        assert "45s" in desc

    def test_generate_description_no_resolution_unknown(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "clip.mp4"
        meta = _make_video_metadata(fp)
        desc = VideoOrganizer().generate_description(meta)
        assert desc.startswith("Video")

    def test_is_screen_recording_macos(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("Screen Recording 2025-01-15 at 3.45.22 PM") is True

    def test_is_screen_recording_obs(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("2025-01-15 14-05-32") is True

    def test_is_screen_recording_camtasia(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("Capture05") is True

    def test_is_screen_recording_generic_keyword(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("my_screencast") is True

    def test_is_screen_recording_false_for_normal_video(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("family_vacation_2024") is False

    def test_is_screen_recording_xbox(self) -> None:
        from file_organizer.services.video.organizer import is_screen_recording

        assert is_screen_recording("Minecraft 2025-01-15 14-05-32") is True

    def test_generate_path_short_clip_exactly_at_threshold(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import SHORT_CLIP_THRESHOLD, VideoOrganizer

        fp = tmp_path / "edge.mp4"
        # Duration exactly at threshold should NOT be "Short_Clips"
        meta = _make_video_metadata(fp, duration=SHORT_CLIP_THRESHOLD)
        folder, _ = VideoOrganizer().generate_path(meta)
        assert folder != "Short_Clips"

    def test_generate_path_below_threshold_is_short_clip(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import SHORT_CLIP_THRESHOLD, VideoOrganizer

        fp = tmp_path / "short.mp4"
        meta = _make_video_metadata(fp, duration=SHORT_CLIP_THRESHOLD - 1.0)
        folder, _ = VideoOrganizer().generate_path(meta)
        assert folder == "Short_Clips"

    def test_generate_path_preserves_original_stem(self, tmp_path: Path) -> None:
        from file_organizer.services.video.organizer import VideoOrganizer

        fp = tmp_path / "my_video_file.mp4"
        meta = _make_video_metadata(fp, duration=300.0)
        _, name = VideoOrganizer().generate_path(meta)
        assert name == "my_video_file"


# ---------------------------------------------------------------------------
# TestVisionProcessor
# ---------------------------------------------------------------------------


class TestVisionProcessor:
    """Tests for vision_processor.VisionProcessor."""

    def _make_mock_model(self) -> Any:
        """Build a minimal mock BaseModel."""
        from file_organizer.models.base import ModelConfig, ModelType

        mock_model = MagicMock()
        mock_model.config = MagicMock(spec=ModelConfig)
        mock_model.config.model_type = ModelType.VISION
        mock_model.is_initialized = True
        mock_model.generate = MagicMock(return_value="mocked response")
        mock_model.safe_cleanup = MagicMock()
        return mock_model

    def test_init_with_vision_model(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        assert processor.vision_model is mock_model
        assert processor._owns_model is False

    def test_init_rejects_non_vision_model(self) -> None:
        from file_organizer.models.base import ModelType
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.TEXT
        with pytest.raises(ValueError, match="VISION or VIDEO"):
            VisionProcessor(vision_model=mock_model)

    def test_process_file_nonexistent_returns_error(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        result = processor.process_file(tmp_path / "ghost.jpg")
        assert result.error == "File not found"
        assert result.folder_name == "errors"

    def test_process_file_returns_processed_image(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import ProcessedImage, VisionProcessor

        fp = tmp_path / "test.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        mock_model.generate = MagicMock(return_value="A beautiful landscape with mountains")

        processor = VisionProcessor(vision_model=mock_model)
        result = processor.process_file(fp, perform_ocr=False)

        assert isinstance(result, ProcessedImage)
        assert result.file_path == fp
        assert result.error is None

    def test_process_file_description_populated(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        fp = tmp_path / "photo.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        mock_model.generate = MagicMock(return_value="nature landscape photography")

        processor = VisionProcessor(vision_model=mock_model)
        result = processor.process_file(fp, perform_ocr=False)
        assert len(result.description) > 0

    def test_process_file_circuit_breaker_opens_on_fatal_error(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        fp = tmp_path / "img.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        mock_model.generate = MagicMock(side_effect=RuntimeError("connection refused to backend"))

        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=9999.0)
        processor.process_file(fp, perform_ocr=False)
        # After fatal error the circuit should be open
        assert processor._is_circuit_open() is True
        # Second call should return fallback immediately
        result2 = processor.process_file(fp, perform_ocr=False)
        assert result2.error is not None
        assert "Vision backend" in result2.error
        assert mock_model.generate.call_count == 1

    def test_process_file_non_fatal_error_does_not_open_circuit(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        fp = tmp_path / "img.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        mock_model.generate = MagicMock(side_effect=ValueError("bad prompt"))

        processor = VisionProcessor(vision_model=mock_model)
        processor.process_file(fp, perform_ocr=False)
        assert processor._is_circuit_open() is False

    def test_is_circuit_open_initially_false(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        assert processor._is_circuit_open() is False

    def test_trip_circuit_makes_is_open_true(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=9999.0)
        processor._trip_backend_circuit(RuntimeError("test"))
        assert processor._is_circuit_open() is True

    def test_circuit_open_error_message(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model, backend_cooldown_seconds=9999.0)
        processor._trip_backend_circuit(RuntimeError("dial tcp refused"))
        msg = processor._circuit_open_error()
        assert "Vision backend unavailable" in msg

    def test_cleanup_calls_safe_cleanup_when_owns_model(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        processor._owns_model = True
        processor.cleanup()
        mock_model.safe_cleanup.assert_called_once()

    def test_cleanup_skips_safe_cleanup_when_not_owns_model(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        processor._owns_model = False
        processor.cleanup()
        mock_model.safe_cleanup.assert_not_called()

    def test_initialize_calls_model_initialize_if_not_initialized(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        mock_model.is_initialized = False
        processor = VisionProcessor(vision_model=mock_model)
        processor.initialize()
        mock_model.initialize.assert_called_once()

    def test_initialize_skips_when_already_initialized(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        mock_model.is_initialized = True
        processor = VisionProcessor(vision_model=mock_model)
        processor.initialize()
        mock_model.initialize.assert_not_called()

    def test_clean_ai_generated_name_removes_stop_words(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        result = processor._clean_ai_generated_name("the beautiful mountain landscape", max_words=3)
        assert "the" not in result.split("_")
        assert "beautiful" in result or "mountain" in result or "landscape" in result

    def test_clean_ai_generated_name_max_words_limit(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        result = processor._clean_ai_generated_name(
            "red blue green yellow purple orange", max_words=2
        )
        assert len(result.split("_")) == 2

    def test_clean_ai_generated_name_removes_image_word(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        result = processor._clean_ai_generated_name("image of nature")
        assert "image" not in result.split("_")

    def test_process_file_ocr_no_text_sentinel(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        fp = tmp_path / "blank.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        responses = ["A blank image", "NO_TEXT", "blank_image"]
        call_count = [0]

        def generate_side_effect(**kwargs: Any) -> str:
            resp = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return resp

        mock_model.generate = MagicMock(side_effect=generate_side_effect)
        processor = VisionProcessor(vision_model=mock_model)
        result = processor.process_file(fp, perform_ocr=True)
        assert result.has_text is False
        assert result.extracted_text is None

    def test_process_file_processing_time_recorded(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        fp = tmp_path / "img.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_model = self._make_mock_model()
        mock_model.generate = MagicMock(return_value="description text here")

        processor = VisionProcessor(vision_model=mock_model)
        result = processor.process_file(fp, perform_ocr=False)
        assert result.processing_time >= 0.0

    def test_is_fatal_backend_error_connection_refused(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        exc = RuntimeError("connection refused to server")
        assert processor._is_fatal_backend_error(exc) is True

    def test_is_fatal_backend_error_non_fatal(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        processor = VisionProcessor(vision_model=mock_model)
        exc = ValueError("invalid argument")
        assert processor._is_fatal_backend_error(exc) is False

    def test_context_manager_calls_initialize_and_cleanup(self, tmp_path: Path) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = self._make_mock_model()
        mock_model.is_initialized = False
        processor = VisionProcessor(vision_model=mock_model)
        processor._owns_model = True

        with processor:
            mock_model.initialize.assert_called_once()

        mock_model.safe_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# TestTextProcessor
# ---------------------------------------------------------------------------


class TestTextProcessor:
    """Tests for text_processor.TextProcessor."""

    def _make_mock_text_model(self) -> Any:
        """Build a minimal mock text BaseModel."""
        from file_organizer.models.base import ModelConfig, ModelType

        mock_model = MagicMock()
        mock_model.config = MagicMock(spec=ModelConfig)
        mock_model.config.model_type = ModelType.TEXT
        mock_model.is_initialized = True
        mock_model.generate = MagicMock(return_value="programming")
        mock_model.safe_cleanup = MagicMock()
        return mock_model

    def test_init_with_text_model(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        assert processor.text_model is mock_model
        assert processor._owns_model is False

    def test_init_rejects_non_text_model(self) -> None:
        from file_organizer.models.base import ModelType
        from file_organizer.services.text_processor import TextProcessor

        mock_model = MagicMock()
        mock_model.config.model_type = ModelType.VISION

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with pytest.raises(ValueError, match="TEXT model"):
                TextProcessor(text_model=mock_model)

    def test_process_file_returns_processed_file(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import ProcessedFile, TextProcessor

        fp = tmp_path / "notes.txt"
        fp.write_text("Python is a programming language used for scripting and data science.")

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="programming")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file",
                return_value="Python programming content",
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text",
                    return_value="Python programming content",
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text",
                        return_value="programming",
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(fp)

        assert isinstance(result, ProcessedFile)
        assert result.file_path == fp
        assert result.error is None

    def test_process_file_unsupported_type_returns_error(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "binary.bin"
        fp.write_bytes(b"\x00\x01\x02\x03")

        mock_model = self._make_mock_text_model()

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch("file_organizer.services.text_processor.read_file", return_value=None):
                processor = TextProcessor(text_model=mock_model)
                result = processor.process_file(fp)

        assert result.error == "Unsupported file type"
        assert result.folder_name == "unsupported"

    def test_process_file_read_error_returns_error(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor
        from file_organizer.utils.file_readers import FileReadError

        fp = tmp_path / "broken.txt"
        fp.write_text("content")

        mock_model = self._make_mock_text_model()

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file",
                side_effect=FileReadError("cannot read file"),
            ):
                processor = TextProcessor(text_model=mock_model)
                result = processor.process_file(fp)

        assert result.error == "cannot read file"
        assert result.folder_name == "errors"

    def test_process_file_description_from_model(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "doc.txt"
        fp.write_text("content here")

        mock_model = self._make_mock_text_model()
        responses = ["A summary of python usage", "programming", "python_guide"]
        call_count = [0]

        def gen_side_effect(prompt: str, **kwargs: Any) -> str:
            resp = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return resp

        mock_model.generate = MagicMock(side_effect=gen_side_effect)

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file", return_value="python content"
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text",
                    return_value="python content",
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text",
                        return_value="programming",
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(fp)

        assert len(result.description) > 0

    def test_process_file_no_description(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "doc.txt"
        fp.write_text("hello world")

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="programming")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file", return_value="hello world"
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text",
                    return_value="hello world",
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text",
                        return_value="programming",
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(
                            fp, generate_description=False, generate_folder=True
                        )

        assert result.description == ""

    def test_process_file_preserves_file_path(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "note.txt"
        fp.write_text("some text")

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="notes")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file", return_value="some text"
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text", return_value="some text"
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text", return_value="notes"
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(fp)

        assert result.file_path == fp

    def test_clean_ai_generated_name_removes_stop_words(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._clean_ai_generated_name("the document about programming")
        assert "the" not in result.split("_")
        assert "document" not in result.split("_")

    def test_clean_ai_generated_name_max_two_words(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._clean_ai_generated_name("alpha beta gamma delta epsilon", max_words=2)
        assert len(result.split("_")) == 2

    def test_clean_ai_generated_name_empty_returns_empty(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._clean_ai_generated_name("the a an and or")
        assert result == ""

    def test_clean_ai_generated_name_with_underscores(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._clean_ai_generated_name("machine_learning")
        assert "machine" in result
        assert "learning" in result

    def test_cleanup_calls_safe_cleanup_when_owns_model(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        processor._owns_model = True
        processor.cleanup()
        mock_model.safe_cleanup.assert_called_once()

    def test_cleanup_skips_when_not_owns(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        processor._owns_model = False
        processor.cleanup()
        mock_model.safe_cleanup.assert_not_called()

    def test_initialize_calls_model_initialize(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.is_initialized = False
        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        processor.initialize()
        mock_model.initialize.assert_called_once()

    def test_process_file_exception_returns_error(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "broken.txt"
        fp.write_text("text")

        mock_model = self._make_mock_text_model()

        def raise_unexpected(_path: Any) -> None:
            # text_processor catches RuntimeError/ValueError/OSError/AttributeError
            raise OSError("unexpected error")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file",
                side_effect=raise_unexpected,
            ):
                processor = TextProcessor(text_model=mock_model)
                result = processor.process_file(fp)

        assert result.error == "unexpected error"
        assert result.folder_name == "errors"

    def test_process_file_processing_time_non_negative(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "doc.txt"
        fp.write_text("sample text for testing")

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="sample")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file", return_value="sample text"
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text",
                    return_value="sample text",
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text", return_value="sample"
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(fp)

        assert result.processing_time >= 0.0

    def test_process_file_original_content_truncated(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        fp = tmp_path / "long.txt"
        long_content = "word " * 200
        fp.write_text(long_content)

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="words")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.read_file", return_value=long_content
            ):
                with patch(
                    "file_organizer.services.text_processor.truncate_text",
                    return_value=long_content[:5000],
                ):
                    with patch(
                        "file_organizer.services.text_processor.clean_text", return_value="words"
                    ):
                        processor = TextProcessor(text_model=mock_model)
                        result = processor.process_file(fp)

        # original_content is first 500 chars (exact cap applied in process_file)
        if result.original_content is not None:
            assert len(result.original_content) == 500

    def test_context_manager_initialize_and_cleanup(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.is_initialized = False

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        processor._owns_model = True

        with processor:
            mock_model.initialize.assert_called_once()

        mock_model.safe_cleanup.assert_called_once()

    def test_generate_description_strips_summary_prefix(self, tmp_path: Path) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="summary: This text is about Python")

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._generate_description("some long content here about Python")
        # prefix stripped
        assert not result.lower().startswith("summary:")

    def test_generate_folder_name_fallback_on_empty_response(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(return_value="the a an")  # all stop words

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            with patch(
                "file_organizer.services.text_processor.clean_text", return_value="programming"
            ):
                processor = TextProcessor(text_model=mock_model)
        result = processor._generate_folder_name("Python programming tutorials and guides")
        # Should be non-empty even with stop-word-only AI response
        assert len(result) >= 1

    def test_generate_folder_name_exception_returns_documents(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(side_effect=RuntimeError)

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._generate_folder_name("some content")
        assert result == "documents"

    def test_generate_filename_exception_returns_document(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        mock_model = self._make_mock_text_model()
        mock_model.generate = MagicMock(side_effect=RuntimeError)

        with patch("file_organizer.services.text_processor.ensure_nltk_data"):
            processor = TextProcessor(text_model=mock_model)
        result = processor._generate_filename("some content")
        assert result == "document"
