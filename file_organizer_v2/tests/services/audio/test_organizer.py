"""
Tests for AudioOrganizer - Audio Organisation Rule Engine

Tests cover:
- Path generation from templates
- Path sanitisation
- Template population for each audio type
- Dry-run organisation preview
- Actual file move operations
- Conflict resolution
- Custom organisation rules
- Edge cases (missing metadata, illegal characters)
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.services.audio.classifier import AudioType
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.organizer import (
    DEFAULT_MUSIC_TEMPLATE,
    DEFAULT_PODCAST_TEMPLATE,
    AudioOrganizer,
    OrganizationPlan,
    OrganizationRules,
    _format_track_number,
    _resolve_conflict,
    _safe_value,
    sanitize_path_component,
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
    """Helper to create AudioMetadata with sensible defaults."""
    return AudioMetadata(
        file_path=file_path or Path("/tmp/test_audio.mp3"),
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


@pytest.fixture
def organizer() -> AudioOrganizer:
    return AudioOrganizer()


@pytest.fixture
def tmp_dir():
    """Provide a temp directory that is cleaned up after the test."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# sanitize_path_component tests
# ---------------------------------------------------------------------------


class TestSanitizePathComponent:
    """Tests for path component sanitisation."""

    def test_removes_illegal_chars(self) -> None:
        assert sanitize_path_component('file<>:"/\\|?*name') == "filename"

    def test_collapses_whitespace(self) -> None:
        assert sanitize_path_component("hello   world") == "hello world"

    def test_strips_dots_and_spaces(self) -> None:
        assert sanitize_path_component("..filename..") == "filename"

    def test_truncates_long_names(self) -> None:
        long_name = "a" * 300
        result = sanitize_path_component(long_name)
        assert len(result) <= 255

    def test_empty_returns_unknown(self) -> None:
        assert sanitize_path_component("") == "Unknown"

    def test_only_dots(self) -> None:
        assert sanitize_path_component("...") == "Unknown"


class TestSafeValue:
    """Tests for _safe_value helper."""

    def test_none_returns_fallback(self) -> None:
        assert _safe_value(None, "Fallback") == "Fallback"

    def test_empty_returns_fallback(self) -> None:
        assert _safe_value("  ", "Fallback") == "Fallback"

    def test_valid_value(self) -> None:
        assert _safe_value("Hello World") == "Hello World"

    def test_sanitises_value(self) -> None:
        result = _safe_value("Hello: World")
        assert ":" not in result


class TestFormatTrackNumber:
    """Tests for track number formatting."""

    def test_none_returns_00(self) -> None:
        assert _format_track_number(None) == "00"

    def test_single_digit(self) -> None:
        assert _format_track_number(5) == "05"

    def test_double_digit(self) -> None:
        assert _format_track_number(12) == "12"


# ---------------------------------------------------------------------------
# OrganizationRules tests
# ---------------------------------------------------------------------------


class TestOrganizationRules:
    """Tests for OrganizationRules configuration."""

    def test_default_templates(self) -> None:
        rules = OrganizationRules()
        assert rules.music_template == DEFAULT_MUSIC_TEMPLATE
        assert rules.podcast_template == DEFAULT_PODCAST_TEMPLATE

    def test_custom_template(self) -> None:
        rules = OrganizationRules(music_template="{Artist} - {Title}")
        assert rules.music_template == "{Artist} - {Title}"

    def test_get_template_music(self) -> None:
        rules = OrganizationRules()
        assert rules.get_template(AudioType.MUSIC) == DEFAULT_MUSIC_TEMPLATE

    def test_get_template_unknown_fallback(self) -> None:
        rules = OrganizationRules()
        template = rules.get_template(AudioType.UNKNOWN)
        assert "Unsorted" in template


# ---------------------------------------------------------------------------
# generate_path tests
# ---------------------------------------------------------------------------


class TestGeneratePath:
    """Tests for path generation from templates."""

    def test_music_path(self, organizer: AudioOrganizer) -> None:
        """Music template should produce Genre/Artist/Album/Track - Title."""
        metadata = _make_metadata(
            title="Song Name",
            artist="Artist Name",
            album="Album Name",
            genre="Rock",
            track_number=3,
        )
        path = organizer.generate_path(AudioType.MUSIC, metadata)
        parts = path.parts
        assert "Rock" in parts
        assert "Artist Name" in parts
        assert "Album Name" in parts
        assert path.name.startswith("03 - Song Name")
        assert path.suffix == ".mp3"

    def test_podcast_path(self, organizer: AudioOrganizer) -> None:
        """Podcast template should include show and year."""
        metadata = _make_metadata(
            title="Episode Title",
            artist="Podcast Host",
            year=2024,
        )
        path = organizer.generate_path(AudioType.PODCAST, metadata)
        assert "2024" in str(path)
        assert path.suffix == ".mp3"

    def test_audiobook_path(self, organizer: AudioOrganizer) -> None:
        """Audiobook template should include author and title."""
        metadata = _make_metadata(
            title="Chapter 1",
            artist="Author Name",
        )
        path = organizer.generate_path(AudioType.AUDIOBOOK, metadata)
        parts = path.parts
        assert "Audiobooks" in parts
        assert "Author Name" in parts

    def test_recording_path(self, organizer: AudioOrganizer) -> None:
        """Recording template should include Recordings directory and year."""
        metadata = _make_metadata(title="Meeting Notes", year=2024)
        path = organizer.generate_path(AudioType.RECORDING, metadata)
        parts = path.parts
        assert "Recordings" in parts
        assert "2024" in parts

    def test_unknown_path(self, organizer: AudioOrganizer) -> None:
        """Unknown audio should go to Unsorted directory."""
        metadata = _make_metadata()
        path = organizer.generate_path(AudioType.UNKNOWN, metadata)
        assert "Unsorted" in path.parts

    def test_missing_metadata_uses_fallbacks(self, organizer: AudioOrganizer) -> None:
        """Missing fields should produce 'Unknown ...' fallback values."""
        metadata = _make_metadata()  # No title, artist, album, genre
        path = organizer.generate_path(AudioType.MUSIC, metadata)
        path_str = str(path)
        assert "Unknown" in path_str

    def test_illegal_chars_in_metadata(self, organizer: AudioOrganizer) -> None:
        """Illegal filesystem characters should be stripped from paths."""
        metadata = _make_metadata(
            title='Song: "Special" <Edition>',
            artist="Artist/Band",
            album="Album|Name",
            genre="Rock",
        )
        path = organizer.generate_path(AudioType.MUSIC, metadata)
        path_str = str(path)
        assert ":" not in path_str
        assert '"' not in path_str
        assert "<" not in path_str
        assert ">" not in path_str
        assert "|" not in path_str

    def test_custom_template(self) -> None:
        """Custom rules should be respected in path generation."""
        rules = OrganizationRules(music_template="{Artist}/{Title}")
        organizer = AudioOrganizer(rules=rules)
        metadata = _make_metadata(title="MySong", artist="MyArtist")
        path = organizer.generate_path(AudioType.MUSIC, metadata)
        assert path.parts[0] == "MyArtist"
        assert path.stem == "MySong"


# ---------------------------------------------------------------------------
# preview_organization tests
# ---------------------------------------------------------------------------


class TestPreviewOrganization:
    """Tests for dry-run preview."""

    def test_preview_returns_plan(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Preview should return an OrganizationPlan."""
        # Create a real temp file
        src = tmp_dir / "song.mp3"
        src.touch()
        metadata = _make_metadata(file_path=src, title="Song", artist="Artist", genre="Pop")
        files = [(src, AudioType.MUSIC, metadata)]
        plan = organizer.preview_organization(files, tmp_dir / "output")
        assert isinstance(plan, OrganizationPlan)
        assert plan.total_planned == 1

    def test_preview_skips_missing_files(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Non-existent source files should be skipped."""
        metadata = _make_metadata(file_path=tmp_dir / "nonexistent.mp3")
        files = [(tmp_dir / "nonexistent.mp3", AudioType.MUSIC, metadata)]
        plan = organizer.preview_organization(files, tmp_dir / "output")
        assert plan.total_planned == 0
        assert plan.total_skipped == 1

    def test_preview_summary(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Summary should contain meaningful text."""
        src = tmp_dir / "test.mp3"
        src.touch()
        metadata = _make_metadata(file_path=src, title="Test")
        files = [(src, AudioType.UNKNOWN, metadata)]
        plan = organizer.preview_organization(files, tmp_dir / "output")
        summary = plan.summary()
        assert "1 files to move" in summary


# ---------------------------------------------------------------------------
# organize tests (dry_run=True)
# ---------------------------------------------------------------------------


class TestOrganizeDryRun:
    """Tests for organization in dry-run mode."""

    def test_dry_run_does_not_move(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Dry run should not physically move files."""
        src = tmp_dir / "song.mp3"
        src.write_text("fake audio data")
        metadata = _make_metadata(file_path=src, title="Song", artist="Artist", genre="Pop")
        files = [(src, AudioType.MUSIC, metadata)]
        result = organizer.organize(files, tmp_dir / "output", dry_run=True)
        assert result.total_moved == 1
        assert result.total_failed == 0
        # File should still be in original location
        assert src.exists()

    def test_dry_run_skips_nonexistent(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Dry run should report skipped files."""
        metadata = _make_metadata(file_path=tmp_dir / "gone.mp3")
        files = [(tmp_dir / "gone.mp3", AudioType.MUSIC, metadata)]
        result = organizer.organize(files, tmp_dir / "output", dry_run=True)
        assert result.total_moved == 0
        assert result.total_skipped == 1


# ---------------------------------------------------------------------------
# organize tests (dry_run=False)
# ---------------------------------------------------------------------------


class TestOrganizeActual:
    """Tests for actual file organisation."""

    def test_actual_move(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Actual run should physically move files."""
        src = tmp_dir / "song.mp3"
        src.write_text("fake audio data")
        metadata = _make_metadata(
            file_path=src, title="Song", artist="Artist", genre="Pop", track_number=1
        )
        output = tmp_dir / "output"
        files = [(src, AudioType.MUSIC, metadata)]
        result = organizer.organize(files, output, dry_run=False)
        assert result.total_moved == 1
        assert result.total_failed == 0
        # Source should no longer exist
        assert not src.exists()
        # Destination should exist
        assert result.moved_files[0].destination.exists()

    def test_creates_directories(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Organisation should create nested directories."""
        src = tmp_dir / "track.mp3"
        src.write_text("data")
        metadata = _make_metadata(
            file_path=src,
            title="Track",
            artist="Artist",
            album="Album",
            genre="Jazz",
            track_number=2,
        )
        output = tmp_dir / "organized"
        files = [(src, AudioType.MUSIC, metadata)]
        result = organizer.organize(files, output, dry_run=False)
        dest = result.moved_files[0].destination
        assert dest.parent.exists()
        assert dest.parent.is_dir()

    def test_conflict_resolution(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Duplicate filenames should be resolved with numeric suffix."""
        output = tmp_dir / "organized"

        # Create first file and move it
        src1 = tmp_dir / "song1.mp3"
        src1.write_text("data1")
        meta1 = _make_metadata(
            file_path=src1, title="Same", artist="Artist", genre="Pop", track_number=1
        )

        src2 = tmp_dir / "song2.mp3"
        src2.write_text("data2")
        meta2 = _make_metadata(
            file_path=src2, title="Same", artist="Artist", genre="Pop", track_number=1
        )

        # Move first file
        result1 = organizer.organize([(src1, AudioType.MUSIC, meta1)], output, dry_run=False)
        assert result1.total_moved == 1

        # Move second file (same destination)
        result2 = organizer.organize([(src2, AudioType.MUSIC, meta2)], output, dry_run=False)
        assert result2.total_moved == 1
        # Destination should have " (1)" suffix
        assert "(1)" in result2.moved_files[0].destination.stem

    def test_report_generation(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """OrganizationResult.report() should return a meaningful string."""
        src = tmp_dir / "test.mp3"
        src.write_text("data")
        metadata = _make_metadata(file_path=src, title="Test")
        files = [(src, AudioType.UNKNOWN, metadata)]
        result = organizer.organize(files, tmp_dir / "out", dry_run=False)
        report = result.report()
        assert "1 moved" in report


# ---------------------------------------------------------------------------
# _resolve_conflict tests
# ---------------------------------------------------------------------------


class TestResolveConflict:
    """Tests for filename conflict resolution."""

    def test_no_conflict(self, tmp_dir: Path) -> None:
        """When no conflict exists, path is returned as-is... wait, it should
        only be called when conflict exists.  Test with existing file."""
        existing = tmp_dir / "file.mp3"
        existing.touch()
        resolved = _resolve_conflict(existing)
        assert resolved.stem == "file (1)"
        assert resolved.suffix == ".mp3"

    def test_multiple_conflicts(self, tmp_dir: Path) -> None:
        """Should increment counter for each existing conflict."""
        for i in range(3):
            if i == 0:
                (tmp_dir / "file.mp3").touch()
            else:
                (tmp_dir / f"file ({i}).mp3").touch()
        resolved = _resolve_conflict(tmp_dir / "file.mp3")
        assert resolved.stem == "file (3)"


# ---------------------------------------------------------------------------
# Multiple files organisation
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    """Tests for organising multiple files at once."""

    def test_multiple_types(self, organizer: AudioOrganizer, tmp_dir: Path) -> None:
        """Different audio types should go to different directories."""
        output = tmp_dir / "organized"
        files_data = []

        # Create music file
        music = tmp_dir / "song.mp3"
        music.write_text("music")
        music_meta = _make_metadata(file_path=music, title="Song", artist="Artist", genre="Rock")
        files_data.append((music, AudioType.MUSIC, music_meta))

        # Create podcast file
        podcast = tmp_dir / "episode.mp3"
        podcast.write_text("podcast")
        pod_meta = _make_metadata(file_path=podcast, title="Ep 1", artist="Host")
        files_data.append((podcast, AudioType.PODCAST, pod_meta))

        result = organizer.organize(files_data, output, dry_run=False)
        assert result.total_moved == 2

        # Verify they went to different parent directories
        parents = {m.destination.parts[len(output.parts)] for m in result.moved_files}
        assert len(parents) == 2
