from file_organizer.services.audio.content_analyzer import (
    AudioContentAnalyzer,
    ContentAnalysis,
    _tokenize,
)
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.transcriber import Segment, TranscriptionResult


def test_tokenize():
    text = "Hello, world! This is a test."
    tokens = _tokenize(text)
    assert tokens == ["hello", "world", "this", "is", "test"]


def test_content_analysis_properties():
    ca = ContentAnalysis(topics=["A", "B"], keywords=["C"], speakers=["S1", "S2", "S3"])
    assert ca.topic_count == 2
    assert ca.keyword_count == 1
    assert ca.speaker_count == 3


def test_analyze_empty():
    analyzer = AudioContentAnalyzer()
    meta = AudioMetadata(
        file_path="dummy",
        file_size=1,
        format="mp3",
        duration=1,
        bitrate=1,
        sample_rate=1,
        channels=1,
    )
    result = analyzer.analyze(meta)
    assert result.topic_count == 0
    assert result.keyword_count == 0


def test_analyze_full():
    analyzer = AudioContentAnalyzer(max_keywords=5, max_topics=3, min_keyword_freq=1)
    meta = AudioMetadata(
        file_path="dummy",
        file_size=1,
        format="mp3",
        duration=1,
        bitrate=1,
        sample_rate=1,
        channels=1,
        title="A beautiful software startup",
        comment="We use python and ai",
        genre="Tech",
        artist="John",
        album="Tech Pod",
    )

    segments = [
        Segment("Hello", 0.0, 1.0, 0.9),
        Segment("Hi there", 3.0, 4.0, 0.9),  # 2s gap, diff speaker
        Segment("Let's talk about machine learning", 4.1, 7.0, 0.9),  # 0.1s gap, same speaker
    ]
    transcription = TranscriptionResult(
        text="Hello. Hi there. Let's talk about machine learning.",
        segments=segments,
        language="en",
        language_confidence=1.0,
        duration=10.0,
        options={},
    )

    result = analyzer.analyze(meta, transcription)

    # Check topics (should match Technology and maybe Business due to startup)
    assert "Technology" in result.topics

    # Check sentiment (beautiful -> positive)
    assert "positive" in result.sentiment_indicators
    assert result.sentiment_indicators["positive"] > 0

    # Check speakers (should be at least 2 speakers because of the gap)
    assert result.speaker_count >= 2


def test_extract_speakers_empty():
    analyzer = AudioContentAnalyzer()
    assert analyzer.extract_speakers([]) == []


def test_analyze_sentiment_zero():
    analyzer = AudioContentAnalyzer()
    res = analyzer._analyze_sentiment("")
    assert res == {"positive": 0.0, "negative": 0.0, "neutral": 0.0}


def test_extract_keywords_fallback():
    analyzer = AudioContentAnalyzer(max_keywords=10, min_keyword_freq=10)
    # The words won't meet freq 10, so it will fallback to top single-occurrence
    kws = analyzer.extract_keywords("unique words that appear only once")
    assert len(kws) > 0
