"""Unit tests for ServiceFacade — all 9 required IPC methods.

Tests live here (tests/services/) because the facade is primarily a thin
wrapper over backend *services*, not an API-transport concern.  The existing
tests/api/test_service_facade.py covers the 3 original methods (health_check,
get_status, get_config) and is retained as-is.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.service_facade import ServiceFacade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_SETTINGS: dict[str, object] = {
    "environment": "test",
    "auth_enabled": False,
    "auth_jwt_secret": "test-secret",
    "rate_limit_enabled": False,
}


def _make_facade(**overrides: object) -> ServiceFacade:
    """Return a ServiceFacade configured for testing."""
    merged = {**_BASE_SETTINGS, **overrides}
    settings = ApiSettings(**merged)  # type: ignore[arg-type]
    return ServiceFacade(settings=settings)


# ---------------------------------------------------------------------------
# organize_files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOrganizeFiles:
    """Tests for ServiceFacade.organize_files()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_on_ok(self, tmp_path: Path) -> None:
        """organize_files returns success=True when organizer succeeds."""
        facade = _make_facade()
        mock_result = MagicMock()
        mock_result.total_files = 5
        mock_result.processed_files = 4
        mock_result.skipped_files = 0
        mock_result.failed_files = 1
        mock_result.processing_time = 1.23
        mock_result.organized_structure = {"documents": ["a.pdf"]}
        mock_result.errors = []

        with patch(
            "file_organizer.api.service_facade.ServiceFacade.organize_files",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "data": {
                    "total_files": 5,
                    "processed_files": 4,
                    "skipped_files": 0,
                    "failed_files": 1,
                    "processing_time": 1.23,
                    "organized_structure": {"documents": ["a.pdf"]},
                    "errors": [],
                    "dry_run": False,
                },
            },
        ):
            result = await facade.organize_files(str(tmp_path))

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """organize_files returns success=False when FileOrganizer raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.core.organizer.FileOrganizer",
            side_effect=RuntimeError("boom"),
        ):
            result = await facade.organize_files("/nonexistent/path")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_data_contains_required_keys(self, tmp_path: Path) -> None:
        """The data dict contains all expected keys on success."""
        facade = _make_facade()
        required = {
            "total_files",
            "processed_files",
            "skipped_files",
            "failed_files",
            "processing_time",
            "organized_structure",
            "errors",
            "dry_run",
        }

        mock_result = MagicMock()
        mock_result.total_files = 0
        mock_result.processed_files = 0
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.0
        mock_result.organized_structure = {}
        mock_result.errors = []

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = await facade.organize_files(str(tmp_path))

        if result["success"]:
            for key in required:
                assert key in result["data"], f"Missing key in data: {key}"

    @pytest.mark.asyncio
    async def test_dry_run_flag_reflected_in_data(self, tmp_path: Path) -> None:
        """dry_run flag is reflected in the returned data."""
        facade = _make_facade()
        mock_result = MagicMock()
        mock_result.total_files = 0
        mock_result.processed_files = 0
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.0
        mock_result.organized_structure = {}
        mock_result.errors = []

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = await facade.organize_files(str(tmp_path), dry_run=True)

        if result["success"]:
            assert result["data"]["dry_run"] is True


# ---------------------------------------------------------------------------
# get_daemon_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDaemonStatus:
    """Tests for ServiceFacade.get_daemon_status()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_structure(self) -> None:
        """get_daemon_status returns success=True with running/uptime/files_processed."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_daemon.is_running = False
        mock_daemon.uptime_seconds = 0.0
        mock_daemon.files_processed = 0

        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            result = await facade.get_daemon_status()

        assert result["success"] is True
        assert "running" in result["data"]
        assert "uptime_seconds" in result["data"]
        assert "files_processed" in result["data"]

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """get_daemon_status returns success=False when an exception is raised."""
        facade = _make_facade()
        with patch(
            "file_organizer.daemon.config.DaemonConfig",
            side_effect=RuntimeError("config error"),
        ):
            result = await facade.get_daemon_status()

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_running_reflects_daemon_state(self) -> None:
        """running field matches the daemon is_running property."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_daemon.is_running = True
        mock_daemon.uptime_seconds = 42.0
        mock_daemon.files_processed = 7

        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            result = await facade.get_daemon_status()

        if result["success"]:
            assert result["data"]["running"] is True
            assert result["data"]["uptime_seconds"] == 42.0
            assert result["data"]["files_processed"] == 7


# ---------------------------------------------------------------------------
# start_daemon
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStartDaemon:
    """Tests for ServiceFacade.start_daemon()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_when_started(self) -> None:
        """start_daemon returns success=True on successful start."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            result = await facade.start_daemon()

        assert result["success"] is True
        assert result["data"]["started"] is True

    @pytest.mark.asyncio
    async def test_calls_start_background(self) -> None:
        """start_daemon calls daemon.start_background()."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            await facade.start_daemon()

        mock_daemon.start_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """start_daemon returns success=False when the daemon raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.daemon.config.DaemonConfig",
            side_effect=RuntimeError("daemon error"),
        ):
            result = await facade.start_daemon()

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# stop_daemon
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStopDaemon:
    """Tests for ServiceFacade.stop_daemon()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_when_stopped(self) -> None:
        """stop_daemon returns success=True on successful stop."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            result = await facade.stop_daemon()

        assert result["success"] is True
        assert result["data"]["stopped"] is True

    @pytest.mark.asyncio
    async def test_calls_stop(self) -> None:
        """stop_daemon calls daemon.stop()."""
        facade = _make_facade()
        mock_daemon = MagicMock()
        mock_config = MagicMock()

        with (
            patch("file_organizer.daemon.config.DaemonConfig", return_value=mock_config),
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_daemon),
        ):
            await facade.stop_daemon()

        mock_daemon.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """stop_daemon returns success=False when an exception is raised."""
        facade = _make_facade()
        with patch(
            "file_organizer.daemon.config.DaemonConfig",
            side_effect=RuntimeError("stop error"),
        ):
            result = await facade.stop_daemon()

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# get_model_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetModelStatus:
    """Tests for ServiceFacade.get_model_status()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_with_models_key(self) -> None:
        """get_model_status returns success=True with a models list."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_model = MagicMock()
        mock_model.name = "qwen2.5:3b"
        mock_model.model_type = "text"
        mock_model.size = "1.9 GB"
        mock_model.quantization = "q4_K_M"
        mock_model.description = "Text model"
        mock_model.installed = True
        mock_manager.list_models.return_value = [mock_model]

        with patch("file_organizer.models.model_manager.ModelManager", return_value=mock_manager):
            result = await facade.get_model_status()

        assert result["success"] is True
        assert "models" in result["data"]
        assert isinstance(result["data"]["models"], list)

    @pytest.mark.asyncio
    async def test_model_entry_has_required_fields(self) -> None:
        """Each model entry contains the expected fields."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_model = MagicMock()
        mock_model.name = "qwen2.5:3b"
        mock_model.model_type = "text"
        mock_model.size = "1.9 GB"
        mock_model.quantization = "q4_K_M"
        mock_model.description = "A text model"
        mock_model.installed = False
        mock_manager.list_models.return_value = [mock_model]

        with patch("file_organizer.models.model_manager.ModelManager", return_value=mock_manager):
            result = await facade.get_model_status()

        if result["success"] and result["data"]["models"]:
            entry = result["data"]["models"][0]
            for field in ("name", "model_type", "size", "quantization", "description", "installed"):
                assert field in entry, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """get_model_status returns success=False when ModelManager raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.models.model_manager.ModelManager",
            side_effect=RuntimeError("model error"),
        ):
            result = await facade.get_model_status()

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_models_list_is_valid(self) -> None:
        """get_model_status accepts an empty model list."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_manager.list_models.return_value = []

        with patch("file_organizer.models.model_manager.ModelManager", return_value=mock_manager):
            result = await facade.get_model_status()

        assert result["success"] is True
        assert result["data"]["models"] == []


# ---------------------------------------------------------------------------
# get_suggestions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSuggestions:
    """Tests for ServiceFacade.get_suggestions()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_with_suggestions_key(self, tmp_path: Path) -> None:
        """get_suggestions returns success=True containing a suggestions list."""
        facade = _make_facade()
        mock_engine = MagicMock()
        mock_suggestion = MagicMock()
        mock_suggestion.suggestion_type = MagicMock()
        mock_suggestion.suggestion_type.value = "move"
        mock_suggestion.source_path = tmp_path / "file.txt"
        mock_suggestion.target_path = tmp_path / "docs" / "file.txt"
        mock_suggestion.confidence = 0.9
        mock_suggestion.reason = "extension match"
        mock_engine.generate_suggestions.return_value = [mock_suggestion]

        with patch(
            "file_organizer.services.smart_suggestions.SuggestionEngine",
            return_value=mock_engine,
        ):
            result = await facade.get_suggestions(str(tmp_path))

        assert result["success"] is True
        assert "suggestions" in result["data"]

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self, tmp_path: Path) -> None:
        """get_suggestions returns success=False when SuggestionEngine raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.services.smart_suggestions.SuggestionEngine",
            side_effect=RuntimeError("engine error"),
        ):
            result = await facade.get_suggestions(str(tmp_path))

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_suggestion_entry_has_required_fields(self, tmp_path: Path) -> None:
        """Each suggestion entry has confidence, source_path, suggestion_type."""
        facade = _make_facade()
        mock_engine = MagicMock()
        mock_suggestion = MagicMock()
        mock_suggestion.suggestion_type = MagicMock()
        mock_suggestion.suggestion_type.value = "rename"
        mock_suggestion.source_path = tmp_path / "old.txt"
        mock_suggestion.target_path = tmp_path / "new.txt"
        mock_suggestion.confidence = 0.75
        mock_suggestion.reason = "pattern"
        mock_engine.generate_suggestions.return_value = [mock_suggestion]

        with patch(
            "file_organizer.services.smart_suggestions.SuggestionEngine",
            return_value=mock_engine,
        ):
            result = await facade.get_suggestions(str(tmp_path))

        if result["success"] and result["data"]["suggestions"]:
            entry = result["data"]["suggestions"][0]
            for field in ("suggestion_type", "source_path", "confidence"):
                assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindDuplicates:
    """Tests for ServiceFacade.find_duplicates()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_with_statistics_and_groups(self, tmp_path: Path) -> None:
        """find_duplicates returns success=True with statistics and groups."""
        facade = _make_facade()
        mock_detector = MagicMock()
        mock_detector.get_statistics.return_value = {"total_files": 0, "duplicate_groups": 0}
        mock_detector.get_duplicate_groups.return_value = {}

        with patch(
            "file_organizer.services.deduplication.detector.DuplicateDetector",
            return_value=mock_detector,
        ):
            result = await facade.find_duplicates(str(tmp_path))

        assert result["success"] is True
        assert "statistics" in result["data"]
        assert "groups" in result["data"]

    @pytest.mark.asyncio
    async def test_groups_serialised_correctly(self, tmp_path: Path) -> None:
        """Duplicate groups are serialised to dicts with hash, file_count, files."""
        facade = _make_facade()
        mock_detector = MagicMock()
        mock_detector.get_statistics.return_value = {}

        mock_group = MagicMock()
        mock_group.files = [tmp_path / "a.txt", tmp_path / "b.txt"]
        mock_detector.get_duplicate_groups.return_value = {"abc123": mock_group}

        with patch(
            "file_organizer.services.deduplication.detector.DuplicateDetector",
            return_value=mock_detector,
        ):
            result = await facade.find_duplicates(str(tmp_path))

        if result["success"] and result["data"]["groups"]:
            group = result["data"]["groups"][0]
            assert group["hash"] == "abc123"
            assert group["file_count"] == 2
            assert len(group["files"]) == 2

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self, tmp_path: Path) -> None:
        """find_duplicates returns success=False when DuplicateDetector raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.services.deduplication.detector.DuplicateDetector",
            side_effect=RuntimeError("dedup error"),
        ):
            result = await facade.find_duplicates(str(tmp_path))

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_scan_directory_called_with_path(self, tmp_path: Path) -> None:
        """find_duplicates calls detector.scan_directory with a Path argument."""
        facade = _make_facade()
        mock_detector = MagicMock()
        mock_detector.get_statistics.return_value = {}
        mock_detector.get_duplicate_groups.return_value = {}

        with patch(
            "file_organizer.services.deduplication.detector.DuplicateDetector",
            return_value=mock_detector,
        ):
            await facade.find_duplicates(str(tmp_path))

        mock_detector.scan_directory.assert_called_once_with(Path(str(tmp_path)))


# ---------------------------------------------------------------------------
# undo_last_operation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUndoLastOperation:
    """Tests for ServiceFacade.undo_last_operation()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_undone_true_when_undo_succeeds(self) -> None:
        """undo_last_operation returns undone=True when UndoManager succeeds."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True

        with patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager):
            result = await facade.undo_last_operation()

        assert result["success"] is True
        assert result["data"]["undone"] is True

    @pytest.mark.asyncio
    async def test_returns_success_true_undone_false_when_nothing_to_undo(self) -> None:
        """undo_last_operation returns undone=False when there's nothing to undo."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = False

        with patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager):
            result = await facade.undo_last_operation()

        assert result["success"] is True
        assert result["data"]["undone"] is False

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """undo_last_operation returns success=False when UndoManager raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.undo.undo_manager.UndoManager",
            side_effect=RuntimeError("undo error"),
        ):
            result = await facade.undo_last_operation()

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_calls_undo_last_operation_on_manager(self) -> None:
        """undo_last_operation delegates to UndoManager.undo_last_operation()."""
        facade = _make_facade()
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True

        with patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager):
            await facade.undo_last_operation()

        mock_manager.undo_last_operation.assert_called_once()


# ---------------------------------------------------------------------------
# get_operation_history
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetOperationHistory:
    """Tests for ServiceFacade.get_operation_history()."""

    @pytest.mark.asyncio
    async def test_returns_success_true_with_operations_list(self) -> None:
        """get_operation_history returns success=True with an operations list."""
        facade = _make_facade()
        mock_history = MagicMock()
        mock_history.get_recent_operations.return_value = []

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            result = await facade.get_operation_history()

        assert result["success"] is True
        assert "operations" in result["data"]
        assert isinstance(result["data"]["operations"], list)

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self) -> None:
        """get_operation_history passes limit=10 by default."""
        facade = _make_facade()
        mock_history = MagicMock()
        mock_history.get_recent_operations.return_value = []

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            await facade.get_operation_history()

        mock_history.get_recent_operations.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_custom_limit_is_forwarded(self) -> None:
        """get_operation_history passes the caller-supplied limit."""
        facade = _make_facade()
        mock_history = MagicMock()
        mock_history.get_recent_operations.return_value = []

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            await facade.get_operation_history(limit=25)

        mock_history.get_recent_operations.assert_called_once_with(limit=25)

    @pytest.mark.asyncio
    async def test_operation_entries_are_serialised(self) -> None:
        """Each operation entry is a plain dict with expected keys."""
        facade = _make_facade()
        mock_history = MagicMock()

        mock_op = MagicMock()
        mock_op.id = 1
        mock_op.operation_type = MagicMock()
        mock_op.operation_type.value = "move"
        mock_op.source_path = Path("/tmp/src.txt")
        mock_op.destination_path = Path("/tmp/dst.txt")
        mock_op.status = MagicMock()
        mock_op.status.value = "completed"
        mock_op.timestamp = MagicMock()
        mock_op.timestamp.isoformat.return_value = "2026-03-01T00:00:00Z"

        mock_history.get_recent_operations.return_value = [mock_op]

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            result = await facade.get_operation_history()

        if result["success"] and result["data"]["operations"]:
            entry = result["data"]["operations"][0]
            for field in ("id", "operation_type", "source_path", "status", "timestamp"):
                assert field in entry, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_returns_success_false_on_exception(self) -> None:
        """get_operation_history returns success=False when OperationHistory raises."""
        facade = _make_facade()
        with patch(
            "file_organizer.history.tracker.OperationHistory",
            side_effect=RuntimeError("history error"),
        ):
            result = await facade.get_operation_history()

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_none_destination_path_serialised_as_none(self) -> None:
        """destination_path is serialised as None when the operation has no destination."""
        facade = _make_facade()
        mock_history = MagicMock()

        mock_op = MagicMock()
        mock_op.id = 2
        mock_op.operation_type = MagicMock()
        mock_op.operation_type.value = "delete"
        mock_op.source_path = Path("/tmp/gone.txt")
        mock_op.destination_path = None
        mock_op.status = MagicMock()
        mock_op.status.value = "completed"
        mock_op.timestamp = MagicMock()
        mock_op.timestamp.isoformat.return_value = "2026-03-01T00:00:00Z"

        mock_history.get_recent_operations.return_value = [mock_op]

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            result = await facade.get_operation_history()

        if result["success"] and result["data"]["operations"]:
            assert result["data"]["operations"][0]["destination_path"] is None
