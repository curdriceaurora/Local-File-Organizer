"""Coverage tests for file_organizer.api.service_facade — uncovered methods.

Targets lines 153-498: organize_files, daemon methods, get_model_status,
get_suggestions, find_duplicates, undo_last_operation, get_operation_history,
and error paths for all of the above.
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.service_facade import ServiceFacade

pytestmark = pytest.mark.unit

_SETTINGS = ApiSettings(
    environment="test",
    auth_enabled=False,
    auth_jwt_secret="test-secret",
    rate_limit_enabled=False,
)


def _facade() -> ServiceFacade:
    return ServiceFacade(settings=_SETTINGS)


# ---------------------------------------------------------------------------
# organize_files
# ---------------------------------------------------------------------------


class TestOrganizeFiles:
    """Tests for ServiceFacade.organize_files."""

    @pytest.mark.asyncio
    async def test_organize_files_success(self, tmp_path) -> None:
        """organize_files returns success dict on happy path."""
        mock_result = MagicMock()
        mock_result.total_files = 3
        mock_result.processed_files = 3
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.5
        mock_result.organized_structure = {}
        mock_result.errors = {}

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            facade = _facade()
            result = await facade.organize_files(str(tmp_path), output_dir=str(tmp_path / "out"))

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_organize_files_no_output_dir(self, tmp_path) -> None:
        """organize_files uses source_dir when output_dir is None."""
        mock_result = MagicMock()
        mock_result.total_files = 0
        mock_result.processed_files = 0
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.0
        mock_result.organized_structure = {}
        mock_result.errors = {}

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer) as mock_cls:
            facade = _facade()
            result = await facade.organize_files(str(tmp_path))

        assert result["success"] is True
        assert result["data"]["dry_run"] is False
        mock_cls.assert_called_once_with(dry_run=False)
        mock_organizer.organize.assert_called_once_with(
            input_path=str(tmp_path), output_path=str(tmp_path)
        )

    @pytest.mark.asyncio
    async def test_organize_files_dry_run(self, tmp_path) -> None:
        """organize_files dry_run=True propagates to result."""
        mock_result = MagicMock()
        mock_result.total_files = 2
        mock_result.processed_files = 2
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.processing_time = 0.1
        mock_result.organized_structure = {}
        mock_result.errors = {}

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer) as mock_cls:
            facade = _facade()
            result = await facade.organize_files(str(tmp_path), dry_run=True)

        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        mock_cls.assert_called_once_with(dry_run=True)
        mock_organizer.organize.assert_called_once_with(
            input_path=str(tmp_path), output_path=str(tmp_path)
        )

    @pytest.mark.asyncio
    async def test_organize_files_exception(self, tmp_path) -> None:
        """organize_files returns error dict when FileOrganizer raises."""
        with patch("file_organizer.core.organizer.FileOrganizer", side_effect=RuntimeError("boom")):
            facade = _facade()
            result = await facade.organize_files(str(tmp_path))

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Daemon management
# ---------------------------------------------------------------------------


class TestDaemonManagement:
    """Tests for daemon start/stop/status via ServiceFacade."""

    def _mock_daemon(self, *, running: bool = False) -> MagicMock:
        daemon = MagicMock()
        daemon.is_running = running
        daemon.uptime_seconds = 0.0
        daemon.files_processed = 0
        daemon.start_background = MagicMock()
        daemon.stop = MagicMock()
        return daemon

    @pytest.mark.asyncio
    async def test_get_daemon_status_success(self) -> None:
        """get_daemon_status returns running/uptime/files_processed."""
        mock_daemon = self._mock_daemon(running=True)
        mock_daemon.uptime_seconds = 42.0
        mock_daemon.files_processed = 7

        facade = _facade()
        facade._daemon_service = mock_daemon

        result = await facade.get_daemon_status()

        assert result["success"] is True
        assert result["data"]["running"] is True
        assert result["data"]["uptime_seconds"] == 42.0
        assert result["data"]["files_processed"] == 7

    @pytest.mark.asyncio
    async def test_get_daemon_status_error(self) -> None:
        """get_daemon_status returns error dict when attribute access raises."""

        class _RaisingDaemon:
            @property
            def is_running(self) -> bool:
                raise RuntimeError("daemon crash")

        facade = _facade()
        facade._daemon_service = _RaisingDaemon()

        result = await facade.get_daemon_status()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_start_daemon_success(self) -> None:
        """start_daemon returns started=True on success."""
        mock_daemon = self._mock_daemon()
        facade = _facade()
        facade._daemon_service = mock_daemon

        result = await facade.start_daemon()

        assert result["success"] is True
        assert result["data"]["started"] is True
        mock_daemon.start_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_daemon_error(self) -> None:
        """start_daemon returns error dict when start raises."""
        mock_daemon = MagicMock()
        mock_daemon.start_background.side_effect = RuntimeError("no start")
        facade = _facade()
        facade._daemon_service = mock_daemon

        result = await facade.start_daemon()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_stop_daemon_success(self) -> None:
        """stop_daemon returns stopped=True on success."""
        mock_daemon = self._mock_daemon(running=True)
        facade = _facade()
        facade._daemon_service = mock_daemon

        result = await facade.stop_daemon()

        assert result["success"] is True
        assert result["data"]["stopped"] is True
        mock_daemon.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_daemon_error(self) -> None:
        """stop_daemon returns error dict when stop raises."""
        mock_daemon = MagicMock()
        mock_daemon.stop.side_effect = RuntimeError("no stop")
        facade = _facade()
        facade._daemon_service = mock_daemon

        result = await facade.stop_daemon()

        assert result["success"] is False

    def test_get_daemon_service_creates_instance(self) -> None:
        """_get_daemon_service lazily creates DaemonService on first call."""
        mock_service = MagicMock()
        mock_config_class = MagicMock(return_value=MagicMock())
        mock_service_class = MagicMock(return_value=mock_service)

        facade = _facade()
        assert facade._daemon_service is None

        with (
            patch("file_organizer.daemon.config.DaemonConfig", mock_config_class),
            patch("file_organizer.daemon.service.DaemonService", mock_service_class),
        ):
            svc = facade._get_daemon_service()

        assert svc is not None

    def test_get_daemon_service_returns_cached(self) -> None:
        """_get_daemon_service returns the same instance on repeated calls."""
        mock_service = MagicMock()
        facade = _facade()
        facade._daemon_service = mock_service

        result = facade._get_daemon_service()

        assert result is mock_service


# ---------------------------------------------------------------------------
# get_model_status
# ---------------------------------------------------------------------------


class TestGetModelStatus:
    """Tests for ServiceFacade.get_model_status."""

    @pytest.mark.asyncio
    async def test_get_model_status_success(self) -> None:
        """get_model_status returns model list on success."""
        mock_model = MagicMock()
        mock_model.name = "qwen2.5:3b"
        mock_model.model_type = "text"
        mock_model.size = "1.9 GB"
        mock_model.quantization = "q4_K_M"
        mock_model.description = "Small text model"
        mock_model.installed = True

        mock_manager = MagicMock()
        mock_manager.list_models.return_value = [mock_model]

        with patch("file_organizer.models.model_manager.ModelManager", return_value=mock_manager):
            facade = _facade()
            result = await facade.get_model_status()

        assert result["success"] is True
        assert len(result["data"]["models"]) == 1
        assert result["data"]["models"][0]["name"] == "qwen2.5:3b"

    @pytest.mark.asyncio
    async def test_get_model_status_empty(self) -> None:
        """get_model_status returns empty list when no models configured."""
        mock_manager = MagicMock()
        mock_manager.list_models.return_value = []

        with patch("file_organizer.models.model_manager.ModelManager", return_value=mock_manager):
            facade = _facade()
            result = await facade.get_model_status()

        assert result["success"] is True
        assert result["data"]["models"] == []

    @pytest.mark.asyncio
    async def test_get_model_status_error(self) -> None:
        """get_model_status returns error dict on exception."""
        with patch("file_organizer.models.model_manager.ModelManager", side_effect=RuntimeError("no models")):
            facade = _facade()
            result = await facade.get_model_status()

        assert result["success"] is False


# ---------------------------------------------------------------------------
# get_suggestions
# ---------------------------------------------------------------------------


class TestGetSuggestions:
    """Tests for ServiceFacade.get_suggestions."""

    @pytest.mark.asyncio
    async def test_get_suggestions_success(self, tmp_path) -> None:
        """get_suggestions returns suggestion list on success."""
        mock_suggestion = MagicMock()
        mock_suggestion.suggestion_type = MagicMock()
        mock_suggestion.suggestion_type.value = "move"
        mock_suggestion.file_path = tmp_path / "test.txt"
        mock_suggestion.target_path = tmp_path / "docs" / "test.txt"
        mock_suggestion.confidence = 0.9
        mock_suggestion.reasoning = "Based on content"

        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [mock_suggestion]

        (tmp_path / "test.txt").write_text("hello")

        with patch("file_organizer.services.smart_suggestions.SuggestionEngine", return_value=mock_engine):
            facade = _facade()
            result = await facade.get_suggestions(str(tmp_path))

        assert result["success"] is True
        assert len(result["data"]["suggestions"]) == 1

    @pytest.mark.asyncio
    async def test_get_suggestions_error(self, tmp_path) -> None:
        """get_suggestions returns error dict on exception."""
        with patch("file_organizer.services.smart_suggestions.SuggestionEngine", side_effect=RuntimeError("boom")):
            facade = _facade()
            result = await facade.get_suggestions(str(tmp_path))

        assert result["success"] is False


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


class TestFindDuplicates:
    """Tests for ServiceFacade.find_duplicates."""

    @pytest.mark.asyncio
    async def test_find_duplicates_success(self, tmp_path) -> None:
        """find_duplicates returns statistics and groups on success."""
        mock_file = MagicMock()
        mock_file.path = tmp_path / "a.txt"

        mock_group = MagicMock()
        mock_group.files = [mock_file, mock_file]

        mock_detector = MagicMock()
        mock_detector.get_statistics.return_value = {"total_duplicates": 1}
        mock_detector.get_duplicate_groups.return_value = {"abc123": mock_group}

        with patch("file_organizer.services.deduplication.detector.DuplicateDetector", return_value=mock_detector):
            facade = _facade()
            result = await facade.find_duplicates(str(tmp_path))

        assert result["success"] is True
        assert "statistics" in result["data"]
        assert len(result["data"]["groups"]) == 1

    @pytest.mark.asyncio
    async def test_find_duplicates_error(self, tmp_path) -> None:
        """find_duplicates returns error dict on exception."""
        with patch("file_organizer.services.deduplication.detector.DuplicateDetector", side_effect=RuntimeError("no dedup")):
            facade = _facade()
            result = await facade.find_duplicates(str(tmp_path))

        assert result["success"] is False


# ---------------------------------------------------------------------------
# undo_last_operation
# ---------------------------------------------------------------------------


class TestUndoLastOperation:
    """Tests for ServiceFacade.undo_last_operation."""

    @pytest.mark.asyncio
    async def test_undo_success_true(self) -> None:
        """undo_last_operation returns undone=True when operation was undone."""
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True

        with patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager):
            facade = _facade()
            result = await facade.undo_last_operation()

        assert result["success"] is True
        assert result["data"]["undone"] is True

    @pytest.mark.asyncio
    async def test_undo_success_false(self) -> None:
        """undo_last_operation returns undone=False when nothing to undo."""
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = False

        with patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager):
            facade = _facade()
            result = await facade.undo_last_operation()

        assert result["success"] is True
        assert result["data"]["undone"] is False

    @pytest.mark.asyncio
    async def test_undo_error(self) -> None:
        """undo_last_operation returns error dict on exception."""
        with patch("file_organizer.undo.undo_manager.UndoManager", side_effect=RuntimeError("no undo")):
            facade = _facade()
            result = await facade.undo_last_operation()

        assert result["success"] is False


# ---------------------------------------------------------------------------
# get_operation_history
# ---------------------------------------------------------------------------


class TestGetOperationHistory:
    """Tests for ServiceFacade.get_operation_history."""

    @pytest.mark.asyncio
    async def test_get_history_success(self) -> None:
        """get_operation_history returns serialised operations list."""
        from datetime import datetime

        mock_op = MagicMock()
        mock_op.id = "op-1"
        mock_op.operation_type = MagicMock()
        mock_op.operation_type.value = "move"
        mock_op.source_path = "/src/a.txt"
        mock_op.destination_path = "/dst/a.txt"
        mock_op.status = MagicMock()
        mock_op.status.value = "completed"
        mock_op.timestamp = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

        mock_history = MagicMock()
        mock_history.get_recent_operations.return_value = [mock_op]

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            facade = _facade()
            result = await facade.get_operation_history(limit=5)

        assert result["success"] is True
        assert len(result["data"]["operations"]) == 1
        assert result["data"]["operations"][0]["id"] == "op-1"
        mock_history.get_recent_operations.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_get_history_no_destination(self) -> None:
        """get_operation_history handles operations with no destination path."""
        from datetime import datetime

        mock_op = MagicMock()
        mock_op.id = "op-2"
        mock_op.operation_type = MagicMock()
        mock_op.operation_type.value = "delete"
        mock_op.source_path = "/src/b.txt"
        mock_op.destination_path = None
        mock_op.status = MagicMock()
        mock_op.status.value = "completed"
        mock_op.timestamp = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)

        mock_history = MagicMock()
        mock_history.get_recent_operations.return_value = [mock_op]

        with patch("file_organizer.history.tracker.OperationHistory", return_value=mock_history):
            facade = _facade()
            result = await facade.get_operation_history()

        assert result["success"] is True
        assert result["data"]["operations"][0]["destination_path"] is None

    @pytest.mark.asyncio
    async def test_get_history_error(self) -> None:
        """get_operation_history returns error dict on exception."""
        with patch("file_organizer.history.tracker.OperationHistory", side_effect=RuntimeError("no history")):
            facade = _facade()
            result = await facade.get_operation_history()

        assert result["success"] is False
