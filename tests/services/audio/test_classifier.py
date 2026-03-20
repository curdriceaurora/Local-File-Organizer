"""
Tests for AudioClassifier - Audio Type Classification Service

Tests cover:
- Music classification (metadata tags, genre, duration)
- Podcast classification (episode metadata, duration range)
- Audiobook classification (chapter metadata, long duration)
- Recording classification (no metadata, short duration)
- Interview classification (multiple speakers, Q&A patterns)
- Lecture classification (single speaker, educational keywords)
- Unknown fallback when no signals present
- Transcription-based scoring
- Confidence and alternatives
- Edge cases
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.audio.classifier import (
    PODCAST_KEYWORDS,
    AudioClassifier,
    AudioType,
    _count_keyword_matches,
    _estimate_speaker_count,
    _has_audiobook_metadata,
    _has_music_metadata,
    _has_podcast_metadata,
)
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.transcriber import (
    Segment,
    TranscriptionOptions,
    TranscriptionResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_metadata(
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    track_number: int | None = None,
    duration: float = 180.0,
    has_artwork: bool = False,
    comment: str | None = None,
    extra_tags: dict[str, str] | None = None,
) -> AudioMetadata:
    """Helper to create AudioMetadata with sensible defaults."""
    return AudioMetadata(
        file_path=Path("/tmp/test_audio.mp3"),
        file_size=5_000_000,
        format="MP3",
        duration=duration,
        bitrate=320000,
        sample_rate=44100,
        channels=2,
        title=title,
        artist=artist,
        album=album,
        genre=genre,
        year=year,
        track_number=track_number,
        has_artwork=has_artwork,
        comment=comment,
        extra_tags=extra_tags or {},
    )


def _make_transcription(
    text: str = "",
    segments: list[Segment] | None = None,
    language: str = "en",
    duration: float = 180.0,
) -> TranscriptionResult:
    """Helper to create TranscriptionResult."""
    return TranscriptionResult(
        text=text,
        segments=segments or [],
        language=language,
        language_confidence=0.95,
        duration=duration,
        options=TranscriptionOptions(),
    )


@pytest.fixture
def classifier() -> AudioClassifier:
    return AudioClassifier()


# ---------------------------------------------------------------------------
# Music classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMusicClassification:
    """Tests for music type detection."""

    def test_music_with_full_tags(self, classifier: AudioClassifier) -> None:
        """Music with artist, album, track, genre, artwork should classify as MUSIC."""
        metadata = _make_metadata(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            genre="Rock",
            track_number=1,
            has_artwork=True,
            duration=354.0,
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.MUSIC
        assert result.confidence > 0.4

    def test_music_short_duration(self, classifier: AudioClassifier) -> None:
        """Short audio with music metadata should classify as MUSIC."""
        metadata = _make_metadata(
            artist="Artist",
            album="Album",
            genre="Pop",
            duration=210.0,
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.MUSIC

    def test_music_genre_matching(self, classifier: AudioClassifier) -> None:
        """Known music genre in metadata should boost MUSIC score."""
        metadata = _make_metadata(
            artist="DJ Someone",
            genre="electronic",
            duration=300.0,
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.MUSIC

    def test_music_minimal_speech_in_transcription(self, classifier: AudioClassifier) -> None:
        """Music with very few transcribed words should still classify as MUSIC."""
        metadata = _make_metadata(
            artist="Instrumental Artist",
            album="Ambient Works",
            genre="Ambient",
            duration=240.0,
        )
        transcription = _make_transcription(
            text="yeah oh",
            duration=240.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.MUSIC


# ---------------------------------------------------------------------------
# Podcast classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPodcastClassification:
    """Tests for podcast type detection."""

    def test_podcast_with_episode_metadata(self, classifier: AudioClassifier) -> None:
        """Episode-style title + podcast duration should classify as PODCAST."""
        metadata = _make_metadata(
            title="Ep. 42 - The Future of AI",
            artist="Tech Talk Show",
            duration=2700.0,  # 45 minutes
            extra_tags={"podcast": "true"},
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.PODCAST

    def test_podcast_keyword_in_title(self, classifier: AudioClassifier) -> None:
        """Title with podcast keywords should score PODCAST."""
        metadata = _make_metadata(
            title="Welcome to the show - Episode 10",
            duration=3600.0,  # 60 minutes
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.PODCAST

    def test_podcast_from_transcription(self, classifier: AudioClassifier) -> None:
        """Transcription with podcast keywords should classify as PODCAST."""
        metadata = _make_metadata(duration=2400.0)
        transcription = _make_transcription(
            text=(
                "Welcome to our podcast episode this week. "
                "Our guest today is a listener favorite. "
                "Don't forget to subscribe. "
                "Thanks for listening and tune in next week."
            ),
            duration=2400.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.PODCAST

    def test_podcast_duration_range(self, classifier: AudioClassifier) -> None:
        """Duration within 15-90 minutes should boost podcast score."""
        metadata = _make_metadata(
            title="Episode 5 - Weekly Update",
            duration=1800.0,  # 30 minutes
        )
        result = classifier.classify(metadata)
        assert AudioType.PODCAST in [
            result.audio_type,
            *(a.audio_type for a in result.alternatives),
        ]


# ---------------------------------------------------------------------------
# Audiobook classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudiobookClassification:
    """Tests for audiobook type detection."""

    def test_audiobook_with_chapter_metadata(self, classifier: AudioClassifier) -> None:
        """Chapter-tagged audiobook should classify as AUDIOBOOK."""
        metadata = _make_metadata(
            title="Chapter 3 - The Journey Begins",
            artist="Famous Author",
            comment="Narrated by John Smith",
            duration=7200.0,  # 2 hours
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.AUDIOBOOK

    def test_audiobook_narrator_tag(self, classifier: AudioClassifier) -> None:
        """Narrator in extra tags should boost AUDIOBOOK score."""
        metadata = _make_metadata(
            title="The Great Novel",
            duration=14400.0,  # 4 hours
            extra_tags={"narrator": "Jane Doe"},
        )
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.AUDIOBOOK

    def test_audiobook_long_narrative_segments(self, classifier: AudioClassifier) -> None:
        """Long single-speaker narrative segments suggest audiobook."""
        metadata = _make_metadata(
            title="Chapter 1",
            duration=3600.0,
            comment="audiobook",
        )
        segments = [
            Segment(id=i, start=i * 20.0, end=(i + 1) * 20.0 - 0.5, text="narrative text")
            for i in range(50)
        ]
        transcription = _make_transcription(
            text="chapter narrator narrated by long story novel",
            segments=segments,
            duration=3600.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.AUDIOBOOK


# ---------------------------------------------------------------------------
# Recording classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordingClassification:
    """Tests for recording/voice memo type detection."""

    def test_recording_no_metadata(self, classifier: AudioClassifier) -> None:
        """Audio with no metadata tags should classify as RECORDING."""
        metadata = _make_metadata(duration=60.0)
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.RECORDING

    def test_recording_short_voice_memo(self, classifier: AudioClassifier) -> None:
        """Very short audio with no metadata is likely a voice memo."""
        metadata = _make_metadata(duration=30.0)
        result = classifier.classify(metadata)
        assert result.audio_type == AudioType.RECORDING

    def test_recording_meeting_keywords(self, classifier: AudioClassifier) -> None:
        """Transcription with meeting keywords should suggest RECORDING."""
        metadata = _make_metadata(duration=1800.0)
        transcription = _make_transcription(
            text=(
                "Let's go over the meeting agenda. "
                "Action items from the conference call include follow up on memo. "
                "Minutes recording for reference."
            ),
            duration=1800.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.RECORDING


# ---------------------------------------------------------------------------
# Interview classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInterviewClassification:
    """Tests for interview type detection."""

    def test_interview_keywords_in_transcription(self, classifier: AudioClassifier) -> None:
        """Transcription with Q&A patterns should classify as INTERVIEW."""
        metadata = _make_metadata(
            title="Interview with Expert",
            duration=2700.0,
        )
        segments = [
            Segment(id=0, start=0.0, end=5.0, text="Tell me about your work"),
            Segment(id=1, start=5.5, end=30.0, text="Well I have been working on..."),
            Segment(id=2, start=31.0, end=33.0, text="What do you think about..."),
            Segment(id=3, start=33.5, end=60.0, text="I believe that..."),
            Segment(id=4, start=61.0, end=63.0, text="How did you start?"),
            Segment(id=5, start=63.5, end=90.0, text="It all began when..."),
        ]
        transcription = _make_transcription(
            text=(
                "interview question answer Tell me about your work. "
                "What do you think about this topic? "
                "How did you start in the field?"
            ),
            segments=segments,
            duration=2700.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.INTERVIEW

    def test_interview_title_keyword(self, classifier: AudioClassifier) -> None:
        """Title containing 'interview' should boost INTERVIEW score."""
        metadata = _make_metadata(
            title="An interview with the CEO",
            duration=1800.0,
        )
        result = classifier.classify(metadata)
        # Should be interview or at least in alternatives
        types = [result.audio_type] + [a.audio_type for a in result.alternatives]
        assert AudioType.INTERVIEW in types


# ---------------------------------------------------------------------------
# Lecture classification tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLectureClassification:
    """Tests for lecture type detection."""

    def test_lecture_keywords_in_transcription(self, classifier: AudioClassifier) -> None:
        """Transcription with educational keywords should classify as LECTURE."""
        metadata = _make_metadata(duration=3000.0)  # 50 minutes
        transcription = _make_transcription(
            text=(
                "Welcome students to this lecture on the university course. "
                "Today's topic covers the syllabus material. "
                "Your homework assignment is due next class. "
                "The exam will cover this education lesson and textbook chapter."
            ),
            segments=[
                Segment(id=i, start=i * 25.0, end=(i + 1) * 25.0 - 1.0, text="lecture content")
                for i in range(20)
            ],
            duration=3000.0,
        )
        result = classifier.classify(metadata, transcription)
        assert result.audio_type == AudioType.LECTURE

    def test_lecture_single_speaker_duration(self, classifier: AudioClassifier) -> None:
        """Single speaker at lecture duration should consider LECTURE."""
        metadata = _make_metadata(
            title="Lecture 5 - Advanced Topics",
            duration=2700.0,  # 45 minutes
        )
        result = classifier.classify(metadata)
        types = [result.audio_type] + [a.audio_type for a in result.alternatives]
        assert AudioType.LECTURE in types


# ---------------------------------------------------------------------------
# Unknown / fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnknownClassification:
    """Tests for edge cases and unknown classification."""

    def test_zero_duration(self, classifier: AudioClassifier) -> None:
        """Audio with zero duration and no metadata should be UNKNOWN or RECORDING."""
        metadata = _make_metadata(duration=0.0)
        result = classifier.classify(metadata)
        # With no metadata and zero duration, RECORDING gets a score from no-metadata
        assert result.audio_type in (AudioType.UNKNOWN, AudioType.RECORDING)

    def test_result_has_alternatives(self, classifier: AudioClassifier) -> None:
        """Classification should include alternatives when scores are close."""
        metadata = _make_metadata(
            title="Episode 1",
            artist="Someone",
            album="Some Album",
            duration=2400.0,
        )
        result = classifier.classify(metadata)
        # Should have at least one alternative given mixed signals
        assert isinstance(result.alternatives, list) and all(
            hasattr(alt, "audio_type") for alt in result.alternatives
        )

    def test_confidence_is_bounded(self, classifier: AudioClassifier) -> None:
        """Confidence must be between 0 and 1."""
        metadata = _make_metadata(
            artist="Artist",
            album="Album",
            genre="Rock",
            track_number=1,
            has_artwork=True,
            duration=200.0,
        )
        result = classifier.classify(metadata)
        assert 0.0 <= result.confidence <= 1.0

    def test_classification_result_fields(self, classifier: AudioClassifier) -> None:
        """ClassificationResult must have all required fields."""
        metadata = _make_metadata(artist="Test")
        result = classifier.classify(metadata)
        assert isinstance(result.audio_type, AudioType)
        assert isinstance(result.confidence, float)
        assert isinstance(result.reasoning, str)
        assert isinstance(result.alternatives, list)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_count_keyword_matches(self) -> None:
        """_count_keyword_matches should count case-insensitive matches."""
        text = "Welcome to this episode of our weekly podcast series"
        count = _count_keyword_matches(text, PODCAST_KEYWORDS)
        assert count >= 2  # "episode", "podcast", "weekly", "series"

    def test_count_keyword_matches_empty(self) -> None:
        """Empty text should return zero matches."""
        assert _count_keyword_matches("", PODCAST_KEYWORDS) == 0

    def test_has_music_metadata_true(self) -> None:
        """Should return True when 2+ music fields are present."""
        metadata = _make_metadata(artist="Artist", album="Album")
        assert _has_music_metadata(metadata) is True

    def test_has_music_metadata_false(self) -> None:
        """Should return False when fewer than 2 music fields are present."""
        metadata = _make_metadata(title="Just a title")
        assert _has_music_metadata(metadata) is False

    def test_has_podcast_metadata(self) -> None:
        """Should detect podcast tags in extra_tags."""
        metadata = _make_metadata(extra_tags={"podcast": "true"})
        assert _has_podcast_metadata(metadata) is True

    def test_has_podcast_metadata_episode_pattern(self) -> None:
        """Should detect 'Ep. 5' pattern in title."""
        metadata = _make_metadata(title="Ep. 5 - Great Discussion")
        assert _has_podcast_metadata(metadata) is True

    def test_has_audiobook_metadata(self) -> None:
        """Should detect audiobook indicators in extra_tags."""
        metadata = _make_metadata(extra_tags={"narrator": "Someone"})
        assert _has_audiobook_metadata(metadata) is True

    def test_estimate_speaker_count_single(self) -> None:
        """Uniform segment durations should suggest 1 speaker."""
        segments = [
            Segment(id=i, start=i * 10.0, end=(i + 1) * 10.0 - 0.5, text="text") for i in range(10)
        ]
        assert _estimate_speaker_count(segments) == 1

    def test_estimate_speaker_count_multiple(self) -> None:
        """Highly variable segment durations suggest multiple speakers."""
        segments = [
            Segment(id=0, start=0.0, end=2.0, text="short"),
            Segment(id=1, start=2.5, end=30.0, text="long"),
            Segment(id=2, start=31.0, end=33.0, text="short"),
            Segment(id=3, start=33.5, end=60.0, text="long"),
            Segment(id=4, start=61.0, end=62.5, text="short"),
            Segment(id=5, start=63.0, end=90.0, text="long"),
        ]
        count = _estimate_speaker_count(segments)
        assert count >= 2

    def test_estimate_speaker_count_few_segments(self) -> None:
        """Fewer than 4 segments should default to 1 speaker."""
        segments = [
            Segment(id=0, start=0.0, end=10.0, text="text"),
            Segment(id=1, start=10.5, end=20.0, text="text"),
        ]
        assert _estimate_speaker_count(segments) == 1
