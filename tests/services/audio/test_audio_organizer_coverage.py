"""Coverage tests for AudioOrganizer — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.audio.classifier import AudioType
from file_organizer.services.audio.metadata_extractor import AudioMetadata
from file_organizer.services.audio.organizer import (
    AudioOrganizer,
    FileMove,
    OrganizationResult,
    OrganizationRules,
    _resolve_conflict,
    sanitize_path_component,
)

pytestmark = pytest.mark.unit


def _make_metadata(
    file_path: Path,
    title: str = "Test Song",
    artist: str = "Test Artist",
    album: str = "Test Album",
    genre: str = "Rock",
    year: int | None = 2024,
    track_number: int | None = 1,
    disc_number: int | None = None,
    album_artist: str | None = None,
) -> AudioMetadata:
    return AudioMetadata(
        file_path=file_path,
        file_size=1024,
        format="mp3",
        duration=180.0,
        bitrate=320000,
        sample_rate=44100,
        channels=2,
        title=title,
        artist=artist,
        album=album,
        genre=genre,
        year=year,
        track_number=track_number,
        disc_number=disc_number,
        album_artist=album_artist,
    )


@pytest.fixture()
def organizer():
    return AudioOrganizer()


# ---------------------------------------------------------------------------
# OrganizationRules
# ---------------------------------------------------------------------------


class TestRules:
    def test_get_template_all_types(self):
        rules = OrganizationRules()
        for audio_type in AudioType:
            template = rules.get_template(audio_type)
            assert isinstance(template, str)
            assert len(template) > 0


# ---------------------------------------------------------------------------
# sanitize_path_component
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_removes_illegal_chars(self):
        assert "ab" == sanitize_path_component("a<b")

    def test_collapses_whitespace(self):
        assert "a b" == sanitize_path_component("a   b")

    def test_strips_dots_spaces(self):
        assert "test" == sanitize_path_component("...test...")

    def test_empty_returns_unknown(self):
        assert "Unknown" == sanitize_path_component("")

    def test_truncates_long(self):
        result = sanitize_path_component("a" * 300)
        assert len(result) <= 255


# ---------------------------------------------------------------------------
# generate_path
# ---------------------------------------------------------------------------


class TestGeneratePath:
    def test_music(self, organizer, tmp_path):
        meta = _make_metadata(tmp_path / "song.mp3")
        path = organizer.generate_path(AudioType.MUSIC, meta)
        assert "Rock" in str(path)
        assert "Test Artist" in str(path)

    def test_podcast(self, organizer, tmp_path):
        meta = _make_metadata(
            tmp_path / "ep.mp3",
            album_artist="Show Name",
        )
        path = organizer.generate_path(AudioType.PODCAST, meta)
        assert "Show Name" in str(path)

    def test_audiobook(self, organizer, tmp_path):
        meta = _make_metadata(tmp_path / "ch1.mp3", artist="Author Name")
        path = organizer.generate_path(AudioType.AUDIOBOOK, meta)
        assert "Author Name" in str(path)

    def test_unknown_type(self, organizer, tmp_path):
        meta = _make_metadata(tmp_path / "file.mp3")
        path = organizer.generate_path(AudioType.UNKNOWN, meta)
        assert "Unsorted" in str(path)

    def test_none_metadata_fields(self, organizer, tmp_path):
        meta = _make_metadata(
            tmp_path / "file.mp3",
            title=None,
            artist=None,
            album=None,
            genre=None,
            year=None,
            track_number=None,
        )
        path = organizer.generate_path(AudioType.MUSIC, meta)
        assert "Unknown" in str(path)


# ---------------------------------------------------------------------------
# preview_organization
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_existing_files(self, organizer, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"\x00")
        meta = _make_metadata(f)
        plan = organizer.preview_organization([(f, AudioType.MUSIC, meta)], tmp_path / "output")
        assert plan.total_planned == 1

    def test_preview_missing_file(self, organizer, tmp_path):
        f = tmp_path / "missing.mp3"
        meta = _make_metadata(f)
        plan = organizer.preview_organization([(f, AudioType.MUSIC, meta)], tmp_path / "output")
        assert plan.total_skipped == 1

    def test_plan_summary(self, organizer, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"\x00")
        meta = _make_metadata(f)
        plan = organizer.preview_organization([(f, AudioType.MUSIC, meta)], tmp_path / "output")
        s = plan.summary()
        assert "1 files to move" in s


# ---------------------------------------------------------------------------
# organize
# ---------------------------------------------------------------------------


class TestOrganize:
    def test_dry_run(self, organizer, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"\x00")
        meta = _make_metadata(f)
        result = organizer.organize([(f, AudioType.MUSIC, meta)], tmp_path / "output", dry_run=True)
        assert result.total_moved == 1

    def test_actual_move(self, organizer, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"\x00" * 100)
        meta = _make_metadata(f)
        result = organizer.organize(
            [(f, AudioType.MUSIC, meta)], tmp_path / "output", dry_run=False
        )
        assert result.total_moved == 1

    def test_skips_missing(self, organizer, tmp_path):
        f = tmp_path / "missing.mp3"
        meta = _make_metadata(f)
        result = organizer.organize(
            [(f, AudioType.MUSIC, meta)], tmp_path / "output", dry_run=False
        )
        assert result.total_skipped == 1

    def test_report(self, organizer, tmp_path):
        result = OrganizationResult()
        result.moved_files.append(
            FileMove(
                source=tmp_path / "a.mp3",
                destination=tmp_path / "b.mp3",
                audio_type=AudioType.MUSIC,
            )
        )
        report = result.report()
        assert "1 moved" in report

    def test_report_with_failures(self):
        result = OrganizationResult()
        result.failed_files.append(
            FileMove(
                source=Path("/a.mp3"),
                destination=Path("/b.mp3"),
                audio_type=AudioType.MUSIC,
                success=False,
                error="Permission denied",
            )
        )
        report = result.report()
        assert "Failures" in report


# ---------------------------------------------------------------------------
# _resolve_conflict
# ---------------------------------------------------------------------------


class TestResolveConflict:
    def test_resolve_adds_suffix(self, tmp_path):
        dest = tmp_path / "song.mp3"
        dest.write_bytes(b"\x00")
        resolved = _resolve_conflict(dest)
        assert "song (1)" in resolved.name

    def test_resolve_increments(self, tmp_path):
        dest = tmp_path / "song.mp3"
        dest.write_bytes(b"\x00")
        (tmp_path / "song (1).mp3").write_bytes(b"\x00")
        resolved = _resolve_conflict(dest)
        assert "song (2)" in resolved.name
