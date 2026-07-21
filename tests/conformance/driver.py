"""Adapter-driver protocol and direct-service oracle driver (#1605).

Every surface adapter (#1595-#1598) implements
:class:`OrganizationConformanceDriver` for its own transport and runs the same
corpus through it.  :class:`DirectServiceDriver` drives the canonical
:class:`~file_organizer.core.organization_service.OrganizationService` and is
the behavioral oracle: golden expectations are captured from it and never from
an adapter.

Determinism seams
-----------------
The oracle keeps model-free canonical semantics deterministic by:

- leaving the text/vision processors uninitialized so classification uses the
  canonical extension-fallback policy;
- replacing byte-level audio/video metadata *parsing* (mutagen/cv2, which vary
  by environment) with fixed per-filename metadata, while the canonical
  classifier and path-generation policy still run unmodified;
- recording audit events in an isolated per-execution history database.

Adapter drivers run in-process (CliRunner, TestClient, Textual pilot) and are
expected to install the same extractor stubs so all surfaces are compared on
identical inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from file_organizer.core import dispatcher
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.history.tracker import OperationHistory
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.services.audio.metadata_extractor import (
    AudioMetadata,
    AudioMetadataExtractor,
)
from file_organizer.services.video.metadata_extractor import (
    VideoMetadata,
    VideoMetadataExtractor,
)
from file_organizer.undo import UndoManager
from tests.conformance.normalize import (
    normalize_audit_events,
    normalize_error,
    normalize_plan,
    normalize_result,
    normalize_scan,
)

#: Model identity every driver must resolve requests against, so plans are
#: byte-comparable across surfaces without contacting any provider.
CONFORMANCE_TEXT_MODEL = ModelConfig("conformance-text", ModelType.TEXT)
CONFORMANCE_VISION_MODEL = ModelConfig("conformance-vision", ModelType.VISION)

#: Fixed audio metadata keyed by filename; unknown filenames get untagged
#: defaults.  Part of the published corpus contract: adapter drivers must
#: stub the same values.
AUDIO_METADATA_BY_NAME: dict[str, dict[str, Any]] = {
    "song.mp3": {
        "title": "Fixture Song",
        "artist": "Fixture Artist",
        "album": "Fixture Album",
        "genre": "Rock",
        "duration": 240.0,
    },
}

#: Fixed video metadata keyed by filename; unknown filenames get metadata-less
#: defaults that route to the canonical unsorted fallback.
VIDEO_METADATA_BY_NAME: dict[str, dict[str, Any]] = {
    "movie.mkv": {
        "duration": 5400.0,
        "width": 1920,
        "height": 1080,
        "creation_date": datetime(2026, 1, 1, tzinfo=UTC),
    },
    "clip.mp4": {"duration": 12.0, "width": 1280, "height": 720},
}


class DeterministicAudioExtractor(AudioMetadataExtractor):
    """Return pinned audio metadata so canonical routing has fixed inputs."""

    def extract(self, audio_path: str | Path) -> AudioMetadata:
        """Build metadata from the corpus table instead of parsing bytes."""
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        overrides = AUDIO_METADATA_BY_NAME.get(path.name, {})
        return AudioMetadata(
            file_path=path,
            file_size=path.stat().st_size,
            format=path.suffix.lstrip(".").lower(),
            duration=overrides.get("duration", 0.0),
            bitrate=0,
            sample_rate=44100,
            channels=2,
            title=overrides.get("title"),
            artist=overrides.get("artist"),
            album=overrides.get("album"),
            genre=overrides.get("genre"),
        )


class DeterministicVideoExtractor(VideoMetadataExtractor):
    """Return pinned video metadata so canonical routing has fixed inputs."""

    def extract(self, video_path: str | Path) -> VideoMetadata:
        """Build metadata from the corpus table instead of probing with cv2."""
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")
        overrides = VIDEO_METADATA_BY_NAME.get(path.name, {})
        return VideoMetadata(
            file_path=path,
            file_size=path.stat().st_size,
            format=path.suffix.lstrip(".").lower(),
            duration=overrides.get("duration"),
            width=overrides.get("width"),
            height=overrides.get("height"),
            creation_date=overrides.get("creation_date"),
        )


@runtime_checkable
class OrganizationConformanceDriver(Protocol):
    """The seam adapter suites implement to run the shared conformance corpus.

    Every method returns a normalized envelope:

    - ``{"outcome": "ok", ...}`` with method-specific normalized payloads, or
    - ``{"outcome": "error", "error": {...}}`` from
      :func:`tests.conformance.normalize.normalize_error`.

    ``execute`` accepts an optional ``plan_payload`` — the transport-neutral
    ``OrganizationPlan.to_dict()`` form returned by ``preview`` — so the
    reviewed-plan handoff crosses every surface as serialized data.
    """

    name: str

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the normalized canonical scan for *request*."""
        ...

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the normalized plan, result, and serialized plan payload."""
        ...

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Apply a reviewed plan (or build one) and return normalized outcomes."""
        ...


class _OracleOrganizer(FileOrganizer):
    """Canonical organizer with the deterministic extractor seams installed."""

    def _init_text_processor(self) -> None:
        """Leave the text model uninitialized; extension fallback is canonical."""
        self.text_processor = None

    def _init_vision_processor(self) -> None:
        """Leave the vision model uninitialized; extension fallback is canonical."""
        self.vision_processor = None

    def _process_audio_files(self, files: list[Path]) -> list[Any]:
        """Route audio through canonical policy fed by pinned metadata."""
        return dispatcher.process_audio_files(
            files,
            extractor_cls=DeterministicAudioExtractor,
            transcriber=None,
            max_transcribe_seconds=self.max_transcribe_seconds,
        )

    def _process_video_files(self, files: list[Path]) -> list[Any]:
        """Route video through canonical policy fed by pinned metadata."""
        return dispatcher.process_video_files(files, extractor_cls=DeterministicVideoExtractor)


class DirectServiceDriver:
    """Reference driver: the canonical application service itself.

    *workspace* holds the isolated per-execution history databases; use a
    fresh temporary directory per test so audit state can never leak between
    scenarios or into user data.
    """

    name = "direct-service"

    def __init__(self, workspace: Path) -> None:
        """Create a driver whose audit databases live under *workspace*."""
        self._workspace = workspace
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._executions = 0
        self._last_history: OperationHistory | None = None
        self._service = OrganizationService(
            text_model_config=CONFORMANCE_TEXT_MODEL,
            vision_model_config=CONFORMANCE_VISION_MODEL,
            organizer_factory=self._create_organizer,
        )

    def _create_organizer(self, **kwargs: Any) -> FileOrganizer:
        organizer = _OracleOrganizer(**kwargs)
        if not organizer.dry_run:
            self._executions += 1
            self._last_history = OperationHistory(
                db_path=self._workspace / f"audit-{self._executions}.db"
            )
            organizer._undo_manager = UndoManager(history=self._last_history)
        return organizer

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the normalized canonical scan for *request*."""
        roots = (request.input_path, request.output_path)
        try:
            scan = self._service.scan(request)
        except (ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        return {"outcome": "ok", "scan": normalize_scan(scan, *roots)}

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the normalized plan, result, and serialized plan payload."""
        roots = (request.input_path, request.output_path)
        try:
            result = self._service.preview(request)
        except (ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        if not isinstance(result.plan, OrganizationPlan):
            raise AssertionError("Canonical preview must produce an executable plan.")
        return {
            "outcome": "ok",
            "plan": normalize_plan(result.plan, *roots),
            "result": normalize_result(result, *roots),
            "plan_payload": result.plan.to_dict(),
        }

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Apply a reviewed plan (or build one) and return normalized outcomes."""
        roots = (request.input_path, request.output_path)
        try:
            plan = OrganizationPlan.from_dict(plan_payload) if plan_payload is not None else None
            result = self._service.execute(request, plan)
        except (ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        if not isinstance(result.plan, OrganizationPlan):
            raise AssertionError("Canonical execution must retain its executable plan.")
        assert self._last_history is not None  # execute always builds a non-dry organizer
        recorded_operations = self._last_history.get_operations()
        # OperationHistory is a newest-first query API. Conformance exposes
        # audit events in their stable insertion/execution order instead.
        recorded_operations.sort(
            key=lambda operation: operation.id if operation.id is not None else -1
        )
        events = normalize_audit_events(recorded_operations, *roots)
        return {
            "outcome": "ok",
            "plan": normalize_plan(result.plan, *roots),
            "result": normalize_result(result, *roots),
            "audit_events": events,
        }
