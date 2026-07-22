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

import asyncio
import json
import re
from contextlib import redirect_stdout
from datetime import UTC, datetime
from html import unescape
from io import StringIO
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_config_manager,
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.organize import get_organization_service
from file_organizer.api.routers.organize import router as api_organize_router
from file_organizer.cli.api import api_app
from file_organizer.cli.main import app
from file_organizer.client.async_client import AsyncFileOrganizerClient
from file_organizer.client.exceptions import ClientError
from file_organizer.client.models import (
    OrganizationOptionsPayload as ClientOrganizationOptions,
)
from file_organizer.client.models import OrganizationPlanPayload as ClientOrganizationPlan
from file_organizer.client.sync_client import FileOrganizerClient
from file_organizer.config.schema import AppConfig
from file_organizer.core import dispatcher
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationScan, OrganizationService
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult
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
from file_organizer.tui.organization_adapter import TUIOrganizationAdapter
from file_organizer.tui.workspace import TUIWorkspace
from file_organizer.undo import UndoManager
from file_organizer.utils.atomic_write import atomic_write_text
from file_organizer.web.organize_routes import (
    get_web_organization_service,
)
from file_organizer.web.organize_routes import (
    organize_router as web_organize_router,
)
from file_organizer.web.organize_services import (
    _delete_organize_plan,
    _get_organize_plan,
    parse_organize_options,
)
from tests.conformance.normalize import (
    normalize_audit_events,
    normalize_error,
    normalize_path,
    normalize_plan,
    normalize_result,
    normalize_scan,
    redact_roots,
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
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        return {"outcome": "ok", "scan": normalize_scan(scan, *roots)}

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the normalized plan, result, and serialized plan payload."""
        roots = (request.input_path, request.output_path)
        try:
            result = self._service.preview(request)
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
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
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
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


class TUIConformanceDriver:
    """Drive the production TUI state adapter against the golden corpus."""

    name = "tui-workspace-adapter"

    def __init__(self, workspace: Path) -> None:
        self._workspace_root = workspace
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        self._oracle = DirectServiceDriver(workspace / "service")
        self._state = TUIWorkspace()
        self._adapter = TUIOrganizationAdapter(self._state, self._oracle._service)

    def _map(self, request: OrganizeRequest) -> None:
        """Round-trip every canonical option through shared TUI session state."""
        self._state.set_roots(request.input_path, request.output_path)
        self._state.set_options(**request.options.to_dict())
        self._state.set_selected_files(set())

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the canonical scan reached from TUI workspace state."""
        self._map(request)
        roots = (request.input_path, request.output_path)
        try:
            scan = self._adapter.scan()
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        return {"outcome": "ok", "scan": normalize_scan(scan, *roots)}

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        """Preview and retain the exact plan represented by TUI state."""
        self._map(request)
        roots = (request.input_path, request.output_path)
        try:
            result = self._adapter.preview()
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        plan = self._state.reviewed_plan
        if plan is None:
            raise AssertionError("TUI preview must retain an executable plan.")
        return {
            "outcome": "ok",
            "plan": normalize_plan(plan, *roots),
            "result": normalize_result(result, *roots),
            "plan_payload": plan.to_dict(),
        }

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Apply the reviewed serialized plan through the TUI adapter."""
        self._map(request)
        roots = (request.input_path, request.output_path)
        try:
            plan = OrganizationPlan.from_dict(plan_payload) if plan_payload is not None else None
            if plan is None:
                self._adapter.preview()
                plan = self._state.reviewed_plan
            result = self._adapter.execute(plan)
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        if not isinstance(result.plan, OrganizationPlan):
            raise AssertionError("TUI execution must retain its executable plan.")
        history = self._oracle._last_history
        assert history is not None
        operations = history.get_operations()
        operations.sort(key=lambda operation: operation.id if operation.id is not None else -1)
        return {
            "outcome": "ok",
            "plan": normalize_plan(result.plan, *roots),
            "result": normalize_result(result, *roots),
            "audit_events": normalize_audit_events(operations, *roots),
        }


class WebFormConformanceDriver:
    """Drive the real Web form routes against the canonical service seam.

    Desktop loads these same ``/ui`` workflows, so its route behavior is
    equivalent by construction rather than independently corpus-driven. Its
    Python bridge adds native path selection and reveal affordances covered by
    focused Desktop tests.
    """

    name = "web-form-adapter"
    _PLAN_ID_PATTERN = re.compile(r'data-plan-id="([^"]+)"')
    _ERROR_PATTERN = re.compile(r'data-error-payload="([^"]+)"')

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._oracle = DirectServiceDriver(workspace / "service")
        settings = ApiSettings(
            allowed_paths=[str(workspace.parent)],
            auth_enabled=False,
            auth_db_path=str(workspace / "auth.db"),
        )
        manager = type(
            "ConformanceConfigManager",
            (),
            {"load": staticmethod(AppConfig)},
        )()
        self._app = FastAPI()
        self._app.dependency_overrides[get_settings] = lambda: settings
        self._app.dependency_overrides[get_config_manager] = lambda: manager
        self._app.dependency_overrides[get_web_organization_service] = lambda: self._oracle._service
        setup_exception_handlers(self._app)
        self._app.include_router(web_organize_router, prefix="/ui")
        self._client = TestClient(self._app, raise_server_exceptions=False)

    @staticmethod
    def _mapped_request(request: OrganizeRequest) -> OrganizeRequest:
        """Map Web-form strings back onto the canonical request contract."""
        mapped = parse_organize_options(
            **WebFormConformanceDriver._option_form_fields(request.options)
        )
        return OrganizeRequest(request.input_path, request.output_path, mapped)

    @staticmethod
    def _option_form_fields(options: OrganizeOptions) -> dict[str, str]:
        """Serialize every canonical option through the Web form contract."""
        return {
            "methodology": options.effective_methodology.value,
            "recursive": "1" if options.recursive else "0",
            "include_hidden": "1" if options.include_hidden else "0",
            "skip_existing": "1" if options.skip_existing else "0",
            "transfer_mode": options.effective_transfer_mode.value,
            "use_hardlinks": "1" if options.use_hardlinks else "0",
            "enable_vision": "1" if options.enable_vision else "0",
            "transcribe_audio": "1" if options.transcribe_audio else "0",
            "max_transcribe_seconds": (
                ""
                if options.max_transcribe_seconds is None
                else str(options.max_transcribe_seconds)
            ),
            "whisper_model": options.whisper_model,
            "parallel_workers": (
                "" if options.parallel_workers is None else str(options.parallel_workers)
            ),
            "prefetch_depth": str(options.prefetch_depth),
            "text_model": options.text_model or "",
            "vision_model": options.vision_model or "",
            "text_provider": options.text_provider or "",
            "vision_provider": options.vision_provider or "",
        }

    @staticmethod
    def _form_data(request: OrganizeRequest) -> dict[str, str]:
        """Add request paths to the shared canonical option serialization."""
        return {
            "input_dir": str(request.input_path),
            "output_dir": str(request.output_path),
            **WebFormConformanceDriver._option_form_fields(request.options),
        }

    def _post_scan(
        self, request: OrganizeRequest
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        response = self._client.post("/ui/organize/scan", data=self._form_data(request))
        if response.status_code != 200:
            raise AssertionError(f"Web scan returned HTTP {response.status_code}.")
        error_match = self._ERROR_PATTERN.search(response.text)
        if error_match is not None:
            payload = json.loads(unescape(error_match.group(1)))
            payload.setdefault("details", {})
            return None, payload
        plan_match = self._PLAN_ID_PATTERN.search(response.text)
        if plan_match is None:
            raise AssertionError("Web scan response did not expose a plan or typed error.")
        stored = _get_organize_plan(plan_match.group(1))
        if stored is None:
            raise AssertionError("Web scan response referenced an unavailable plan.")
        return stored, None

    @staticmethod
    def _normalize_web_error(payload: dict[str, Any], roots: tuple[Path, Path]) -> dict[str, Any]:
        try:
            error = DomainError.from_dict(payload)
        except (KeyError, ValueError):
            return {
                "code": str(payload.get("code", "execution_failed")),
                "message": redact_roots(str(payload.get("message", "Request failed.")), *roots),
                "retryable": bool(payload.get("retryable", False)),
                "details": dict(payload.get("details", {})),
            }
        return normalize_error(error, *roots)

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        """Return the scan persisted by the real Web form route."""
        roots = (request.input_path, request.output_path)
        stored: dict[str, Any] | None = None
        try:
            stored, error = self._post_scan(request)
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        if error is not None:
            return {"outcome": "error", "error": self._normalize_web_error(error, roots)}
        if stored is None:
            raise AssertionError("Successful Web scan must persist a reviewed plan.")
        try:
            scan = OrganizationScan(
                Path(stored["input_dir"]),
                tuple(Path(path) for path in stored["scan_files"]),
                dict(stored["scan_counts"]),
            )
            return {"outcome": "ok", "scan": normalize_scan(scan, *roots)}
        finally:
            _delete_organize_plan(stored["plan_id"])

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        """Round-trip the plan through dashboard, scan, and clear routes."""
        roots = (request.input_path, request.output_path)
        stored: dict[str, Any] | None = None
        try:
            dashboard = self._client.get("/ui/organize")
            if dashboard.status_code != 200:
                raise AssertionError(f"Web dashboard returned HTTP {dashboard.status_code}.")
            stored, error = self._post_scan(request)
            if error is not None:
                return {"outcome": "error", "error": self._normalize_web_error(error, roots)}
            if stored is None:
                raise AssertionError("Successful Web preview must persist a reviewed plan.")
            plan = OrganizationPlan.from_dict(stored["executable_plan"])
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        finally:
            if stored is not None:
                clear = self._client.post(
                    "/ui/organize/plan/clear", data={"plan_id": stored["plan_id"]}
                )
                if clear.status_code != 200 or _get_organize_plan(stored["plan_id"]) is not None:
                    raise AssertionError("Web clear-plan route did not remove the reviewed plan.")
        result = OrganizationResult(
            total_files=plan.total_files,
            processed_files=plan.processed_files,
            skipped_files=plan.skipped_files,
            failed_files=plan.failed_files,
            deduplicated_files=plan.deduplicated_files,
            organized_structure=plan.organized_structure(),
            errors=plan.errors,
            plan=plan,
        )
        return {
            "outcome": "ok",
            "plan": normalize_plan(plan, *roots),
            "result": normalize_result(result, *roots),
            "plan_payload": plan.to_dict(),
        }

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute the reviewed serialized plan through the shared service."""
        mapped = self._mapped_request(request)
        roots = (mapped.input_path, mapped.output_path)
        try:
            plan = OrganizationPlan.from_dict(plan_payload) if plan_payload is not None else None
            result = self._oracle._service.execute(mapped, plan)
        except (DomainError, ValueError, RuntimeError, OSError) as exc:
            return {"outcome": "error", "error": normalize_error(exc, *roots)}
        if not isinstance(result.plan, OrganizationPlan):
            raise AssertionError("Web execution must retain its executable plan.")
        history = self._oracle._last_history
        assert history is not None
        operations = history.get_operations()
        operations.sort(key=lambda operation: operation.id if operation.id is not None else -1)
        return {
            "outcome": "ok",
            "plan": normalize_plan(result.plan, *roots),
            "result": normalize_result(result, *roots),
            "audit_events": normalize_audit_events(operations, *roots),
        }


class CLIConformanceDriver:
    """Drive the local CLI through JSON, with the direct service as its oracle seam."""

    name = "cli"

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._oracle = DirectServiceDriver(workspace / "service")
        self._invocations = 0

    @staticmethod
    def _option_args(request: OrganizeRequest) -> list[str]:
        options = request.options
        args = [
            "--recursive" if options.recursive else "--no-recursive",
            "--include-hidden" if options.include_hidden else "--exclude-hidden",
            "--skip-existing" if options.skip_existing else "--overwrite-existing",
            "--transfer-mode",
            options.effective_transfer_mode.value,
            "--methodology",
            options.effective_methodology.value,
            "--prefetch-depth",
            str(options.prefetch_depth),
            "--whisper-model",
            options.whisper_model,
            "--max-transcribe-seconds",
            str(options.max_transcribe_seconds or 0),
        ]
        if not options.enable_vision:
            args.append("--no-vision")
        if options.transcribe_audio:
            args.append("--transcribe-audio")
        if options.parallel_workers is not None:
            args.extend(("--max-workers", str(options.parallel_workers)))
        for flag, value in (
            ("--text-model", options.text_model),
            ("--vision-model", options.vision_model),
            ("--text-provider", options.text_provider),
            ("--vision-provider", options.vision_provider),
        ):
            if value is not None:
                args.extend((flag, value))
        return args

    def _invoke(self, args: list[str]) -> dict[str, Any]:
        self._invocations += 1
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch(
                "file_organizer.cli.organize._create_service",
                return_value=self._oracle._service,
            ),
        ):
            result = CliRunner().invoke(app, args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"CLI did not emit valid JSON (exit {result.exit_code}): {result.stdout}"
            ) from exc
        if result.exit_code == 0 and payload.get("outcome") != "ok":
            raise AssertionError(f"CLI succeeded with a non-success envelope: {payload}")
        return payload

    @staticmethod
    def _result(payload: dict[str, Any], plan: OrganizationPlan | None) -> OrganizationResult:
        return OrganizationResult(
            total_files=payload["total_files"],
            processed_files=payload["processed_files"],
            skipped_files=payload["skipped_files"],
            failed_files=payload["failed_files"],
            deduplicated_files=payload["deduplicated_files"],
            processing_time=payload["processing_time"],
            organized_structure=payload["organized_structure"],
            errors=[tuple(error) for error in payload["errors"]],
            plan=plan,
            transaction_id=payload["transaction_id"],
        )

    @staticmethod
    def _normalize_cli_error(
        payload: dict[str, Any], input_root: Path, output_root: Path
    ) -> dict[str, Any]:
        error = dict(payload["error"])
        if "code" in error:
            error.setdefault("details", {})
            return normalize_error(DomainError.from_dict(error), input_root, output_root)
        error["message"] = (
            error.get("message", "")
            .replace(str(input_root.resolve(strict=False)), "<input>")
            .replace(str(output_root.resolve(strict=False)), "<output>")
        )
        if "conflicts" in error:
            for conflict in error["conflicts"]:
                conflict["path"] = normalize_path(conflict["path"], input_root, output_root)
            error["conflicts"].sort(
                key=lambda conflict: (conflict["conflict_type"], conflict["path"])
            )
        return error

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        payload = self._invoke(
            [
                "preview",
                str(request.input_path),
                "--output-dir",
                str(request.output_path),
                "--json",
                *self._option_args(request),
            ]
        )
        if payload["outcome"] == "error":
            return {"outcome": "error", "error": self._normalize_cli_error(payload, *roots)}
        raw = payload["scan"]
        scan = OrganizationScan(
            Path(raw["input_path"]), tuple(Path(path) for path in raw["files"]), raw["counts"]
        )
        return {"outcome": "ok", "scan": normalize_scan(scan, *roots)}

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        payload = self._invoke(
            [
                "preview",
                str(request.input_path),
                "--output-dir",
                str(request.output_path),
                "--json",
                *self._option_args(request),
            ]
        )
        if payload["outcome"] == "error":
            return {"outcome": "error", "error": self._normalize_cli_error(payload, *roots)}
        plan = OrganizationPlan.from_dict(payload["plan"])
        result = self._result(payload["result"], plan)
        return {
            "outcome": "ok",
            "plan": normalize_plan(plan, *roots),
            "result": normalize_result(result, *roots),
            "plan_payload": payload["plan"],
        }

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        args = [
            "organize",
            str(request.input_path),
            str(request.output_path),
            "--json",
            *self._option_args(request),
        ]
        if plan_payload is not None:
            plan_path = self._workspace / f"plan-{self._invocations + 1}.json"
            atomic_write_text(plan_path, json.dumps(plan_payload))
            args.extend(("--plan", str(plan_path)))
        payload = self._invoke(args)
        if payload["outcome"] == "error":
            return {"outcome": "error", "error": self._normalize_cli_error(payload, *roots)}
        plan = OrganizationPlan.from_dict(payload["plan"])
        result = self._result(payload["result"], plan)
        history = self._oracle._last_history
        assert history is not None
        operations = history.get_operations()
        operations.sort(key=lambda operation: operation.id if operation.id is not None else -1)
        return {
            "outcome": "ok",
            "plan": normalize_plan(plan, *roots),
            "result": normalize_result(result, *roots),
            "audit_events": normalize_audit_events(operations, *roots),
        }


class _TransportFailure(Exception):
    """Carry a stable HTTP error payload across conformance driver helpers."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("message", payload)))


class _HTTPConformanceDriver:
    """Shared normalization and deterministic API setup for HTTP-backed drivers."""

    name = "http"

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._oracle = DirectServiceDriver(workspace / "service")
        settings = ApiSettings(
            environment="test",
            auth_enabled=False,
            allowed_paths=[str(workspace.parent)],
            auth_jwt_secret="conformance-secret",
            rate_limit_enabled=False,
        )
        self._app = FastAPI()
        setup_exception_handlers(self._app)
        self._app.dependency_overrides[get_settings] = lambda: settings
        self._app.dependency_overrides[get_current_active_user] = lambda: object()
        self._app.dependency_overrides[get_organization_service] = lambda: self._oracle._service
        self._app.include_router(api_organize_router, prefix="/api/v1")
        self._test_client = TestClient(self._app, raise_server_exceptions=False)

    @staticmethod
    def _request_payload(
        request: OrganizeRequest,
        *,
        plan_payload: dict[str, Any] | None = None,
        dry_run: bool,
    ) -> dict[str, Any]:
        return {
            "input_dir": str(request.input_path),
            "output_dir": str(request.output_path),
            "options": request.options.to_dict(),
            "plan": plan_payload,
            "dry_run": dry_run,
            "run_in_background": False,
        }

    @staticmethod
    def _response_payload(response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        if not response.is_success:
            raise _TransportFailure(payload)
        return payload

    @staticmethod
    def _sdk_failure(exc: ClientError) -> _TransportFailure:
        return _TransportFailure(
            {
                "error": exc.error_code,
                "message": exc.detail,
                "retryable": exc.retryable,
                "details": exc.details,
            }
        )

    @staticmethod
    def _normalize_failure(
        failure: _TransportFailure,
        input_root: Path,
        output_root: Path,
    ) -> dict[str, Any]:
        payload = failure.payload
        code = str(payload.get("code") or payload.get("error") or "")
        if code == "plan_validation_failed":
            details = payload.get("details") or {}
            return {
                "error_type": str(details.get("error_type", "PlanValidationError")),
                "message": redact_roots(str(payload.get("message", "")), input_root, output_root),
                "conflicts": sorted(
                    (
                        {
                            "conflict_type": str(conflict["conflict_type"]),
                            "path": normalize_path(conflict["path"], input_root, output_root),
                        }
                        for conflict in details.get("conflicts", [])
                    ),
                    key=lambda conflict: (conflict["conflict_type"], conflict["path"]),
                ),
            }
        try:
            error_code = DomainErrorCode(code)
        except ValueError:
            return {
                "error_type": code or "HTTPError",
                "message": redact_roots(str(payload.get("message", "")), input_root, output_root),
            }
        error = DomainError(
            error_code,
            str(payload.get("message", "Request failed.")),
            retryable=bool(payload.get("retryable", False)),
            details=dict(payload.get("details") or {}),
        )
        return normalize_error(error, input_root, output_root)

    @staticmethod
    def _scan_envelope(
        payload: dict[str, Any], input_root: Path, output_root: Path
    ) -> dict[str, Any]:
        scan = OrganizationScan(
            Path(payload["input_dir"]),
            tuple(Path(path) for path in payload["files"]),
            dict(payload["counts"]),
        )
        return {"outcome": "ok", "scan": normalize_scan(scan, input_root, output_root)}

    @staticmethod
    def _result_envelope(
        payload: dict[str, Any], input_root: Path, output_root: Path
    ) -> dict[str, Any]:
        plan_payload = payload.get("plan")
        if not isinstance(plan_payload, dict):
            raise AssertionError("Organization transport omitted its executable plan.")
        plan = OrganizationPlan.from_dict(plan_payload)
        result = OrganizationResult(
            total_files=payload["total_files"],
            processed_files=payload["processed_files"],
            skipped_files=payload["skipped_files"],
            failed_files=payload["failed_files"],
            deduplicated_files=payload["deduplicated_files"],
            processing_time=payload["processing_time"],
            organized_structure=payload["organized_structure"],
            errors=[(error["file"], error["error"]) for error in payload["errors"]],
            plan=plan,
            transaction_id=payload.get("transaction_id"),
        )
        return {
            "outcome": "ok",
            "plan": normalize_plan(plan, input_root, output_root),
            "result": normalize_result(result, input_root, output_root),
            "plan_payload": plan_payload,
        }

    def _audit_events(self, roots: tuple[Path, Path]) -> list[dict[str, Any]]:
        history = self._oracle._last_history
        assert history is not None
        operations = history.get_operations()
        operations.sort(key=lambda operation: operation.id if operation.id is not None else -1)
        return normalize_audit_events(operations, *roots)

    def _scan(self, request: OrganizeRequest) -> dict[str, Any]:
        raise NotImplementedError

    def _preview(self, request: OrganizeRequest) -> dict[str, Any]:
        raise NotImplementedError

    def _execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        raise NotImplementedError

    def scan(self, request: OrganizeRequest) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        try:
            payload = self._scan(request)
        except _TransportFailure as exc:
            return {"outcome": "error", "error": self._normalize_failure(exc, *roots)}
        return self._scan_envelope(payload, *roots)

    def preview(self, request: OrganizeRequest) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        try:
            payload = self._preview(request)
        except _TransportFailure as exc:
            return {"outcome": "error", "error": self._normalize_failure(exc, *roots)}
        return self._result_envelope(payload, *roots)

    def execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        roots = (request.input_path, request.output_path)
        try:
            payload = self._execute(request, plan_payload)
        except _TransportFailure as exc:
            return {"outcome": "error", "error": self._normalize_failure(exc, *roots)}
        envelope = self._result_envelope(payload, *roots)
        envelope.pop("plan_payload")
        envelope["audit_events"] = self._audit_events(roots)
        return envelope


class RESTConformanceDriver(_HTTPConformanceDriver):
    """Drive canonical organization behavior through the public REST routes."""

    name = "rest"

    def _scan(self, request: OrganizeRequest) -> dict[str, Any]:
        response = self._test_client.post(
            "/api/v1/organize/scan",
            json={
                "input_dir": str(request.input_path),
                "recursive": request.options.recursive,
                "include_hidden": request.options.include_hidden,
            },
        )
        return self._response_payload(response)

    def _preview(self, request: OrganizeRequest) -> dict[str, Any]:
        response = self._test_client.post(
            "/api/v1/organize/preview",
            json=self._request_payload(request, dry_run=True),
        )
        return self._response_payload(response)

    def _execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        response = self._test_client.post(
            "/api/v1/organize/execute",
            json=self._request_payload(request, plan_payload=plan_payload, dry_run=False),
        )
        outer = self._response_payload(response)
        result = outer.get("result")
        if not isinstance(result, dict):
            raise AssertionError(f"REST execution omitted its result: {outer}")
        return result


class PythonSDKConformanceDriver(_HTTPConformanceDriver):
    """Drive the shared corpus through the synchronous official Python SDK."""

    name = "python-sdk"

    def __init__(self, workspace: Path) -> None:
        super().__init__(workspace)
        self._sdk = FileOrganizerClient(base_url="http://testserver")
        self._sdk._client.close()
        self._sdk._client = self._test_client  # type: ignore[assignment]

    @staticmethod
    def _options(request: OrganizeRequest) -> ClientOrganizationOptions:
        return ClientOrganizationOptions.model_validate(request.options.to_dict())

    def _scan(self, request: OrganizeRequest) -> dict[str, Any]:
        try:
            response = self._sdk.scan(
                str(request.input_path),
                recursive=request.options.recursive,
                include_hidden=request.options.include_hidden,
            )
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        return response.model_dump(mode="json")

    def _preview(self, request: OrganizeRequest) -> dict[str, Any]:
        try:
            response = self._sdk.preview_organize(
                str(request.input_path),
                str(request.output_path),
                options=self._options(request),
            )
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        return response.model_dump(mode="json")

    def _execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        plan = (
            ClientOrganizationPlan.model_validate(plan_payload)
            if plan_payload is not None
            else None
        )
        try:
            response = self._sdk.organize(
                str(request.input_path),
                str(request.output_path),
                options=self._options(request),
                plan=plan,
                run_in_background=False,
            )
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        if response.result is None:
            raise AssertionError(f"Python SDK execution omitted its result: {response}")
        return response.result.model_dump(mode="json")


class _NonClosingSDKProxy:
    """Delegate SDK calls while leaving the shared test transport open."""

    def __init__(self, sdk: FileOrganizerClient) -> None:
        self._sdk = sdk

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._sdk, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            with redirect_stdout(StringIO()):
                return attribute(*args, **kwargs)

        return invoke

    def close(self) -> None:
        """Keep the conformance TestClient available for the next command."""


class RemoteCLIConformanceDriver(PythonSDKConformanceDriver):
    """Drive ``fo api`` through the official synchronous SDK and REST routes."""

    name = "fo-api"

    def _invoke(self, args: list[str]) -> dict[str, Any]:
        proxy = _NonClosingSDKProxy(self._sdk)
        with patch(
            "file_organizer.cli.api._build_client",
            return_value=(proxy, ClientError),
        ):
            result = CliRunner().invoke(api_app, args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"fo api did not emit valid JSON (exit {result.exit_code}): {result.stdout}"
            ) from exc
        if result.exit_code != 0:
            error = payload.get("error")
            raise _TransportFailure(error if isinstance(error, dict) else payload)
        if payload.get("outcome") != "ok":
            raise AssertionError(f"fo api succeeded with a non-success envelope: {payload}")
        return payload

    def _scan(self, request: OrganizeRequest) -> dict[str, Any]:
        outer = self._invoke(
            [
                "scan",
                str(request.input_path),
                "--json",
                "--recursive" if request.options.recursive else "--no-recursive",
                ("--include-hidden" if request.options.include_hidden else "--exclude-hidden"),
            ]
        )
        scan = dict(outer["scan"])
        scan["input_dir"] = scan.pop("input_path")
        return scan

    def _preview(self, request: OrganizeRequest) -> dict[str, Any]:
        outer = self._invoke(
            [
                "preview",
                str(request.input_path),
                str(request.output_path),
                "--json",
                *CLIConformanceDriver._option_args(request),
            ]
        )
        result = dict(outer["result"])
        result["plan"] = outer["plan"]
        return result

    def _execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        args = [
            "organize",
            str(request.input_path),
            str(request.output_path),
            "--foreground",
            "--json",
        ]
        if plan_payload is None:
            args.extend(CLIConformanceDriver._option_args(request))
        else:
            plan_path = self._workspace / "fo-api-plan.json"
            atomic_write_text(plan_path, json.dumps(plan_payload))
            args.extend(("--plan", str(plan_path)))
            args.extend(CLIConformanceDriver._option_args(request))
        outer = self._invoke(args)
        result = outer.get("result")
        if not isinstance(result, dict):
            raise AssertionError(f"fo api execution omitted its result: {outer}")
        result = dict(result)
        result["plan"] = outer["plan"]
        return result


class AsyncPythonSDKConformanceDriver(_HTTPConformanceDriver):
    """Drive the shared corpus through the asynchronous official Python SDK."""

    name = "python-async-sdk"

    async def _with_sdk(self, operation: Any) -> Any:
        transport = httpx.ASGITransport(app=self._app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            sdk = AsyncFileOrganizerClient(base_url="http://testserver")
            await sdk._client.aclose()
            sdk._client = http_client
            return await operation(sdk)

    @staticmethod
    def _options(request: OrganizeRequest) -> ClientOrganizationOptions:
        return ClientOrganizationOptions.model_validate(request.options.to_dict())

    def _scan(self, request: OrganizeRequest) -> dict[str, Any]:
        async def invoke(sdk: AsyncFileOrganizerClient) -> Any:
            return await sdk.scan(
                str(request.input_path),
                recursive=request.options.recursive,
                include_hidden=request.options.include_hidden,
            )

        try:
            response = asyncio.run(self._with_sdk(invoke))
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        return response.model_dump(mode="json")

    def _preview(self, request: OrganizeRequest) -> dict[str, Any]:
        async def invoke(sdk: AsyncFileOrganizerClient) -> Any:
            return await sdk.preview_organize(
                str(request.input_path),
                str(request.output_path),
                options=self._options(request),
            )

        try:
            response = asyncio.run(self._with_sdk(invoke))
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        return response.model_dump(mode="json")

    def _execute(
        self, request: OrganizeRequest, plan_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        plan = (
            ClientOrganizationPlan.model_validate(plan_payload)
            if plan_payload is not None
            else None
        )

        async def invoke(sdk: AsyncFileOrganizerClient) -> Any:
            return await sdk.organize(
                str(request.input_path),
                str(request.output_path),
                options=self._options(request),
                plan=plan,
                run_in_background=False,
            )

        try:
            response = asyncio.run(self._with_sdk(invoke))
        except ClientError as exc:
            raise self._sdk_failure(exc) from exc
        if response.result is None:
            raise AssertionError(f"Async Python SDK execution omitted its result: {response}")
        return response.result.model_dump(mode="json")
