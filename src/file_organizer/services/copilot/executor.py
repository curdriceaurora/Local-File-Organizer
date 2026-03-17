"""Command executor — delegates parsed intents to existing services.

This module bridges the copilot's intent model with the concrete service
layer (``FileOrganizer``, ``UndoManager``, ``SmartSuggestions``, etc.).
Each intent type maps to a handler method that invokes the appropriate
service and returns an ``ExecutionResult``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from file_organizer.services.copilot.models import (
    ExecutionResult,
    Intent,
    IntentType,
)

if TYPE_CHECKING:
    from file_organizer.interfaces.search import RetrieverProtocol


class CommandExecutor:
    """Execute copilot intents by delegating to the service layer.

    Args:
        working_directory: Default directory context for operations.
        retriever: Optional :class:`RetrieverProtocol` for semantic FIND
            intents.  When provided and initialised, ``_handle_find`` uses
            it for context gathering instead of the default filename scan.
    """

    def __init__(
        self,
        *,
        working_directory: str | None = None,
        retriever: RetrieverProtocol | None = None,
    ) -> None:
        """Initialize CommandExecutor."""
        self._working_dir = Path(working_directory) if working_directory else Path.cwd()
        self._retriever = retriever

    def execute(self, intent: Intent) -> ExecutionResult:
        """Dispatch an intent to the appropriate handler.

        Args:
            intent: Parsed intent with parameters.

        Returns:
            An ``ExecutionResult`` describing the outcome.
        """
        handlers = {
            IntentType.ORGANIZE: self._handle_organize,
            IntentType.MOVE: self._handle_move,
            IntentType.RENAME: self._handle_rename,
            IntentType.FIND: self._handle_find,
            IntentType.UNDO: self._handle_undo,
            IntentType.REDO: self._handle_redo,
            IntentType.PREVIEW: self._handle_preview,
            IntentType.SUGGEST: self._handle_suggest,
        }

        handler = handlers.get(intent.intent_type)
        if handler is None:
            return ExecutionResult(
                success=False,
                message=f"No handler for intent: {intent.intent_type.value}",
            )

        try:
            return handler(intent)
        except Exception as exc:
            logger.error("Executor error for {}: {}", intent.intent_type.value, exc)
            return ExecutionResult(
                success=False,
                message=f"Operation failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_organize(self, intent: Intent) -> ExecutionResult:
        """Organise files in a directory.

        Args:
            intent: Intent with optional ``source`` and ``destination`` parameters.

        Returns:
            Execution result.
        """
        params = intent.parameters
        source = self._resolve_path(params.get("source"))
        destination = params.get("destination")
        dry_run = params.get("dry_run", False)

        if not source.is_dir():
            return ExecutionResult(
                success=False,
                message=f"Directory not found: {source}",
            )

        try:
            from file_organizer.core.organizer import FileOrganizer

            dest_path = self._resolve_path(destination) if destination else source / "organized"
            organizer = FileOrganizer(dry_run=dry_run)
            result = organizer.organize(input_path=source, output_path=dest_path)

            verb = "Would organise" if dry_run else "Organised"
            return ExecutionResult(
                success=True,
                message=(
                    f"{verb} {result.processed_files} files from {source} "
                    f"into {dest_path} ({result.skipped_files} skipped, "
                    f"{result.failed_files} failed)."
                ),
                details={
                    "result": {
                        "processed": result.processed_files,
                        "skipped": result.skipped_files,
                        "failed": result.failed_files,
                    }
                },
            )
        except ImportError as exc:
            return ExecutionResult(
                success=False,
                message=f"Organiser not available: {exc}",
            )

    def _handle_move(self, intent: Intent) -> ExecutionResult:
        """Move a file to a new location.

        Args:
            intent: Intent with ``source`` and ``destination`` parameters.

        Returns:
            Execution result.
        """
        params = intent.parameters
        source = params.get("source")
        destination = params.get("destination")

        if not source or not destination:
            return ExecutionResult(
                success=False,
                message="Please specify both source and destination paths.",
            )

        src = self._resolve_path(source)
        dst = self._resolve_path(destination)

        if not src.exists():
            return ExecutionResult(success=False, message=f"Source not found: {src}")

        try:
            import shutil

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ExecutionResult(
                success=True,
                message=f"Moved {src.name} to {dst}",
                affected_files=[str(src), str(dst)],
            )
        except OSError as exc:
            return ExecutionResult(success=False, message=f"Move failed: {exc}")

    def _handle_rename(self, intent: Intent) -> ExecutionResult:
        """Rename a file.

        Args:
            intent: Intent with ``target`` and ``new_name`` parameters.

        Returns:
            Execution result.
        """
        params = intent.parameters
        target = params.get("target")
        new_name = params.get("new_name")

        if not target or not new_name:
            return ExecutionResult(
                success=False,
                message="Please specify the file to rename and the new name.",
            )

        src = self._resolve_path(target)
        if not src.exists():
            return ExecutionResult(success=False, message=f"File not found: {src}")

        dst = src.parent / new_name
        try:
            src.rename(dst)
            return ExecutionResult(
                success=True,
                message=f"Renamed {src.name} to {new_name}",
                affected_files=[str(src), str(dst)],
            )
        except OSError as exc:
            return ExecutionResult(success=False, message=f"Rename failed: {exc}")

    def _build_retriever_for_root(self, search_root: Path) -> RetrieverProtocol | None:
        """Auto-build a HybridRetriever indexed on *search_root* (lazy optional dep).

        Returns ``None`` when search dependencies are unavailable or the corpus
        is too small to index.

        Args:
            search_root: Directory to index.

        Returns:
            An initialised :class:`HybridRetriever`, or ``None`` on failure.
        """
        try:
            from file_organizer.services.search.hybrid_retriever import (
                HybridRetriever,
                read_text_safe,
            )
        except ImportError:
            return None  # search deps not installed

        retriever = HybridRetriever()
        docs: list[str] = []
        paths: list[Path] = []
        try:
            for entry in search_root.rglob("*"):
                if entry.is_symlink() or not entry.is_file():
                    continue
                text = read_text_safe(entry)
                docs.append(f"{entry.stem} {' '.join(entry.parts)} {text}".strip())
                paths.append(entry)
                if len(docs) >= 500:  # cap corpus for interactive use
                    break
        except PermissionError:
            pass
        if not docs:
            return None
        try:
            retriever.index(docs, paths)
        except ValueError:
            return None  # corpus too small — fall through to filename scan
        return retriever

    def _handle_find(self, intent: Intent) -> ExecutionResult:
        """Find files matching a query.

        When a :class:`RetrieverProtocol` instance was supplied at construction
        and is initialised, it is used for semantic context gathering.
        When no retriever was injected, a :class:`HybridRetriever` is
        auto-built from *search_root* if the optional search dependencies are
        available.  Results are scoped to *search_root* in both cases.
        Otherwise the default filename-scan fallback is used.

        Args:
            intent: Intent with ``query`` parameter.

        Returns:
            Execution result with matched files.
        """
        query = intent.parameters.get("query", "")
        search_paths = intent.parameters.get("paths", [str(self._working_dir)])

        if not query:
            return ExecutionResult(
                success=False,
                message="Please tell me what to search for.",
            )

        search_root = self._resolve_path(search_paths[0]) if search_paths else self._working_dir
        if not search_root.is_dir():
            search_root = self._working_dir

        # ------------------------------------------------------------------
        # Semantic path — use injected retriever or auto-build from search_root
        # ------------------------------------------------------------------
        retriever = self._retriever or self._build_retriever_for_root(search_root)

        if retriever is not None and retriever.is_initialized:
            try:
                results = retriever.retrieve(query, top_k=20)
                # Scope results to search_root only
                matches = [str(p) for p, _ in results if Path(p).is_relative_to(search_root)]
            except Exception as exc:
                logger.warning("Retriever failed in _handle_find, falling back: {}", exc)
                matches = []
            if matches:
                file_list = "\n".join(f"  - {m}" for m in matches[:10])
                extra = f"\n  ... and {len(matches) - 10} more" if len(matches) > 10 else ""
                return ExecutionResult(
                    success=True,
                    message=(
                        f"Found {len(matches)} file(s) matching '{query}' (semantic):"
                        f"\n{file_list}{extra}"
                    ),
                    affected_files=matches,
                )

        # ------------------------------------------------------------------
        # Default path — filename substring scan
        # ------------------------------------------------------------------
        query_lower = query.lower()
        matches = []
        try:
            for entry in search_root.rglob("*"):
                if entry.is_file() and query_lower in entry.name.lower():
                    matches.append(str(entry))
                    if len(matches) >= 20:
                        break
        except PermissionError:
            pass

        if matches:
            file_list = "\n".join(f"  - {m}" for m in matches[:10])
            extra = f"\n  ... and {len(matches) - 10} more" if len(matches) > 10 else ""
            return ExecutionResult(
                success=True,
                message=f"Found {len(matches)} file(s) matching '{query}':\n{file_list}{extra}",
                affected_files=matches,
            )
        return ExecutionResult(
            success=True,
            message=f"No files matching '{query}' found in {search_root}.",
        )

    def _handle_undo(self, intent: Intent) -> ExecutionResult:
        """Undo the last file operation.

        Args:
            intent: Undo intent.

        Returns:
            Execution result.
        """
        try:
            from file_organizer.history.tracker import OperationHistory
            from file_organizer.undo.undo_manager import UndoManager

            history = OperationHistory()
            try:
                manager = UndoManager(history=history)
                success = manager.undo_last_operation()
                if success:
                    return ExecutionResult(success=True, message="Last operation undone.")
                return ExecutionResult(success=False, message="Nothing to undo.")
            finally:
                history.close()
        except ImportError as exc:
            return ExecutionResult(success=False, message=f"Undo not available: {exc}")

    def _handle_redo(self, intent: Intent) -> ExecutionResult:
        """Redo the last undone operation.

        Args:
            intent: Redo intent.

        Returns:
            Execution result.
        """
        try:
            from file_organizer.history.tracker import OperationHistory
            from file_organizer.undo.undo_manager import UndoManager

            history = OperationHistory()
            try:
                manager = UndoManager(history=history)
                success = manager.redo_last_operation()
                if success:
                    return ExecutionResult(success=True, message="Operation redone.")
                return ExecutionResult(success=False, message="Nothing to redo.")
            finally:
                history.close()
        except ImportError as exc:
            return ExecutionResult(success=False, message=f"Redo not available: {exc}")

    def _handle_preview(self, intent: Intent) -> ExecutionResult:
        """Preview what an organisation pass would do (dry-run).

        Args:
            intent: Preview intent with optional ``source`` parameter.

        Returns:
            Execution result.
        """
        # Delegate to organize handler with dry_run forced on
        intent.parameters["dry_run"] = True
        return self._handle_organize(intent)

    def _handle_suggest(self, intent: Intent) -> ExecutionResult:
        """Suggest better locations for files.

        Args:
            intent: Suggest intent with optional paths.

        Returns:
            Execution result.
        """
        paths = intent.parameters.get("paths", [])
        if not paths:
            return ExecutionResult(
                success=False,
                message="Please specify a file or directory for suggestions.",
            )

        target = self._resolve_path(paths[0])
        if not target.exists():
            return ExecutionResult(success=False, message=f"Path not found: {target}")

        # Attempt to use SmartSuggestions if available
        try:
            from file_organizer.services import smart_suggestions as _ss  # noqa: F401

            return ExecutionResult(
                success=True,
                message=f"Suggestion engine available for {target.name}. "
                "Use 'organize --dry-run' to preview placement suggestions.",
            )
        except ImportError:
            return ExecutionResult(
                success=True,
                message=f"Suggestion engine not available. Try: file-organizer preview {target}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path_str: Any) -> Path:
        """Resolve a path string relative to the working directory.

        Args:
            path_str: Path string or None.

        Returns:
            Resolved ``Path`` object.
        """
        if path_str is None:
            return self._working_dir
        p = Path(os.path.expanduser(str(path_str)))
        if not p.is_absolute():
            p = self._working_dir / p
        return p.resolve()
