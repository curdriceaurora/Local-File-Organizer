"""
Tests for AudioContentAnalyzer - Content Analysis Service

Tests cover:
- Topic extraction from text
- Keyword extraction with frequency analysis
- Speaker estimation from segments
- Sentiment analysis
- Integration with AudioMetadata and TranscriptionResult
- Edge cases (empty text, no transcription, short segments)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.audio.content_analyzer import (
    STOP_WORDS,
    AudioContentAnalyzer,
    ContentAnalysis,
    _tokenize,
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
    comment: str | None = None,
    year: int | None = 2024,
    duration: float = 180.0,
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
        comment=comment,
        year=year,
        extra_tags={},
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
def analyzer() -> AudioContentAnalyzer:
    return AudioContentAnalyzer()


# ---------------------------------------------------------------------------
# Tokenization tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTokenize:
    """Tests for the _tokenize helper."""

    def test_basic_tokenization(self) -> None:
        tokens = _tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_punctuation_removal(self) -> None:
        tokens = _tokenize("Hello, World! How are you?")
        assert "hello" in tokens
        assert "world" in tokens

    def test_empty_string(self) -> None:
        assert _tokenize("") == []

    def test_single_char_filtered(self) -> None:
        """Single-character tokens should be filtered out."""
        tokens = _tokenize("I a the big dog")
        assert "i" not in tokens  # single char removed


# ---------------------------------------------------------------------------
# Topic extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTopicExtraction:
    """Tests for topic category matching."""

    def test_technology_topic(self, analyzer: AudioContentAnalyzer) -> None:
        text = "This software uses machine learning algorithms for data analysis"
        topics = analyzer.extract_topics(text)
        assert "Technology" in topics

    def test_health_topic(self, analyzer: AudioContentAnalyzer) -> None:
        text = "The doctor recommended therapy and treatment for the patient's disease"
        topics = analyzer.extract_topics(text)
        assert "Health" in topics

    def test_multiple_topics(self, analyzer: AudioContentAnalyzer) -> None:
        text = (
            "The university research team published a scientific study about "
            "machine learning algorithms and artificial intelligence in education"
        )
        topics = analyzer.extract_topics(text)
        assert len(topics) >= 2

    def test_no_topics_for_unrelated_text(self, analyzer: AudioContentAnalyzer) -> None:
        text = "lorem ipsum dolor sit amet"
        topics = analyzer.extract_topics(text)
        assert len(topics) == 0

    def test_max_topics_limit(self) -> None:
        analyzer = AudioContentAnalyzer(max_topics=2)
        text = (
            "software programming education university health medical business market sports game"
        )
        topics = analyzer.extract_topics(text)
        assert len(topics) == 2  # max_topics=2 guarantees exactly 2 from multi-topic input


# ---------------------------------------------------------------------------
# Keyword extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestKeywordExtraction:
    """Tests for keyword frequency extraction."""

    def test_extracts_frequent_words(self, analyzer: AudioContentAnalyzer) -> None:
        text = (
            "python programming python code python development "
            "programming language programming tools"
        )
        keywords = analyzer.extract_keywords(text)
        assert "python" in keywords
        assert "programming" in keywords

    def test_filters_stop_words(self, analyzer: AudioContentAnalyzer) -> None:
        text = "the and or but in on at to for of with by from"
        keywords = analyzer.extract_keywords(text)
        for kw in keywords:
            # All stop words should be filtered out
            assert kw not in STOP_WORDS

    def test_empty_text(self, analyzer: AudioContentAnalyzer) -> None:
        keywords = analyzer.extract_keywords("")
        assert keywords == []

    def test_max_keywords_limit(self) -> None:
        analyzer = AudioContentAnalyzer(max_keywords=3)
        text = "alpha alpha beta beta gamma gamma delta delta epsilon epsilon"
        keywords = analyzer.extract_keywords(text)
        assert len(keywords) == 3  # max_keywords=3 guarantees exactly 3 from 5-unique-word input

    def test_min_keyword_freq(self) -> None:
        analyzer = AudioContentAnalyzer(min_keyword_freq=3)
        text = "python python python java java ruby"
        keywords = analyzer.extract_keywords(text)
        # "python" appears 3 times so should be first
        assert keywords[0] == "python"


# ---------------------------------------------------------------------------
# Speaker extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSpeakerExtraction:
    """Tests for speaker estimation from segments."""

    def test_no_segments_no_speakers(self, analyzer: AudioContentAnalyzer) -> None:
        speakers = analyzer.extract_speakers([])
        assert speakers == []

    def test_single_speaker_uniform_segments(self, analyzer: AudioContentAnalyzer) -> None:
        """Uniform segments with small gaps should show 1 speaker."""
        segments = [
            Segment(id=i, start=i * 5.0, end=(i + 1) * 5.0 - 0.3, text="text") for i in range(10)
        ]
        speakers = analyzer.extract_speakers(segments)
        assert "Speaker 1" in speakers

    def test_multiple_speakers_from_gaps(self, analyzer: AudioContentAnalyzer) -> None:
        """Large gaps between segments should produce multiple speakers."""
        segments = [
            Segment(id=0, start=0.0, end=5.0, text="Hello"),
            Segment(id=1, start=8.0, end=13.0, text="Response"),  # 3s gap
            Segment(id=2, start=15.0, end=20.0, text="Follow up"),
            Segment(id=3, start=24.0, end=29.0, text="Answer"),  # 4s gap
        ]
        speakers = analyzer.extract_speakers(segments)
        assert len(speakers) >= 2

    def test_multiple_speakers_from_duration_variance(self, analyzer: AudioContentAnalyzer) -> None:
        """Large duration differences should hint at speaker changes."""
        segments = [
            Segment(id=0, start=0.0, end=2.0, text="short question"),
            Segment(id=1, start=2.2, end=30.0, text="long answer" * 20),
            Segment(id=2, start=30.5, end=32.0, text="short follow up"),
            Segment(id=3, start=32.2, end=60.0, text="another long answer" * 20),
        ]
        speakers = analyzer.extract_speakers(segments)
        assert len(speakers) >= 2


# ---------------------------------------------------------------------------
# Sentiment analysis tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSentimentAnalysis:
    """Tests for sentiment indicator extraction."""

    def test_positive_sentiment(self, analyzer: AudioContentAnalyzer) -> None:
        metadata = _make_metadata(title="Amazing wonderful brilliant")
        analysis = analyzer.analyze(metadata)
        assert analysis.sentiment_indicators.get("positive", 0) > 0

    def test_negative_sentiment(self, analyzer: AudioContentAnalyzer) -> None:
        metadata = _make_metadata(title="terrible horrible awful failure")
        analysis = analyzer.analyze(metadata)
        assert analysis.sentiment_indicators.get("negative", 0) > 0

    def test_neutral_text(self, analyzer: AudioContentAnalyzer) -> None:
        metadata = _make_metadata(title="however furthermore consequently")
        analysis = analyzer.analyze(metadata)
        assert analysis.sentiment_indicators.get("neutral", 0) > 0

    def test_no_sentiment_words(self, analyzer: AudioContentAnalyzer) -> None:
        metadata = _make_metadata(title="just some random title")
        analysis = analyzer.analyze(metadata)
        sentiments = analysis.sentiment_indicators
        total = sum(sentiments.values())
        assert total == 0.0


# ---------------------------------------------------------------------------
# Full analyze() integration tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeIntegration:
    """Tests for the full analyze() method."""

    def test_metadata_only(self, analyzer: AudioContentAnalyzer) -> None:
        """Analyze with metadata only (no transcription)."""
        metadata = _make_metadata(
            title="Machine Learning Tutorial",
            genre="Education",
            comment="A deep dive into AI and software development",
        )
        analysis = analyzer.analyze(metadata)
        assert isinstance(analysis, ContentAnalysis)
        assert analysis.topic_count > 0
        assert analysis.language is None  # No transcription -> no language

    def test_with_transcription(self, analyzer: AudioContentAnalyzer) -> None:
        """Analyze with both metadata and transcription."""
        metadata = _make_metadata(title="Tech Talk")
        transcription = _make_transcription(
            text=(
                "Today we discuss software programming and machine learning. "
                "The algorithm processes data efficiently. "
                "Cloud computing enables scalable solutions."
            ),
            language="en",
        )
        analysis = analyzer.analyze(metadata, transcription)
        assert "Technology" in analysis.topics
        assert analysis.language == "en"

    def test_speakers_from_segments(self, analyzer: AudioContentAnalyzer) -> None:
        """Speakers should be extracted from transcription segments."""
        metadata = _make_metadata()
        segments = [
            Segment(id=0, start=0.0, end=5.0, text="Question"),
            Segment(id=1, start=8.0, end=30.0, text="Long answer here"),
            Segment(id=2, start=32.0, end=35.0, text="Follow up"),
            Segment(id=3, start=38.0, end=60.0, text="Detailed response"),
        ]
        transcription = _make_transcription(
            text="Question Long answer Follow up Detailed response",
            segments=segments,
        )
        analysis = analyzer.analyze(metadata, transcription)
        assert analysis.speaker_count >= 1

    def test_empty_metadata(self, analyzer: AudioContentAnalyzer) -> None:
        """No text available at all should produce empty analysis."""
        metadata = _make_metadata()
        analysis = analyzer.analyze(metadata)
        assert analysis.topic_count == 0
        assert analysis.keyword_count == 0
        assert analysis.speaker_count == 0

    def test_content_analysis_properties(self, analyzer: AudioContentAnalyzer) -> None:
        """ContentAnalysis properties should work correctly."""
        analysis = ContentAnalysis(
            topics=["Tech", "Science"],
            keywords=["python", "code"],
            speakers=["Speaker 1", "Speaker 2"],
        )
        assert analysis.topic_count == 2
        assert analysis.keyword_count == 2
        assert analysis.speaker_count == 2

    def test_metadata_with_artist_and_album(self, analyzer: AudioContentAnalyzer) -> None:
        """Artist and album metadata fields should be included in analysis text."""
        metadata = _make_metadata(
            title="Live Performance",
            artist="DJ Software Engineer",
            album="Cloud Computing Sessions",
        )
        analysis = analyzer.analyze(metadata)
        # "software" and "cloud" + "computing" should trigger Technology topic
        assert "Technology" in analysis.topics
        assert analysis.keyword_count > 0

    def test_metadata_artist_only(self, analyzer: AudioContentAnalyzer) -> None:
        """Artist field alone should contribute to combined text."""
        metadata = _make_metadata(artist="Amazing Orchestra")
        analysis = analyzer.analyze(metadata)
        # Should produce a non-empty analysis since artist text is present
        assert isinstance(analysis, ContentAnalysis)
        assert analysis.sentiment_indicators.get("positive", 0) > 0  # "amazing"

    def test_metadata_album_only(self, analyzer: AudioContentAnalyzer) -> None:
        """Album field alone should contribute to combined text."""
        metadata = _make_metadata(album="Greatest Scientific Discoveries")
        analysis = analyzer.analyze(metadata)
        assert isinstance(analysis, ContentAnalysis)
        assert "Science" in analysis.topics
