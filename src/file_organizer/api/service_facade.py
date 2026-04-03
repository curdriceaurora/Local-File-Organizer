"""ServiceFacade: unified entry point for desktop shell integration.

Provides a clean, importable interface for the Tauri desktop shell to interact
with the Python backend without starting the FastAPI server.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from loguru import logger

from file_organizer.api.config import ApiSettings
from file_organizer.api.routers.config import ConfigResponse
from file_organizer.config.provider_env import get_current_provider
from file_organizer.version import __version__


class ServiceFacade:
    """Unified facade over the file-organizer backend services.

    Designed to be imported and used without starting the HTTP server.
    All methods are async to allow callers (e.g. Tauri IPC bridges) to
    await results without blocking the event loop.

    Example usage::

        facade = ServiceFacade()
        health = await facade.health_check()
        config = await facade.get_config()
        result = await facade.organize_files("/home/user/Downloads")
    """

    def __init__(self, settings: ApiSettings | None = None) -> None:
        """Initialise the facade with optional API settings.

        Args:
            settings: Optional :class:`~file_organizer.api.config.ApiSettings`
                instance.  When *None* the default settings are used.
        """
        if settings is None:
            settings = ApiSettings()
        self._settings: ApiSettings = settings
        self._daemon_service: Any = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Return a health-check payload for the desktop shell.

        The response always contains:

        * ``status`` -- ``"ok"`` when the configured provider is reachable.
          For ``"ollama"`` provider: ``"ok"`` when Ollama is reachable,
          ``"degraded"`` when Ollama is unreachable.
          For ``"openai"``, ``"llama_cpp"``, or ``"mlx"`` provider:
          ``"unknown"`` — no connectivity probe is performed against provider
          endpoints at health-check time; the first model call will surface any
          auth or network errors.
        * ``version`` -- the package version string.
        * ``provider`` -- the active provider (``"ollama"``, ``"openai"``, ``"llama_cpp"``, or ``"mlx"``).
        * ``ollama`` -- ``True`` when the Ollama service is reachable.
        * ``capabilities`` -- present only when ``provider`` is ``"ollama"``
          and ``status`` is ``"degraded"``.  Describes which file types fall
          back to rule-based organisation when Ollama is unreachable.

        Returns:
            A dictionary with keys ``status``, ``version``, ``provider``,
            ``ollama``, and optionally ``capabilities``.
        """
        provider = get_current_provider()
        # Skip the Ollama probe entirely when using providers that do not require
        # the Ollama daemon for inference.
        # it adds a 2-second timeout for no benefit and can cause spurious failures.
        provider_not_probed = provider in {"openai", "llama_cpp", "mlx"}
        ollama_ok = False if provider_not_probed else await self._check_ollama()
        if provider_not_probed:
            status = "unknown"  # Provider endpoint is not probed at health-check time
        else:
            status = "ok" if ollama_ok else "degraded"
        payload: dict[str, Any] = {
            "status": status,
            "version": __version__,
            "provider": provider,
            "ollama": ollama_ok,
        }
        if provider == "ollama" and not ollama_ok:
            payload["capabilities"] = {
                "full_ai": [],
                "rule_based": ["audio", "video", "deduplication"],
                "extension_fallback": ["text", "images", "cad"],
                "note": (
                    "Ollama is unreachable. Audio/video use metadata-based organization. "
                    "Text/CAD files are sorted by file extension into named folders. "
                    "Images are placed into Images/<year> based on file modification time. "
                    "Start Ollama to enable full AI-powered organization."
                ),
            }
        return payload

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Return runtime status information.

        Returns a dict containing:

        * ``environment`` -- the configured environment name.
        * ``version`` -- the package version string.
        * ``auth_enabled`` -- whether authentication is active.
        * ``ollama`` -- Ollama reachability flag.

        Returns:
            A dictionary with current service status information.
        """
        ollama_ok = await self._check_ollama()
        settings = self._settings
        return {
            "environment": settings.environment,
            "version": __version__,
            "auth_enabled": settings.auth_enabled,
            "ollama": ollama_ok,
        }

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    async def get_config(self) -> dict[str, Any]:
        """Return the current application configuration.

        Reads from the in-memory config store used by the REST endpoints so
        that the desktop shell always sees the same values as the API.

        Returns:
            A dictionary representation of
            :class:`~file_organizer.api.routers.config.ConfigResponse`.
        """
        # Import here to avoid circular dependencies at module level
        from file_organizer.api.routers import config as _config_router

        cfg: ConfigResponse = _config_router._config
        return cfg.model_dump()

    # ------------------------------------------------------------------
    # organize_files
    # ------------------------------------------------------------------

    async def organize_files(
        self,
        source_dir: str,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Organize files in *source_dir* using the core FileOrganizer.

        This is a thin async wrapper around
        :class:`~file_organizer.core.organizer.FileOrganizer`.  Business
        logic lives entirely in that class; this method only handles the
        IPC envelope.

        Args:
            source_dir: Absolute path to the directory whose files should
                be organized.
            output_dir: Optional destination directory.  When *None* the
                source directory is used as the output (in-place
                organization).
            dry_run: When ``True`` no files are moved; a simulation report
                is returned instead.

        Returns:
            ``{"success": True, "data": {...}}`` on success, or
            ``{"success": False, "error": "<message>"}`` on failure.
            The ``data`` payload mirrors
            :class:`~file_organizer.core.organizer.OrganizationResult` field
            names.
        """
        try:
            from file_organizer.core.organizer import FileOrganizer

            def _blocking_organize() -> dict[str, Any]:
                organizer = FileOrganizer(dry_run=dry_run)
                dest = output_dir if output_dir is not None else source_dir
                result = organizer.organize(
                    input_path=source_dir,
                    output_path=dest,
                )
                return {
                    "total_files": result.total_files,
                    "processed_files": result.processed_files,
                    "skipped_files": result.skipped_files,
                    "failed_files": result.failed_files,
                    "deduplicated_files": result.deduplicated_files,
                    "processing_time": result.processing_time,
                    "organized_structure": result.organized_structure,
                    "errors": result.errors,
                    "dry_run": dry_run,
                }

            data = await asyncio.to_thread(_blocking_organize)
            return {"success": True, "data": data}
        except Exception as exc:
            logger.error("organize_files failed: {}", exc)
            return {"success": False, "error": "Internal server error during file organization"}

    # ------------------------------------------------------------------
    # Daemon management
    # ------------------------------------------------------------------

    def _get_daemon_service(self) -> Any:
        """Return the cached DaemonService instance, creating it on first use.

        Lazy-initialises a single :class:`~file_organizer.daemon.service.DaemonService`
        so that all daemon methods (start, stop, status) operate on the
        same instance.  This ensures that a daemon started via
        :meth:`start_daemon` can later be queried or stopped.

        Returns:
            The shared :class:`DaemonService` instance.
        """
        if self._daemon_service is None:
            from file_organizer.daemon.config import DaemonConfig
            from file_organizer.daemon.service import DaemonService

            config = DaemonConfig()
            self._daemon_service = DaemonService(config)
        return self._daemon_service

    async def get_daemon_status(self) -> dict[str, Any]:
        """Return the current status of the background daemon service.

        Queries the shared
        :class:`~file_organizer.daemon.service.DaemonService` instance to
        read its current state.  Reports the daemon's running flag, uptime,
        and file-processing count.

        Returns:
            ``{"success": True, "data": {"running": bool, "uptime_seconds":
            float, "files_processed": int}}`` on success, or
            ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            daemon = self._get_daemon_service()

            def _blocking_status() -> dict[str, Any]:
                return {
                    "running": daemon.is_running,
                    "uptime_seconds": daemon.uptime_seconds,
                    "files_processed": daemon.files_processed,
                }

            data = await asyncio.to_thread(_blocking_status)
            return {"success": True, "data": data}
        except Exception as exc:
            logger.error("get_daemon_status failed: {}", exc)
            return {"success": False, "error": "Internal server error while querying daemon status"}

    async def start_daemon(self) -> dict[str, Any]:
        """Start the background daemon service.

        Launches the :class:`~file_organizer.daemon.service.DaemonService`
        in a background thread so the call returns immediately.

        Returns:
            ``{"success": True, "data": {"started": True}}`` when the daemon
            starts successfully, or ``{"success": False, "error": "<message>"}``
            on failure.
        """
        try:
            daemon = self._get_daemon_service()

            def _blocking_start() -> None:
                daemon.start_background()

            await asyncio.to_thread(_blocking_start)
            return {"success": True, "data": {"started": True}}
        except Exception as exc:
            logger.error("start_daemon failed: {}", exc)
            return {"success": False, "error": "Internal server error while starting daemon"}

    async def stop_daemon(self) -> dict[str, Any]:
        """Stop the background daemon service.

        Signals the running :class:`~file_organizer.daemon.service.DaemonService`
        to stop and waits briefly for it to terminate.

        Returns:
            ``{"success": True, "data": {"stopped": True}}`` when the daemon
            stops, or ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            daemon = self._get_daemon_service()

            def _blocking_stop() -> None:
                daemon.stop()

            await asyncio.to_thread(_blocking_stop)
            return {"success": True, "data": {"stopped": True}}
        except Exception as exc:
            logger.error("stop_daemon failed: {}", exc)
            return {"success": False, "error": "Internal server error while stopping daemon"}

    # ------------------------------------------------------------------
    # Model status
    # ------------------------------------------------------------------

    async def get_model_status(self) -> dict[str, Any]:
        """Return the status of all configured AI models.

        Queries :class:`~file_organizer.models.model_manager.ModelManager`
        for the list of known models and their installation status.

        Returns:
            ``{"success": True, "data": {"models": [...]}}`` where each
            entry contains ``name``, ``model_type``, ``size``,
            ``quantization``, ``description`` and ``installed`` fields.
            Returns ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            from file_organizer.models.model_manager import ModelManager

            def _blocking_models() -> list[dict[str, Any]]:
                manager = ModelManager()
                models = manager.list_models()
                return [
                    {
                        "name": m.name,
                        "model_type": m.model_type,
                        "size": m.size,
                        "quantization": m.quantization,
                        "description": m.description,
                        "installed": m.installed,
                    }
                    for m in models
                ]

            model_list = await asyncio.to_thread(_blocking_models)
            return {"success": True, "data": {"models": model_list}}
        except Exception as exc:
            logger.error("get_model_status failed: {}", exc)
            return {"success": False, "error": "Internal server error while querying model status"}

    # ------------------------------------------------------------------
    # Smart suggestions
    # ------------------------------------------------------------------

    async def get_suggestions(self, path: str) -> dict[str, Any]:
        """Return organization suggestions for a given directory path.

        Wraps :class:`~file_organizer.services.smart_suggestions.SuggestionEngine`
        to analyse the files at *path* and produce ranked placement
        suggestions.

        Args:
            path: Absolute path to a directory whose files should be
                analysed. Must be pre-validated by the API layer.

        Returns:
            ``{"success": True, "data": {"suggestions": [...]}}`` where each
            entry contains the suggestion details, or
            ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            from file_organizer.services.smart_suggestions import SuggestionEngine

            def _blocking_suggestions() -> list[dict[str, Any]]:
                engine = SuggestionEngine()
                # Path must be pre-validated at API boundary
                target = Path(path)
                files = [p for p in target.rglob("*") if p.is_file()]
                suggestions = engine.generate_suggestions(files)
                return [
                    {
                        "suggestion_type": s.suggestion_type.value
                        if hasattr(s.suggestion_type, "value")
                        else str(s.suggestion_type),
                        "source_path": str(s.file_path),
                        "target_path": str(s.target_path)
                        if hasattr(s, "target_path") and s.target_path is not None
                        else None,
                        "confidence": s.confidence,
                        "reason": s.reasoning if hasattr(s, "reasoning") else "",
                    }
                    for s in suggestions
                ]

            suggestion_list = await asyncio.to_thread(_blocking_suggestions)
            return {"success": True, "data": {"suggestions": suggestion_list}}
        except Exception as exc:
            logger.error("get_suggestions failed: {}", exc)
            return {"success": False, "error": "Internal server error while generating suggestions"}

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    async def find_duplicates(self, scan_dir: str) -> dict[str, Any]:
        """Scan *scan_dir* for duplicate files and return a summary.

        Wraps
        :class:`~file_organizer.services.deduplication.detector.DuplicateDetector`.

        Args:
            scan_dir: Absolute path to the directory to scan.
                Must be pre-validated by the API layer.

        Returns:
            ``{"success": True, "data": {"statistics": {...}, "groups": [...]}}``
            on success, or ``{"success": False, "error": "<message>"}`` on
            failure.  ``statistics`` mirrors the output of
            :meth:`~file_organizer.services.deduplication.detector.DuplicateDetector.get_statistics`.
        """
        try:
            from file_organizer.services.deduplication.detector import (
                DuplicateDetector,
            )

            def _blocking_dedup() -> dict[str, Any]:
                detector = DuplicateDetector()
                # Path must be pre-validated at API boundary
                detector.scan_directory(Path(scan_dir))

                stats = detector.get_statistics()  # type: ignore[no-untyped-call]
                groups_raw = detector.get_duplicate_groups()  # type: ignore[no-untyped-call]

                # Serialise groups (dict of hash -> DuplicateGroup objects)
                groups: list[dict[str, Any]] = []
                for file_hash, group in groups_raw.items():
                    paths = [str(fm.path) for fm in group.files] if hasattr(group, "files") else []
                    groups.append(
                        {
                            "hash": file_hash,
                            "file_count": len(paths),
                            "files": paths,
                        }
                    )

                return {
                    "statistics": stats if isinstance(stats, dict) else vars(stats),
                    "groups": groups,
                }

            data = await asyncio.to_thread(_blocking_dedup)
            return {"success": True, "data": data}
        except Exception as exc:
            logger.error("find_duplicates failed: {}", exc)
            return {"success": False, "error": "Internal server error during duplicate detection"}

    # ------------------------------------------------------------------
    # Undo / history
    # ------------------------------------------------------------------

    async def undo_last_operation(self) -> dict[str, Any]:
        """Undo the most recently completed file operation.

        Wraps :class:`~file_organizer.undo.undo_manager.UndoManager`.

        Returns:
            ``{"success": True, "data": {"undone": True}}`` when the undo
            succeeds, ``{"success": True, "data": {"undone": False}}`` when
            there is nothing to undo, or
            ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            from file_organizer.undo.undo_manager import UndoManager

            def _blocking_undo() -> bool:
                manager = UndoManager()
                return manager.undo_last_operation()

            undone = await asyncio.to_thread(_blocking_undo)
            return {"success": True, "data": {"undone": undone}}
        except Exception as exc:
            logger.error("undo_last_operation failed: {}", exc)
            return {"success": False, "error": "Internal server error during undo operation"}

    async def get_operation_history(self, limit: int = 10) -> dict[str, Any]:
        """Return recent file operation history.

        Wraps :class:`~file_organizer.history.tracker.OperationHistory`.

        Args:
            limit: Maximum number of operations to return (default: 10).

        Returns:
            ``{"success": True, "data": {"operations": [...]}}`` where each
            entry is a serialised
            :class:`~file_organizer.history.tracker.Operation`, or
            ``{"success": False, "error": "<message>"}`` on failure.
        """
        try:
            from file_organizer.history.tracker import OperationHistory

            def _blocking_history() -> list[dict[str, Any]]:
                history = OperationHistory()
                ops = history.get_recent_operations(limit=limit)

                serialised = []
                for op in ops:
                    serialised.append(
                        {
                            "id": op.id,
                            "operation_type": op.operation_type.value
                            if hasattr(op.operation_type, "value")
                            else str(op.operation_type),
                            "source_path": str(op.source_path),
                            "destination_path": str(op.destination_path)
                            if op.destination_path is not None
                            else None,
                            "status": op.status.value
                            if hasattr(op.status, "value")
                            else str(op.status),
                            "timestamp": op.timestamp.isoformat()
                            if hasattr(op.timestamp, "isoformat")
                            else str(op.timestamp),
                        }
                    )
                return serialised

            operations = await asyncio.to_thread(_blocking_history)
            return {"success": True, "data": {"operations": operations}}
        except Exception as exc:
            logger.error("get_operation_history failed: {}", exc)
            return {
                "success": False,
                "error": "Internal server error while retrieving operation history",
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_ollama(self) -> bool:
        """Probe the Ollama service and return ``True`` if it responds.

        Makes a lightweight HTTP request to the configured Ollama endpoint.
        The URL is read from :attr:`ApiSettings.ollama_url` which defaults to
        ``http://localhost:11434`` and can be overridden via the ``OLLAMA_HOST``
        or ``FO_OLLAMA_URL`` environment variables.

        Returns ``False`` on any network or HTTP error so the facade never
        raises from a health-check call.

        Returns:
            ``True`` when Ollama is reachable, ``False`` otherwise.
        """
        settings = self._settings
        url = settings.ollama_url

        def _blocking_check() -> bool:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    return bool(response.status == 200)
            except Exception as exc:
                logger.debug("Ollama not reachable at {}: {}", url, exc)
                return False

        return await asyncio.to_thread(_blocking_check)
