"""TUI view for audio file browsing, metadata, and classification.

Provides panels showing discovered audio files, metadata details,
and AI-powered classification results.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

if TYPE_CHECKING:
    from file_organizer.services.audio.classifier import ClassificationResult
    from file_organizer.services.audio.metadata_extractor import AudioMetadata

# Audio file extensions to scan for
_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".m4a", ".ogg"})
_MAX_SCAN_FILES = 50


class AudioFileListPanel(Static):
    """Table of discovered audio files."""

    DEFAULT_CSS = """
    AudioFileListPanel {
        height: auto;
        padding: 1 2;
    }
    """

    def set_files(self, files: list[tuple[str, str, str]]) -> None:
        """Render a table of audio files.

        Args:
            files: List of (name, format, duration) tuples.
        """
        if not files:
            self.update("[b]Audio Files[/b]\n\n  [dim]No audio files found.[/dim]")
            return

        lines = [
            f"[b]Audio Files[/b]  ({len(files)} found)\n",
            f"  {'#':<4} {'Name':<35} {'Format':<8} {'Duration'}",
            "  " + "-" * 60,
        ]
        for idx, (name, fmt, duration) in enumerate(files, 1):
            display_name = _truncate(name, 33)
            lines.append(f"  {idx:<4} {display_name:<35} {fmt:<8} {duration}")

        self.update("\n".join(lines))


class AudioMetadataPanel(Static):
    """Displays detailed metadata for a selected audio file."""

    DEFAULT_CSS = """
    AudioMetadataPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
    }
    """

    def set_metadata(self, metadata: AudioMetadata | None) -> None:
        """Update the metadata display.

        Args:
            metadata: AudioMetadata instance or None.
        """
        if metadata is None:
            self.update("[b]Metadata[/b]\n\n  [dim]Select a file to view metadata.[/dim]")
            return

        # Import here to get format helpers
        try:
            from file_organizer.services.audio.metadata_extractor import (
                AudioMetadataExtractor,
            )

            duration_str = AudioMetadataExtractor.format_duration(metadata.duration)
            bitrate_str = AudioMetadataExtractor.format_bitrate(metadata.bitrate)
        except Exception:
            duration_str = f"{metadata.duration:.1f}s"
            bitrate_str = f"{metadata.bitrate} bps"

        # Calculate tag completeness
        tag_fields = [
            metadata.title,
            metadata.artist,
            metadata.album,
            metadata.genre,
            metadata.year,
        ]
        filled = sum(1 for f in tag_fields if f is not None)
        completeness = int(filled / len(tag_fields) * 100)
        bar_filled = int(filled / len(tag_fields) * 20)
        bar = "[green]" + "#" * bar_filled + "[/green]" + "." * (20 - bar_filled)

        lines = [
            "[b]Metadata[/b]\n",
            f"  Title:        {metadata.title or '[dim]unknown[/dim]'}",
            f"  Artist:       {metadata.artist or '[dim]unknown[/dim]'}",
            f"  Album:        {metadata.album or '[dim]unknown[/dim]'}",
            f"  Genre:        {metadata.genre or '[dim]unknown[/dim]'}",
            f"  Year:         {metadata.year or '[dim]unknown[/dim]'}",
            "",
            f"  Duration:     {duration_str}",
            f"  Bitrate:      {bitrate_str}",
            f"  Sample rate:  {metadata.sample_rate} Hz",
            f"  Channels:     {metadata.channels}",
            "",
            f"  Tag complete: {bar} {completeness}%",
        ]
        self.update("\n".join(lines))


class AudioClassificationPanel(Static):
    """Displays AI classification result for a selected audio file."""

    DEFAULT_CSS = """
    AudioClassificationPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
        background: $surface;
    }
    """

    def set_classification(self, result: ClassificationResult | None) -> None:
        """Update the classification display.

        Args:
            result: ClassificationResult instance or None.
        """
        if result is None:
            self.update("[b]Classification[/b]\n\n  [dim]No classification available.[/dim]")
            return

        audio_type = (
            str(result.audio_type.value)
            if hasattr(result.audio_type, "value")
            else str(result.audio_type)
        )
        confidence = result.confidence
        conf_bar_len = int(confidence * 30)
        color = "green" if confidence >= 0.7 else "yellow" if confidence >= 0.4 else "red"
        conf_bar = f"[{color}]" + "#" * conf_bar_len + f"[/{color}]" + "." * (30 - conf_bar_len)

        lines = [
            "[b]Classification[/b]\n",
            f"  Type:       [bold]{audio_type}[/bold]",
            f"  Confidence: {conf_bar} {confidence:.0%}",
            f"  Reasoning:  {result.reasoning}",
        ]

        if result.alternatives:
            lines.append("\n  [dim]Alternatives:[/dim]")
            for alt in result.alternatives[:3]:
                alt_type = (
                    str(alt.audio_type.value)
                    if hasattr(alt.audio_type, "value")
                    else str(alt.audio_type)
                )
                lines.append(f"    {alt_type:<12} {alt.confidence:.0%}  {alt.reasoning}")

        self.update("\n".join(lines))


class AudioView(Vertical):
    """Audio file browser and classifier view mounted as ``#view``.

    Bindings:
        r - Refresh / rescan audio files
        j - Select next file
        k - Select previous file
    """

    DEFAULT_CSS = """
    AudioView {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_audio", "Refresh", show=True),
        Binding("j", "next_file", "Next", show=True),
        Binding("k", "prev_file", "Prev", show=True),
    ]

    def __init__(
        self,
        scan_dir: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the audio view to scan the given directory."""
        super().__init__(name=name, id=id, classes=classes)
        self._scan_dir = Path(scan_dir)
        self._files: list[
            tuple[Path, AudioMetadata | None, ClassificationResult | None]
        ] = []  # (path, metadata, classification)
        self._current_index: int = 0

    def compose(self) -> ComposeResult:
        """Build the audio view layout."""
        yield Static("[b]Audio Files[/b]\n", id="audio-header")
        yield AudioFileListPanel("[dim]Scanning...[/dim]")
        yield AudioMetadataPanel("[dim]Loading...[/dim]")
        yield AudioClassificationPanel("[dim]Loading...[/dim]")

    def on_mount(self) -> None:
        """Trigger the initial audio scan."""
        self._scan_audio_files()

    def action_refresh_audio(self) -> None:
        """Rescan audio files."""
        self.query_one(AudioFileListPanel).update("[dim]Scanning...[/dim]")
        self.query_one(AudioMetadataPanel).update("[dim]Loading...[/dim]")
        self.query_one(AudioClassificationPanel).update("[dim]Loading...[/dim]")
        self._files = []
        self._current_index = 0
        self._scan_audio_files()

    def action_next_file(self) -> None:
        """Select the next audio file."""
        if not self._files:
            return
        self._current_index = min(self._current_index + 1, len(self._files) - 1)
        self._show_file_details(self._current_index)

    def action_prev_file(self) -> None:
        """Select the previous audio file."""
        if not self._files:
            return
        self._current_index = max(self._current_index - 1, 0)
        self._show_file_details(self._current_index)

    @work(thread=True)
    def _scan_audio_files(self) -> None:
        """Scan directory for audio files in a worker thread."""
        try:
            from file_organizer.services.audio.classifier import AudioClassifier
            from file_organizer.services.audio.metadata_extractor import (
                AudioMetadataExtractor,
            )

            extractor = AudioMetadataExtractor()
            classifier = AudioClassifier()

            # Collect audio files
            audio_paths: list[Path] = []
            scan_dir = self._scan_dir
            if scan_dir.is_dir():
                for p in sorted(scan_dir.rglob("*")):
                    if p.suffix.lower() in _AUDIO_EXTENSIONS and p.is_file():
                        audio_paths.append(p)
                        if len(audio_paths) >= _MAX_SCAN_FILES:
                            break

            if not audio_paths:
                self.app.call_from_thread(
                    self.query_one(AudioFileListPanel).set_files,
                    [],
                )
                self.app.call_from_thread(
                    self.query_one(AudioMetadataPanel).set_metadata,
                    None,
                )
                self.app.call_from_thread(
                    self.query_one(AudioClassificationPanel).set_classification,
                    None,
                )
                self.app.call_from_thread(self._set_status, "No audio files found")
                return

            # Extract metadata and classify each file
            file_entries: list[tuple[str, str, str]] = []
            file_data: list[tuple[Path, AudioMetadata | None, ClassificationResult | None]] = []

            for audio_path in audio_paths:
                try:
                    metadata = extractor.extract(audio_path)
                    classification = classifier.classify(metadata)
                    duration_str = AudioMetadataExtractor.format_duration(metadata.duration)
                    file_entries.append((audio_path.name, metadata.format, duration_str))
                    file_data.append((audio_path, metadata, classification))
                except Exception:
                    file_entries.append((audio_path.name, audio_path.suffix.lstrip("."), "?"))
                    file_data.append((audio_path, None, None))

            self._files = file_data

            self.app.call_from_thread(
                self.query_one(AudioFileListPanel).set_files,
                file_entries,
            )

            # Show first file details
            if file_data:
                self._current_index = 0
                _, first_metadata, first_classification = file_data[0]
                self.app.call_from_thread(
                    self.query_one(AudioMetadataPanel).set_metadata,
                    first_metadata,
                )
                self.app.call_from_thread(
                    self.query_one(AudioClassificationPanel).set_classification,
                    first_classification,
                )

            self.app.call_from_thread(
                self._set_status,
                f"Audio: {len(file_data)} files loaded",
            )

        except ImportError as exc:
            msg = f"[red]Audio features unavailable:[/red] {exc}\n\n  Install: pip install mutagen"
            for panel_type in (AudioFileListPanel, AudioMetadataPanel, AudioClassificationPanel):
                self.app.call_from_thread(self.query_one(panel_type).update, msg)
        except Exception as exc:
            msg = f"[red]Audio scan failed:[/red] {exc}"
            for panel_type in (AudioFileListPanel, AudioMetadataPanel, AudioClassificationPanel):
                self.app.call_from_thread(self.query_one(panel_type).update, msg)

    def _show_file_details(self, index: int) -> None:
        """Update metadata and classification panels for the file at index.

        Args:
            index: Index into self._files.
        """
        if index < 0 or index >= len(self._files):
            return
        _, metadata, classification = self._files[index]
        self.query_one(AudioMetadataPanel).set_metadata(metadata)
        self.query_one(AudioClassificationPanel).set_classification(classification)

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            pass


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long.

    Args:
        text: Text to truncate.
        max_len: Maximum length.

    Returns:
        Truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"
