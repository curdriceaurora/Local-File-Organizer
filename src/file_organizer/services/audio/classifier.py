"""Audio Type Classification Service.

Classifies audio files into content types (music, podcast, audiobook, etc.)
using rule-based heuristics from metadata and optional transcription data.
No external AI dependencies required.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from file_organizer._compat import StrEnum

from .metadata_extractor import AudioMetadata
from .transcriber import Segment, TranscriptionResult

logger = logging.getLogger(__name__)


class AudioType(StrEnum):
    """Audio content type classification."""

    MUSIC = "music"
    PODCAST = "podcast"
    AUDIOBOOK = "audiobook"
    RECORDING = "recording"
    INTERVIEW = "interview"
    LECTURE = "lecture"
    UNKNOWN = "unknown"


@dataclass
class ClassificationAlternative:
    """An alternative classification with its confidence score."""

    audio_type: AudioType
    confidence: float
    reasoning: str


@dataclass
class ClassificationResult:
    """Result of audio type classification."""

    audio_type: AudioType
    confidence: float
    reasoning: str
    alternatives: list[ClassificationAlternative] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Keyword dictionaries for rule-based content classification
# ---------------------------------------------------------------------------

PODCAST_KEYWORDS: set[str] = {
    "episode",
    "podcast",
    "host",
    "guest",
    "listener",
    "subscribe",
    "show notes",
    "sponsor",
    "advertisement",
    "intro",
    "outro",
    "welcome to",
    "thanks for listening",
    "tune in",
    "weekly",
    "ep.",
    "ep ",
    "series",
}

AUDIOBOOK_KEYWORDS: set[str] = {
    "chapter",
    "narrator",
    "narrated by",
    "audiobook",
    "read by",
    "prologue",
    "epilogue",
    "unabridged",
    "abridged",
    "book",
    "novel",
    "author",
    "pages",
}

LECTURE_KEYWORDS: set[str] = {
    "lecture",
    "professor",
    "university",
    "syllabus",
    "exam",
    "students",
    "course",
    "class",
    "semester",
    "homework",
    "assignment",
    "textbook",
    "topic",
    "education",
    "lesson",
    "tutorial",
    "slide",
    "curriculum",
}

INTERVIEW_KEYWORDS: set[str] = {
    "interview",
    "question",
    "answer",
    "interviewer",
    "interviewee",
    "tell me about",
    "what do you think",
    "how did you",
    "q&a",
    "panel",
    "discussion",
    "moderator",
    "respondent",
}

RECORDING_KEYWORDS: set[str] = {
    "meeting",
    "minutes",
    "memo",
    "recording",
    "voice note",
    "dictation",
    "note to self",
    "reminder",
    "agenda",
    "action items",
    "follow up",
    "conference call",
}

MUSIC_GENRES: set[str] = {
    "rock",
    "pop",
    "jazz",
    "blues",
    "classical",
    "country",
    "hip hop",
    "hip-hop",
    "rap",
    "r&b",
    "rnb",
    "electronic",
    "dance",
    "edm",
    "metal",
    "punk",
    "folk",
    "soul",
    "funk",
    "reggae",
    "latin",
    "indie",
    "alternative",
    "ambient",
    "techno",
    "house",
    "trance",
    "dubstep",
    "world",
}


def _count_keyword_matches(text: str, keywords: set[str]) -> int:
    """Count how many keywords appear in the given text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def _has_music_metadata(metadata: AudioMetadata) -> bool:
    """Check whether metadata fields strongly suggest music."""
    indicators = 0
    if metadata.artist is not None:
        indicators += 1
    if metadata.album is not None:
        indicators += 1
    if metadata.track_number is not None:
        indicators += 1
    if metadata.genre is not None:
        indicators += 1
    if metadata.has_artwork:
        indicators += 1
    return indicators >= 2


def _has_podcast_metadata(metadata: AudioMetadata) -> bool:
    """Check whether metadata or extra tags suggest a podcast."""
    # Look for podcast-related extra tags
    extra_lower = {k.lower(): v.lower() for k, v in metadata.extra_tags.items()}

    podcast_tag_keys = {"podcast", "show", "episode", "episode_sort"}
    if any(k in extra_lower for k in podcast_tag_keys):
        return True

    # Check title/comment for podcast indicators
    searchable = " ".join(s for s in [metadata.title, metadata.comment] if s is not None).lower()
    return bool(re.search(r"\bep(isode)?[\s.#]*\d", searchable))


def _has_audiobook_metadata(metadata: AudioMetadata) -> bool:
    """Check whether metadata or extra tags suggest an audiobook."""
    extra_lower = {k.lower(): v.lower() for k, v in metadata.extra_tags.items()}

    audiobook_tag_keys = {"narrator", "narrated by", "chapter", "audiobook"}
    if any(k in extra_lower for k in audiobook_tag_keys):
        return True

    # Check title/comment/genre for audiobook indicators
    searchable = " ".join(
        s for s in [metadata.title, metadata.comment, metadata.genre] if s is not None
    ).lower()
    return any(kw in searchable for kw in ("audiobook", "narrated by", "chapter"))


def _estimate_speaker_count(segments: list[Segment]) -> int:
    """Estimate speaker diversity from segment patterns.

    Uses pause-gap heuristics: large gaps between segments and varying
    segment lengths suggest multiple speakers.  This is a rough proxy
    when real diarisation is unavailable.
    """
    if len(segments) < 4:
        return 1

    # Look at variance in segment durations as a proxy
    durations = [seg.end - seg.start for seg in segments]
    if not durations:
        return 1

    mean_dur = sum(durations) / len(durations)
    variance = sum((d - mean_dur) ** 2 for d in durations) / len(durations)
    std_dev = variance**0.5

    # High variability in segment length hints at multiple speakers
    coefficient_of_variation = std_dev / mean_dur if mean_dur > 0 else 0

    if coefficient_of_variation > 0.8:
        return 3  # Likely multiple speakers
    elif coefficient_of_variation > 0.4:
        return 2  # Possibly two speakers
    return 1


class AudioClassifier:
    """Rule-based audio type classifier.

    Uses metadata tags, duration heuristics, and optional transcription
    content to classify audio files without requiring external AI models.

    Example:
        >>> classifier = AudioClassifier()
        >>> result = classifier.classify(metadata)
        >>> print(result.audio_type, result.confidence)
    """

    # Duration thresholds in seconds
    MUSIC_MAX_DURATION: float = 600.0  # 10 minutes
    PODCAST_MIN_DURATION: float = 900.0  # 15 minutes
    PODCAST_MAX_DURATION: float = 5400.0  # 90 minutes
    AUDIOBOOK_MIN_DURATION: float = 1800.0  # 30 minutes
    LECTURE_MIN_DURATION: float = 1800.0  # 30 minutes
    LECTURE_MAX_DURATION: float = 5400.0  # 90 minutes

    def classify(
        self,
        metadata: AudioMetadata,
        transcription: TranscriptionResult | None = None,
    ) -> ClassificationResult:
        """Classify an audio file by content type.

        Args:
            metadata: Audio file metadata (required).
            transcription: Optional transcription result for deeper analysis.

        Returns:
            ClassificationResult with type, confidence, reasoning, and alternatives.
        """
        scores: dict[AudioType, float] = dict.fromkeys(AudioType, 0.0)
        reasons: dict[AudioType, list[str]] = {t: [] for t in AudioType}

        # ------------------------------------------------------------------
        # Phase 1: Metadata-based scoring
        # ------------------------------------------------------------------
        self._score_from_metadata(metadata, scores, reasons)

        # ------------------------------------------------------------------
        # Phase 2: Duration-based scoring
        # ------------------------------------------------------------------
        self._score_from_duration(metadata.duration, scores, reasons)

        # ------------------------------------------------------------------
        # Phase 3: Transcription-based scoring (if available)
        # ------------------------------------------------------------------
        if transcription is not None:
            self._score_from_transcription(transcription, scores, reasons)

        # ------------------------------------------------------------------
        # Select winner
        # ------------------------------------------------------------------
        # Remove UNKNOWN from competition (it is the fallback)
        candidate_scores = {t: s for t, s in scores.items() if t != AudioType.UNKNOWN}

        if not candidate_scores or max(candidate_scores.values()) <= 0:
            return ClassificationResult(
                audio_type=AudioType.UNKNOWN,
                confidence=0.0,
                reasoning="No classification signals detected.",
            )

        # Sort by score descending
        ranked = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        best_type, best_score = ranked[0]

        # Normalise confidence to 0-1 range
        total = sum(max(s, 0) for s in candidate_scores.values())
        confidence = best_score / total if total > 0 else 0.0
        confidence = min(confidence, 1.0)

        # Build alternatives
        alternatives: list[ClassificationAlternative] = []
        for alt_type, alt_score in ranked[1:]:
            if alt_score > 0:
                alt_conf = alt_score / total if total > 0 else 0.0
                alternatives.append(
                    ClassificationAlternative(
                        audio_type=alt_type,
                        confidence=min(alt_conf, 1.0),
                        reasoning="; ".join(reasons[alt_type]),
                    )
                )

        reasoning = "; ".join(reasons[best_type]) if reasons[best_type] else "Best match by score."

        result = ClassificationResult(
            audio_type=best_type,
            confidence=round(confidence, 3),
            reasoning=reasoning,
            alternatives=alternatives,
        )

        logger.info(
            f"Classified {metadata.file_path.name} as {result.audio_type.value} "
            f"(confidence={result.confidence})"
        )
        return result

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _score_from_metadata(
        self,
        metadata: AudioMetadata,
        scores: dict[AudioType, float],
        reasons: dict[AudioType, list[str]],
    ) -> None:
        """Score audio types based on metadata tags."""
        # Music signals
        if _has_music_metadata(metadata):
            scores[AudioType.MUSIC] += 3.0
            reasons[AudioType.MUSIC].append("Has music metadata (artist/album/track)")

        if metadata.genre is not None and metadata.genre.lower() in MUSIC_GENRES:
            scores[AudioType.MUSIC] += 2.0
            reasons[AudioType.MUSIC].append(f"Genre '{metadata.genre}' is a music genre")

        if metadata.has_artwork:
            scores[AudioType.MUSIC] += 1.0
            reasons[AudioType.MUSIC].append("Has embedded artwork")

        # Podcast signals
        if _has_podcast_metadata(metadata):
            scores[AudioType.PODCAST] += 3.0
            reasons[AudioType.PODCAST].append("Has podcast metadata indicators")

        # Audiobook signals
        if _has_audiobook_metadata(metadata):
            scores[AudioType.AUDIOBOOK] += 3.0
            reasons[AudioType.AUDIOBOOK].append("Has audiobook metadata indicators")

        # Recording signals (lack of metadata)
        tag_count = sum(
            1
            for val in [
                metadata.title,
                metadata.artist,
                metadata.album,
                metadata.genre,
                metadata.track_number,
            ]
            if val is not None
        )
        if tag_count == 0:
            scores[AudioType.RECORDING] += 2.0
            reasons[AudioType.RECORDING].append("No metadata tags present")
        elif tag_count == 1 and metadata.title is not None:
            scores[AudioType.RECORDING] += 1.0
            reasons[AudioType.RECORDING].append("Only title tag present, no other metadata")

        # Check title/comment text for keyword matches
        searchable_text = " ".join(s for s in [metadata.title, metadata.comment] if s is not None)
        if searchable_text:
            for audio_type, kw_set in [
                (AudioType.PODCAST, PODCAST_KEYWORDS),
                (AudioType.AUDIOBOOK, AUDIOBOOK_KEYWORDS),
                (AudioType.LECTURE, LECTURE_KEYWORDS),
                (AudioType.INTERVIEW, INTERVIEW_KEYWORDS),
                (AudioType.RECORDING, RECORDING_KEYWORDS),
            ]:
                matches = _count_keyword_matches(searchable_text, kw_set)
                if matches > 0:
                    scores[audio_type] += matches * 1.5
                    reasons[audio_type].append(f"{matches} keyword match(es) in title/comment")

    def _score_from_duration(
        self,
        duration: float,
        scores: dict[AudioType, float],
        reasons: dict[AudioType, list[str]],
    ) -> None:
        """Score audio types based on duration heuristics."""
        if duration <= 0:
            return

        # Short audio -> likely music or recording
        if duration <= self.MUSIC_MAX_DURATION:
            scores[AudioType.MUSIC] += 1.5
            reasons[AudioType.MUSIC].append(f"Duration ({duration:.0f}s) within music range")

        # Podcast range
        if self.PODCAST_MIN_DURATION <= duration <= self.PODCAST_MAX_DURATION:
            scores[AudioType.PODCAST] += 1.5
            reasons[AudioType.PODCAST].append(
                f"Duration ({duration:.0f}s) within podcast range (15-90min)"
            )

        # Audiobook range
        if duration >= self.AUDIOBOOK_MIN_DURATION:
            scores[AudioType.AUDIOBOOK] += 1.5
            reasons[AudioType.AUDIOBOOK].append(
                f"Duration ({duration:.0f}s) within audiobook range (>30min)"
            )

        # Lecture range
        if self.LECTURE_MIN_DURATION <= duration <= self.LECTURE_MAX_DURATION:
            scores[AudioType.LECTURE] += 1.0
            reasons[AudioType.LECTURE].append(
                f"Duration ({duration:.0f}s) within lecture range (30-90min)"
            )

        # Very short recordings (<2min) hint at voice memos
        if duration < 120:
            scores[AudioType.RECORDING] += 1.0
            reasons[AudioType.RECORDING].append(
                f"Duration ({duration:.0f}s) suggests a short recording/memo"
            )

    def _score_from_transcription(
        self,
        transcription: TranscriptionResult,
        scores: dict[AudioType, float],
        reasons: dict[AudioType, list[str]],
    ) -> None:
        """Score audio types based on transcription content."""
        text = transcription.text

        # Keyword matching on full transcription text
        for audio_type, kw_set in [
            (AudioType.PODCAST, PODCAST_KEYWORDS),
            (AudioType.AUDIOBOOK, AUDIOBOOK_KEYWORDS),
            (AudioType.LECTURE, LECTURE_KEYWORDS),
            (AudioType.INTERVIEW, INTERVIEW_KEYWORDS),
            (AudioType.RECORDING, RECORDING_KEYWORDS),
        ]:
            matches = _count_keyword_matches(text, kw_set)
            if matches >= 3:
                scores[audio_type] += 3.0
                reasons[audio_type].append(f"{matches} keyword matches in transcription")
            elif matches >= 1:
                scores[audio_type] += matches * 0.8
                reasons[audio_type].append(f"{matches} keyword match(es) in transcription")

        # If transcription has minimal text, it might be music
        word_count = len(text.split())
        if word_count < 20 and transcription.duration > 60:
            scores[AudioType.MUSIC] += 2.0
            reasons[AudioType.MUSIC].append("Very few words detected, likely instrumental/music")

        # Speaker count estimation from segments
        if transcription.segments:
            speaker_count = _estimate_speaker_count(transcription.segments)

            if speaker_count >= 3:
                scores[AudioType.INTERVIEW] += 2.0
                scores[AudioType.PODCAST] += 1.5
                reasons[AudioType.INTERVIEW].append(
                    f"Estimated {speaker_count} speakers (segment variance)"
                )
                reasons[AudioType.PODCAST].append(
                    f"Estimated {speaker_count} speakers (segment variance)"
                )
            elif speaker_count == 2:
                scores[AudioType.INTERVIEW] += 1.5
                scores[AudioType.PODCAST] += 1.0
                reasons[AudioType.INTERVIEW].append("Estimated 2 speakers (segment variance)")
                reasons[AudioType.PODCAST].append("Estimated 2 speakers (segment variance)")
            elif speaker_count == 1:
                scores[AudioType.LECTURE] += 1.0
                scores[AudioType.AUDIOBOOK] += 1.0
                reasons[AudioType.LECTURE].append("Estimated single speaker (segment variance)")
                reasons[AudioType.AUDIOBOOK].append("Estimated single speaker (segment variance)")

        # Narrative speech pattern (long continuous segments)
        if transcription.segments:
            avg_segment_len = sum(seg.end - seg.start for seg in transcription.segments) / len(
                transcription.segments
            )
            if avg_segment_len > 15:
                scores[AudioType.AUDIOBOOK] += 1.5
                scores[AudioType.LECTURE] += 1.0
                reasons[AudioType.AUDIOBOOK].append(
                    f"Long average segment length ({avg_segment_len:.1f}s) suggests narrative"
                )
                reasons[AudioType.LECTURE].append(
                    f"Long average segment length ({avg_segment_len:.1f}s) suggests lecture"
                )
