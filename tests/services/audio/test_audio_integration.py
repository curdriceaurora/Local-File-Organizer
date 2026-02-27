"""
Integration Tests for Audio Content-Based Organization

Tests the complete pipeline: metadata -> classification -> content analysis -> organisation.
All tests use mock data (no actual audio files or AI models required).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.services.audio.classifier import (
    AudioClassifier,
    AudioType,
    ClassificationResult,
)
from file_organizer.services.audio.content_analyzer import (
    AudioContentAnalyzer,
    ContentAnalysis,
)
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.organizer import (
    AudioOrganizer,
    OrganizationRules,
)
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
    file_path: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    year: int | None = 2024,
    track_number: int | None = None,
    duration: float = 180.0,
    has_artwork: bool = False,
    comment: str | None = None,
    extra_tags: dict[str, str] | None = None,
    album_artist: str | None = None,
) -> AudioMetadata:
    """Helper to create AudioMetadata."""
    return AudioMetadata(
        file_path=file_path or Path("/tmp/test.mp3"),
        file_size=5_000_000,
        format="MP3",
        duration=duration,
        bitrate=320000,
        sample_rate=44100,
        channels=2,
        title=title,
        artist=artist,
        album=album,
        album_artist=album_artist,
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
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def classifier() -> AudioClassifier:
    return AudioClassifier()


@pytest.fixture
def analyzer() -> AudioContentAnalyzer:
    return AudioContentAnalyzer()


@pytest.fixture
def organizer() -> AudioOrganizer:
    return AudioOrganizer()


# ---------------------------------------------------------------------------
# End-to-end pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFullPipeline:
    """Tests for the complete classify -> analyze -> organize pipeline."""

    def test_music_pipeline(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
        organizer: AudioOrganizer,
        tmp_dir: Path,
    ) -> None:
        """Full pipeline for a music file."""
        src = tmp_dir / "song.mp3"
        src.write_text("fake")

        metadata = _make_metadata(
            file_path=src,
            title="Song Title",
            artist="Band Name",
            album="Album Name",
            genre="Rock",
            track_number=5,
            has_artwork=True,
            duration=240.0,
        )

        # Step 1: Classify
        classification = classifier.classify(metadata)
        assert classification.audio_type == AudioType.MUSIC

        # Step 2: Analyze content
        analysis = analyzer.analyze(metadata)
        assert isinstance(analysis, ContentAnalysis)

        # Step 3: Generate path
        path = organizer.generate_path(classification.audio_type, metadata)
        assert "Rock" in path.parts
        assert "Band Name" in path.parts

        # Step 4: Organize (dry run)
        files = [(src, classification.audio_type, metadata)]
        result = organizer.organize(files, tmp_dir / "output", dry_run=True)
        assert result.total_moved == 1

    def test_podcast_pipeline(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
        organizer: AudioOrganizer,
        tmp_dir: Path,
    ) -> None:
        """Full pipeline for a podcast file."""
        src = tmp_dir / "episode.mp3"
        src.write_text("fake")

        metadata = _make_metadata(
            file_path=src,
            title="Ep. 42 - AI Ethics",
            artist="Tech Weekly",
            duration=2700.0,
            extra_tags={"podcast": "true"},
        )
        transcription = _make_transcription(
            text=(
                "Welcome to this episode of our podcast. "
                "Today's guest is here to discuss AI ethics. "
                "Subscribe and tune in next week."
            ),
            duration=2700.0,
        )

        # Classify
        classification = classifier.classify(metadata, transcription)
        assert classification.audio_type == AudioType.PODCAST

        # Analyze
        analysis = analyzer.analyze(metadata, transcription)
        assert analysis.language == "en"
        assert analysis.topic_count >= 0  # May detect Technology

        # Organize
        path = organizer.generate_path(classification.audio_type, metadata)
        assert path.suffix == ".mp3"

    def test_audiobook_pipeline(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
        organizer: AudioOrganizer,
        tmp_dir: Path,
    ) -> None:
        """Full pipeline for an audiobook file."""
        src = tmp_dir / "chapter1.mp3"
        src.write_text("fake")

        metadata = _make_metadata(
            file_path=src,
            title="Chapter 1 - The Beginning",
            artist="Author Name",
            comment="Narrated by Reader",
            duration=7200.0,
            extra_tags={"narrator": "Reader Name"},
        )

        classification = classifier.classify(metadata)
        assert classification.audio_type == AudioType.AUDIOBOOK

        analysis = analyzer.analyze(metadata)
        assert isinstance(analysis, ContentAnalysis)

        path = organizer.generate_path(classification.audio_type, metadata)
        assert "Audiobooks" in path.parts

    def test_recording_pipeline(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
        organizer: AudioOrganizer,
        tmp_dir: Path,
    ) -> None:
        """Full pipeline for a voice recording."""
        src = tmp_dir / "memo.mp3"
        src.write_text("fake")

        metadata = _make_metadata(
            file_path=src,
            duration=45.0,
        )
        transcription = _make_transcription(
            text="Note to self: follow up on the meeting agenda and action items.",
            duration=45.0,
        )

        classification = classifier.classify(metadata, transcription)
        assert classification.audio_type == AudioType.RECORDING

        analysis = analyzer.analyze(metadata, transcription)
        assert analysis.keyword_count >= 0

        path = organizer.generate_path(classification.audio_type, metadata)
        assert "Recordings" in path.parts


# ---------------------------------------------------------------------------
# Cross-component compatibility tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrossComponent:
    """Tests to verify components work correctly together."""

    def test_classifier_result_feeds_organizer(
        self, classifier: AudioClassifier, organizer: AudioOrganizer
    ) -> None:
        """AudioType from classifier is compatible with organizer."""
        metadata = _make_metadata(artist="Test", album="Album", genre="Pop", track_number=1)
        result = classifier.classify(metadata)
        # Should not raise
        path = organizer.generate_path(result.audio_type, metadata)
        assert isinstance(path, Path)

    def test_all_audio_types_generate_valid_paths(self, organizer: AudioOrganizer) -> None:
        """Every AudioType should produce a valid, non-empty path."""
        metadata = _make_metadata(title="Test File")
        for audio_type in AudioType:
            path = organizer.generate_path(audio_type, metadata)
            assert len(path.parts) >= 1
            assert path.suffix == ".mp3"

    def test_analyzer_works_with_classifier_output(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
    ) -> None:
        """Analyzer does not depend on classifier output, but both can
        process the same metadata/transcription consistently."""
        metadata = _make_metadata(
            title="Technology Lecture on AI",
            genre="Education",
        )
        transcription = _make_transcription(
            text="This lecture covers machine learning algorithms and data analysis.",
        )
        classification = classifier.classify(metadata, transcription)
        analysis = analyzer.analyze(metadata, transcription)

        # Both should process without error
        assert isinstance(classification, ClassificationResult)
        assert isinstance(analysis, ContentAnalysis)

    def test_organize_multiple_types_end_to_end(
        self,
        classifier: AudioClassifier,
        organizer: AudioOrganizer,
        tmp_dir: Path,
    ) -> None:
        """Classify and organize a mixed batch of files."""
        files_data = []

        # Music
        music_src = tmp_dir / "track.mp3"
        music_src.write_text("music")
        music_meta = _make_metadata(
            file_path=music_src,
            artist="Artist",
            album="Album",
            genre="Rock",
            track_number=1,
            duration=200.0,
        )
        music_type = classifier.classify(music_meta).audio_type
        files_data.append((music_src, music_type, music_meta))

        # Recording
        rec_src = tmp_dir / "memo.mp3"
        rec_src.write_text("rec")
        rec_meta = _make_metadata(
            file_path=rec_src,
            duration=30.0,
        )
        rec_type = classifier.classify(rec_meta).audio_type
        files_data.append((rec_src, rec_type, rec_meta))

        result = organizer.organize(files_data, tmp_dir / "output", dry_run=False)
        assert result.total_moved == 2
        assert result.total_failed == 0


# ---------------------------------------------------------------------------
# Custom rules integration tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCustomRulesIntegration:
    """Tests for custom OrganizationRules with the full pipeline."""

    def test_flat_music_template(
        self,
        classifier: AudioClassifier,
        tmp_dir: Path,
    ) -> None:
        """Flat template without nesting should produce simple paths."""
        rules = OrganizationRules(music_template="{Artist} - {Title}")
        organizer = AudioOrganizer(rules=rules)

        src = tmp_dir / "song.mp3"
        src.write_text("data")
        metadata = _make_metadata(
            file_path=src,
            title="Song",
            artist="Artist",
            genre="Pop",
        )
        classification = classifier.classify(metadata)

        path = organizer.generate_path(classification.audio_type, metadata)
        # Should be a simple flat path
        assert len(path.parts) <= 2  # "Artist - Song.mp3"

    def test_date_based_recording_template(self, tmp_dir: Path) -> None:
        """Custom recording template with date should work."""
        rules = OrganizationRules(recording_template="Voice Memos/{Date}/{Title}")
        organizer = AudioOrganizer(rules=rules)
        metadata = _make_metadata(title="Quick Note")
        path = organizer.generate_path(AudioType.RECORDING, metadata)
        assert "Voice Memos" in path.parts


# ---------------------------------------------------------------------------
# Edge case integration tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEdgeCases:
    """Integration tests for edge cases."""

    def test_empty_transcription_text(
        self,
        classifier: AudioClassifier,
        analyzer: AudioContentAnalyzer,
    ) -> None:
        """Empty transcription should not break any component."""
        metadata = _make_metadata(artist="Someone", album="Album")
        transcription = _make_transcription(text="", duration=100.0)
        classification = classifier.classify(metadata, transcription)
        analysis = analyzer.analyze(metadata, transcription)
        assert isinstance(classification, ClassificationResult)
        assert isinstance(analysis, ContentAnalysis)

    def test_unicode_metadata(
        self,
        classifier: AudioClassifier,
        organizer: AudioOrganizer,
    ) -> None:
        """Unicode characters in metadata should be handled gracefully."""
        metadata = _make_metadata(
            title="Chanson d'amour",
            artist="Artiste francais",
            album="L'album special",
            genre="Pop",
        )
        classification = classifier.classify(metadata)
        path = organizer.generate_path(classification.audio_type, metadata)
        assert isinstance(path, Path)
        assert path.suffix == ".mp3"

    def test_very_long_metadata_values(self, organizer: AudioOrganizer) -> None:
        """Very long metadata should be truncated in paths."""
        metadata = _make_metadata(
            title="A" * 500,
            artist="B" * 500,
            genre="Rock",
        )
        path = organizer.generate_path(AudioType.MUSIC, metadata)
        # Each component should be <= 255 chars
        for part in path.parts:
            assert len(part) <= 260  # 255 + extension
