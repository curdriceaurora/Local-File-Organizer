"""Audio Organization Rule Engine.

Generates organized folder structures for audio files based on their
classification type and metadata. Supports customizable path templates,
dry-run previews, and safe file operations.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .classifier import AudioType
from .metadata_extractor import AudioMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path-template defaults
# ---------------------------------------------------------------------------

DEFAULT_MUSIC_TEMPLATE = "{Genre}/{Artist}/{Album}/{TrackNum} - {Title}"
DEFAULT_PODCAST_TEMPLATE = "{Show}/{Year}/{Episode} - {Title}"
DEFAULT_RECORDING_TEMPLATE = "Recordings/{Year}/{Month}/{Topic}/{Date}"
DEFAULT_AUDIOBOOK_TEMPLATE = "Audiobooks/{Author}/{Title}"
DEFAULT_INTERVIEW_TEMPLATE = "Interviews/{Year}/{Title}"
DEFAULT_LECTURE_TEMPLATE = "Lectures/{Year}/{Topic}/{Title}"
DEFAULT_UNKNOWN_TEMPLATE = "Unsorted/{Year}/{Filename}"


@dataclass
class OrganizationRules:
    """Customisable path templates for each audio type."""

    music_template: str = DEFAULT_MUSIC_TEMPLATE
    podcast_template: str = DEFAULT_PODCAST_TEMPLATE
    recording_template: str = DEFAULT_RECORDING_TEMPLATE
    audiobook_template: str = DEFAULT_AUDIOBOOK_TEMPLATE
    interview_template: str = DEFAULT_INTERVIEW_TEMPLATE
    lecture_template: str = DEFAULT_LECTURE_TEMPLATE
    unknown_template: str = DEFAULT_UNKNOWN_TEMPLATE

    def get_template(self, audio_type: AudioType) -> str:
        """Return the path template for a given audio type."""
        mapping: dict[AudioType, str] = {
            AudioType.MUSIC: self.music_template,
            AudioType.PODCAST: self.podcast_template,
            AudioType.RECORDING: self.recording_template,
            AudioType.AUDIOBOOK: self.audiobook_template,
            AudioType.INTERVIEW: self.interview_template,
            AudioType.LECTURE: self.lecture_template,
            AudioType.UNKNOWN: self.unknown_template,
        }
        return mapping.get(audio_type, self.unknown_template)


@dataclass
class FileMove:
    """Record of a single file move operation."""

    source: Path
    destination: Path
    audio_type: AudioType
    success: bool = True
    error: str | None = None


@dataclass
class OrganizationPlan:
    """Preview of planned file organisation (dry-run)."""

    planned_moves: list[FileMove] = field(default_factory=list)
    skipped_files: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total_planned(self) -> int:
        """Return the total number of planned moves."""
        return len(self.planned_moves)

    @property
    def total_skipped(self) -> int:
        """Return the total number of skipped files."""
        return len(self.skipped_files)

    def summary(self) -> str:
        """Return a human-readable summary of the plan."""
        lines = [f"Organization plan: {self.total_planned} files to move"]
        for move in self.planned_moves:
            lines.append(f"  {move.source.name} -> {move.destination}")
        if self.skipped_files:
            lines.append(f"  Skipped: {self.total_skipped} files")
            for path, reason in self.skipped_files:
                lines.append(f"    {path.name}: {reason}")
        return "\n".join(lines)


@dataclass
class OrganizationResult:
    """Outcome of an actual organisation run."""

    moved_files: list[FileMove] = field(default_factory=list)
    failed_files: list[FileMove] = field(default_factory=list)
    skipped_files: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total_moved(self) -> int:
        """Return the total number of moved files."""
        return len(self.moved_files)

    @property
    def total_failed(self) -> int:
        """Return the total number of failed moves."""
        return len(self.failed_files)

    @property
    def total_skipped(self) -> int:
        """Return the total number of skipped files."""
        return len(self.skipped_files)

    def report(self) -> str:
        """Generate a summary report of the organisation run."""
        lines = [
            f"Organization complete: {self.total_moved} moved, "
            f"{self.total_failed} failed, {self.total_skipped} skipped"
        ]
        if self.failed_files:
            lines.append("Failures:")
            for fm in self.failed_files:
                lines.append(f"  {fm.source.name}: {fm.error}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path sanitisation helpers
# ---------------------------------------------------------------------------

# Characters illegal in most filesystems
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTIPLE_SPACES = re.compile(r"\s+")


def sanitize_path_component(value: str) -> str:
    """Sanitise a single path component for filesystem compatibility.

    Removes illegal characters, collapses whitespace, strips leading/trailing
    dots and spaces, and truncates to 255 characters.
    """
    value = _ILLEGAL_CHARS.sub("", value)
    value = _MULTIPLE_SPACES.sub(" ", value)
    value = value.strip(". ")
    # Truncate to filesystem limit
    if len(value) > 255:
        value = value[:255].rstrip(". ")
    return value or "Unknown"


def _format_track_number(track: int | None) -> str:
    """Format a track number as zero-padded string."""
    if track is None:
        return "00"
    return f"{track:02d}"


def _safe_value(value: str | None, fallback: str = "Unknown") -> str:
    """Return sanitised value or fallback if None/empty."""
    if value is None or not value.strip():
        return fallback
    return sanitize_path_component(value.strip())


# ---------------------------------------------------------------------------
# Main organiser
# ---------------------------------------------------------------------------


class AudioOrganizer:
    """Organises audio files into directory structures based on type and metadata.

    Supports customisable templates, dry-run previews, and safe file moves
    with conflict resolution.

    Example:
        >>> organizer = AudioOrganizer()
        >>> plan = organizer.preview_organization(files, base_path)
        >>> print(plan.summary())
        >>> result = organizer.organize(files, base_path, dry_run=False)
    """

    def __init__(
        self,
        rules: OrganizationRules | None = None,
        classifier_fn: object | None = None,
    ) -> None:
        """Initialise the audio organiser.

        Args:
            rules: Organisation rules / templates.  Defaults used if None.
            classifier_fn: Not used directly; classification results are
                passed into generate_path.
        """
        self.rules = rules or OrganizationRules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_path(
        self,
        audio_type: AudioType,
        metadata: AudioMetadata,
    ) -> Path:
        """Generate an organised relative path for a single audio file.

        Args:
            audio_type: The classified audio type.
            metadata: Audio file metadata.

        Returns:
            A relative Path representing the organised location.
        """
        template = self.rules.get_template(audio_type)
        populated = self._populate_template(template, audio_type, metadata)
        # Append original file extension
        extension = metadata.file_path.suffix
        return Path(populated + extension)

    def preview_organization(
        self,
        files: list[tuple[Path, AudioType, AudioMetadata]],
        base_path: Path,
    ) -> OrganizationPlan:
        """Preview organisation without moving any files.

        Args:
            files: List of (source_path, audio_type, metadata) tuples.
            base_path: Root directory to organise into.

        Returns:
            OrganizationPlan describing planned moves.
        """
        plan = OrganizationPlan()

        for source, audio_type, metadata in files:
            if not source.exists():
                plan.skipped_files.append((source, "File does not exist"))
                continue

            try:
                rel_path = self.generate_path(audio_type, metadata)
                dest = base_path / rel_path
                plan.planned_moves.append(
                    FileMove(source=source, destination=dest, audio_type=audio_type)
                )
            except Exception as exc:
                plan.skipped_files.append((source, str(exc)))

        return plan

    def organize(
        self,
        files: list[tuple[Path, AudioType, AudioMetadata]],
        base_path: Path,
        dry_run: bool = True,
    ) -> OrganizationResult:
        """Organise audio files into the target directory structure.

        Args:
            files: List of (source_path, audio_type, metadata) tuples.
            base_path: Root directory to organise into.
            dry_run: If True, only preview without moving.  Default True for safety.

        Returns:
            OrganizationResult with details of moved/failed/skipped files.
        """
        result = OrganizationResult()

        for source, audio_type, metadata in files:
            if not source.exists():
                result.skipped_files.append((source, "File does not exist"))
                continue

            try:
                rel_path = self.generate_path(audio_type, metadata)
                dest = base_path / rel_path
            except Exception as exc:
                result.skipped_files.append((source, str(exc)))
                continue

            if dry_run:
                result.moved_files.append(
                    FileMove(source=source, destination=dest, audio_type=audio_type)
                )
                continue

            # Actual file move
            move = self._move_file(source, dest, audio_type)
            if move.success:
                result.moved_files.append(move)
            else:
                result.failed_files.append(move)

        logger.info(result.report())
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _populate_template(
        self,
        template: str,
        audio_type: AudioType,
        metadata: AudioMetadata,
    ) -> str:
        """Fill in a template string with metadata values."""
        now = datetime.now(UTC)
        file_year = metadata.year or now.year

        # Build substitution map
        values: dict[str, str] = {
            "Genre": _safe_value(metadata.genre, "Unknown Genre"),
            "Artist": _safe_value(metadata.artist, "Unknown Artist"),
            "Album": _safe_value(metadata.album, "Unknown Album"),
            "AlbumArtist": _safe_value(metadata.album_artist, "Unknown Artist"),
            "Title": _safe_value(metadata.title, metadata.file_path.stem),
            "TrackNum": _format_track_number(metadata.track_number),
            "DiscNum": _format_track_number(metadata.disc_number),
            "Year": str(file_year),
            "Month": f"{now.month:02d}",
            "Date": now.strftime("%Y-%m-%d"),
            "Filename": sanitize_path_component(metadata.file_path.stem),
            # Podcast / show fields (fall back to title / artist)
            "Show": _safe_value(metadata.album_artist or metadata.artist, "Unknown Show"),
            "Episode": _safe_value(metadata.title, "Untitled Episode"),
            # Audiobook fields
            "Author": _safe_value(metadata.artist, "Unknown Author"),
            # Lecture / interview fields
            "Topic": _safe_value(metadata.title, "Untitled"),
        }

        # Perform substitution
        result = template
        for key, val in values.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, val)

        # Sanitise each path component individually
        parts = Path(result).parts
        sanitized_parts = [sanitize_path_component(p) for p in parts]
        return str(Path(*sanitized_parts)) if sanitized_parts else "Unsorted"

    @staticmethod
    def _move_file(source: Path, dest: Path, audio_type: AudioType) -> FileMove:
        """Move a single file, creating parent directories as needed."""
        try:
            # Create destination directory
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Handle name conflicts
            final_dest = dest
            if final_dest.exists():
                final_dest = _resolve_conflict(final_dest)

            shutil.move(str(source), str(final_dest))
            logger.info(f"Moved: {source} -> {final_dest}")
            return FileMove(
                source=source,
                destination=final_dest,
                audio_type=audio_type,
                success=True,
            )
        except Exception as exc:
            logger.error(f"Failed to move {source}: {exc}")
            return FileMove(
                source=source,
                destination=dest,
                audio_type=audio_type,
                success=False,
                error=str(exc),
            )


def _resolve_conflict(dest: Path) -> Path:
    """Resolve filename conflicts by appending a numeric suffix.

    e.g. song.mp3 -> song (1).mp3 -> song (2).mp3
    """
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 9999:
            raise RuntimeError(f"Too many conflicting files for {dest.name}")
