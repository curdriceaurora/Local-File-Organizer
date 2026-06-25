"""Audio Content Analysis Service.

Extracts topics, keywords, speaker information, and sentiment indicators
from audio metadata and transcription data.  Uses lightweight NLP
techniques (keyword extraction, regex, heuristics) without requiring
external AI models.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from .lexicons import SentimentLexicon
from .metadata_extractor import AudioMetadata
from .transcriber import Segment, TranscriptionResult

logger = logging.getLogger(__name__)

# D6: sentiment / keyword lexicons moved to an external JSON file.
# Module-level constants are the default lexicon's fields — pre-D6
# consumers importing ``STOP_WORDS`` etc. keep working unchanged.
# See ``src/services/audio/lexicons.py`` for the loader + schema.
_DEFAULT_LEXICON = SentimentLexicon.load_default()
STOP_WORDS: frozenset[str] = _DEFAULT_LEXICON.stop_words
TOPIC_CATEGORIES: dict[str, list[str]] = _DEFAULT_LEXICON.topic_categories
POSITIVE_WORDS: frozenset[str] = _DEFAULT_LEXICON.positive_words
NEGATIVE_WORDS: frozenset[str] = _DEFAULT_LEXICON.negative_words
NEUTRAL_WORDS: frozenset[str] = _DEFAULT_LEXICON.neutral_words


@dataclass
class ContentAnalysis:
    """Complete content analysis result for an audio file."""

    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    language: str | None = None
    sentiment_indicators: dict[str, float] = field(default_factory=dict)

    @property
    def topic_count(self) -> int:
        """Return the number of topics."""
        return len(self.topics)

    @property
    def keyword_count(self) -> int:
        """Return the number of keywords."""
        return len(self.keywords)

    @property
    def speaker_count(self) -> int:
        """Return the number of speakers."""
        return len(self.speakers)


def _tokenize(text: str) -> list[str]:
    """Simple word tokenisation: lowercase, strip punctuation."""
    # Remove punctuation except apostrophes within words
    cleaned = re.sub(r"[^\w\s'-]", " ", text.lower())
    tokens = cleaned.split()
    return [t.strip("'-") for t in tokens if len(t.strip("'-")) > 1]


class AudioContentAnalyzer:
    """Analyses audio content by extracting topics, keywords, speakers.

    Extracts and sentiment indicators from metadata and transcription data.
    Uses lightweight rule-based NLP rather than external AI models.

    Example:
        >>> analyzer = AudioContentAnalyzer()
        >>> analysis = analyzer.analyze(metadata, transcription)
        >>> print(analysis.topics, analysis.keywords)
    """

    def __init__(
        self,
        max_keywords: int = 20,
        max_topics: int = 5,
        min_keyword_freq: int = 2,
    ) -> None:
        """Initialise the content analyser.

        Args:
            max_keywords: Maximum number of keywords to extract.
            max_topics: Maximum number of topics to return.
            min_keyword_freq: Minimum word frequency to be considered a keyword.
        """
        self.max_keywords = max_keywords
        self.max_topics = max_topics
        self.min_keyword_freq = min_keyword_freq

    def analyze(
        self,
        metadata: AudioMetadata,
        transcription: TranscriptionResult | None = None,
    ) -> ContentAnalysis:
        """Perform full content analysis on an audio file.

        Args:
            metadata: Audio file metadata.
            transcription: Optional transcription result.

        Returns:
            ContentAnalysis with topics, keywords, speakers, language, sentiment.
        """
        analysis = ContentAnalysis()

        # Gather all available text
        text_parts: list[str] = []
        if metadata.title:
            text_parts.append(metadata.title)
        if metadata.comment:
            text_parts.append(metadata.comment)
        if metadata.genre:
            text_parts.append(metadata.genre)
        if metadata.artist:
            text_parts.append(metadata.artist)
        if metadata.album:
            text_parts.append(metadata.album)

        transcription_text = ""
        if transcription is not None:
            transcription_text = transcription.text
            text_parts.append(transcription_text)
            analysis.language = transcription.language

        combined_text = " ".join(text_parts)

        if combined_text.strip():
            # Extract topics and keywords
            analysis.topics = self.extract_topics(combined_text)
            analysis.keywords = self.extract_keywords(combined_text)
            analysis.sentiment_indicators = self._analyze_sentiment(combined_text)

        # Extract speakers if transcription segments are available
        if transcription is not None and transcription.segments:
            analysis.speakers = self.extract_speakers(transcription.segments)

        logger.info(
            f"Content analysis: {analysis.topic_count} topics, "
            f"{analysis.keyword_count} keywords, "
            f"{analysis.speaker_count} speakers"
        )
        return analysis

    def extract_topics(self, text: str) -> list[str]:
        """Extract topic categories from text.

        Matches text against known topic keyword dictionaries.

        Args:
            text: The text to analyse.

        Returns:
            Sorted list of matched topic category names.
        """
        text_lower = text.lower()
        topic_scores: dict[str, int] = {}

        for category, keywords in TOPIC_CATEGORIES.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                topic_scores[category] = score

        # Sort by score descending, return top N
        ranked = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
        return [cat for cat, _ in ranked[: self.max_topics]]

    def extract_keywords(self, text: str) -> list[str]:
        """Extract significant keywords from text.

        Uses frequency analysis with stop-word filtering.

        Args:
            text: The text to analyse.

        Returns:
            List of keywords sorted by frequency (descending).
        """
        tokens = _tokenize(text)

        # Filter stop words and very short tokens
        filtered = [t for t in tokens if t not in STOP_WORDS and len(t) > 2 and not t.isdigit()]

        # Count frequencies
        freq = Counter(filtered)

        # Filter by minimum frequency
        significant = [
            (word, count) for word, count in freq.most_common() if count >= self.min_keyword_freq
        ]

        # If we have fewer than max_keywords at min_freq, include top single-occurrence
        if len(significant) < self.max_keywords:
            remaining = [
                (word, count) for word, count in freq.most_common() if count < self.min_keyword_freq
            ]
            significant.extend(remaining[: self.max_keywords - len(significant)])

        return [word for word, _ in significant[: self.max_keywords]]

    def extract_speakers(self, segments: list[Segment]) -> list[str]:
        """Estimate speaker labels from transcription segments.

        Since we do not have real speaker diarisation, we use segment
        timing patterns to infer speaker turns.  Speakers are labelled
        as ``Speaker 1``, ``Speaker 2``, etc.

        Args:
            segments: Transcription segments.

        Returns:
            List of estimated speaker labels.
        """
        if not segments:
            return []

        # Use gap-based heuristic for turn detection
        speakers: list[str] = ["Speaker 1"]
        current_speaker_idx = 0
        turn_threshold = 1.5  # seconds of gap suggesting speaker change

        for i in range(1, len(segments)):
            gap = segments[i].start - segments[i - 1].end

            # Duration ratio between consecutive segments
            prev_dur = segments[i - 1].end - segments[i - 1].start
            curr_dur = segments[i].end - segments[i].start
            dur_ratio = (
                max(prev_dur, curr_dur) / min(prev_dur, curr_dur)
                if min(prev_dur, curr_dur) > 0
                else 1.0
            )

            # A significant gap or large duration change hints at a speaker switch
            if gap > turn_threshold or dur_ratio > 3.0:
                current_speaker_idx = (current_speaker_idx + 1) % 4  # max 4 speakers
                label = f"Speaker {current_speaker_idx + 1}"
                if label not in speakers:
                    speakers.append(label)

        return speakers

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _analyze_sentiment(text: str) -> dict[str, float]:
        """Compute simple sentiment indicators from word frequency.

        Returns a dict with 'positive', 'negative', and 'neutral' scores
        normalised to the 0-1 range.
        """
        tokens = set(_tokenize(text))

        pos_count = len(tokens & POSITIVE_WORDS)
        neg_count = len(tokens & NEGATIVE_WORDS)
        neu_count = len(tokens & NEUTRAL_WORDS)
        total = pos_count + neg_count + neu_count

        if total == 0:
            return {"positive": 0.0, "negative": 0.0, "neutral": 0.0}

        return {
            "positive": round(pos_count / total, 3),
            "negative": round(neg_count / total, 3),
            "neutral": round(neu_count / total, 3),
        }
