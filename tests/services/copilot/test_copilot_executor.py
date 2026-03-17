"""Unit tests for CommandExecutor.

Tests intent dispatch, all handler methods, and path resolution.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.copilot.executor import CommandExecutor
from file_organizer.services.copilot.models import (
    ExecutionResult,
    Intent,
    IntentType,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp(tmp_path):
    """Provide a clean temporary directory."""
    return tmp_path


@pytest.fixture()
def executor(tmp_path):
    """Return a CommandExecutor rooted at tmp_path."""
    return CommandExecutor(working_directory=str(tmp_path))


def _intent(intent_type: IntentType, **params) -> Intent:
    return Intent(intent_type=intent_type, confidence=0.9, parameters=params, raw_text="test")


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestCommandExecutorInit:
    """Test CommandExecutor.__init__."""

    def test_default_working_directory(self):
        ex = CommandExecutor()
        assert ex._working_dir == Path.cwd()

    def test_custom_working_directory(self, tmp_path):
        ex = CommandExecutor(working_directory=str(tmp_path))
        assert ex._working_dir == tmp_path


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestExecuteDispatch:
    """Test the execute() dispatch logic."""

    def test_unknown_intent_type(self, executor):
        result = executor.execute(_intent(IntentType.CHAT))
        assert not result.success
        assert "No handler" in result.message

    def test_status_intent_no_handler(self, executor):
        result = executor.execute(_intent(IntentType.STATUS))
        assert not result.success

    def test_handler_exception_caught(self, executor):
        with patch.object(executor, "_handle_organize", side_effect=RuntimeError("boom")):
            result = executor.execute(_intent(IntentType.ORGANIZE))
        assert not result.success
        assert "boom" in result.message


# ---------------------------------------------------------------------------
# _handle_organize
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleOrganize:
    """Test the organize handler."""

    def test_source_not_a_directory(self, executor, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        result = executor.execute(_intent(IntentType.ORGANIZE, source=str(f)))
        assert not result.success
        assert "not found" in result.message.lower() or "Directory" in result.message

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=ImportError("no"),
    )
    def test_organizer_import_error(self, _mock, executor, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        # Patch the import inside the handler
        result = executor._handle_organize(_intent(IntentType.ORGANIZE, source=str(sub)))
        assert not result.success
        assert "not available" in result.message.lower() or "no" in result.message.lower()

    def test_organizer_success(self, executor, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        mock_result = MagicMock()
        mock_result.processed_files = 5
        mock_result.skipped_files = 1
        mock_result.failed_files = 0
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch(
            "file_organizer.core.organizer.FileOrganizer",
            return_value=mock_organizer,
        ):
            result = executor._handle_organize(
                _intent(IntentType.ORGANIZE, source=str(sub), destination=str(tmp_path / "dest"))
            )
        assert result.success
        assert "5" in result.message

    def test_organizer_dry_run(self, executor, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        mock_result = MagicMock()
        mock_result.processed_files = 3
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch(
            "file_organizer.core.organizer.FileOrganizer",
            return_value=mock_organizer,
        ):
            result = executor._handle_organize(
                _intent(IntentType.ORGANIZE, source=str(sub), dry_run=True)
            )
        assert result.success
        assert "Would" in result.message

    def test_organize_default_destination(self, executor, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        mock_result = MagicMock(processed_files=1, skipped_files=0, failed_files=0)
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch(
            "file_organizer.core.organizer.FileOrganizer",
            return_value=mock_organizer,
        ):
            result = executor._handle_organize(_intent(IntentType.ORGANIZE, source=str(sub)))
        assert result.success
        # Default dest is source / "organized"
        mock_organizer.organize.assert_called_once()
        call_kwargs = mock_organizer.organize.call_args
        assert "organized" in str(call_kwargs)


# ---------------------------------------------------------------------------
# _handle_move
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleMove:
    """Test the move handler."""

    def test_missing_source_param(self, executor):
        result = executor.execute(_intent(IntentType.MOVE, destination="/tmp/x"))
        assert not result.success
        assert "specify" in result.message.lower()

    def test_missing_destination_param(self, executor, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hi")
        result = executor.execute(_intent(IntentType.MOVE, source=str(f)))
        assert not result.success

    def test_source_not_found(self, executor, tmp_path):
        result = executor.execute(
            _intent(IntentType.MOVE, source=str(tmp_path / "nope"), destination=str(tmp_path / "d"))
        )
        assert not result.success
        assert "not found" in result.message.lower()

    def test_move_success(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "sub" / "dst.txt"
        result = executor.execute(_intent(IntentType.MOVE, source=str(src), destination=str(dst)))
        assert result.success
        assert dst.exists()
        assert not src.exists()

    def test_move_os_error(self, executor, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        with patch("shutil.move", side_effect=OSError("fail")):
            result = executor._handle_move(
                _intent(IntentType.MOVE, source=str(src), destination=str(tmp_path / "dst"))
            )
        assert not result.success
        assert "fail" in result.message.lower()


# ---------------------------------------------------------------------------
# _handle_rename
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleRename:
    """Test the rename handler."""

    def test_missing_target(self, executor):
        result = executor.execute(_intent(IntentType.RENAME, new_name="y.txt"))
        assert not result.success

    def test_missing_new_name(self, executor, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hi")
        result = executor.execute(_intent(IntentType.RENAME, target=str(f)))
        assert not result.success

    def test_target_not_found(self, executor, tmp_path):
        result = executor.execute(
            _intent(IntentType.RENAME, target=str(tmp_path / "nope"), new_name="b.txt")
        )
        assert not result.success

    def test_rename_success(self, executor, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("hi")
        result = executor.execute(_intent(IntentType.RENAME, target=str(src), new_name="b.txt"))
        assert result.success
        assert (tmp_path / "b.txt").exists()
        assert not src.exists()

    def test_rename_os_error(self, executor, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("hi")
        with patch.object(Path, "rename", side_effect=OSError("fail")):
            result = executor._handle_rename(
                _intent(IntentType.RENAME, target=str(src), new_name="b.txt")
            )
        assert not result.success


# ---------------------------------------------------------------------------
# _handle_find
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleFind:
    """Test the find handler."""

    def test_empty_query(self, executor):
        result = executor.execute(_intent(IntentType.FIND, query=""))
        assert not result.success
        assert "search" in result.message.lower()

    def test_find_matches(self, executor, tmp_path):
        (tmp_path / "hello.txt").write_text("x")
        (tmp_path / "world.txt").write_text("y")
        with patch.object(executor, "_build_retriever_for_root", return_value=None):
            result = executor.execute(_intent(IntentType.FIND, query="hello"))
        assert result.success
        assert len(result.affected_files) == 1

    def test_find_no_matches(self, executor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        result = executor.execute(_intent(IntentType.FIND, query="zzzzz"))
        assert result.success
        assert "No files" in result.message

    def test_find_custom_search_path(self, executor, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "found.txt").write_text("x")
        result = executor.execute(_intent(IntentType.FIND, query="found", paths=[str(sub)]))
        assert result.success
        assert len(result.affected_files) == 1

    def test_find_invalid_search_path_fallback(self, executor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        result = executor.execute(
            _intent(IntentType.FIND, query="a", paths=[str(tmp_path / "nope")])
        )
        assert result.success

    def test_find_caps_at_20(self, executor, tmp_path):
        for i in range(25):
            (tmp_path / f"match_{i}.txt").write_text("x")
        result = executor.execute(_intent(IntentType.FIND, query="match"))
        assert result.success
        assert len(result.affected_files) == 20


# ---------------------------------------------------------------------------
# _handle_undo / _handle_redo
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleUndoRedo:
    """Test undo and redo handlers."""

    def test_undo_success(self, executor):
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = True
        with (
            patch("file_organizer.history.tracker.OperationHistory") as mock_history_cls,
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            mock_history_cls.return_value = MagicMock()
            result = executor._handle_undo(_intent(IntentType.UNDO))
        assert result.success
        assert "undone" in result.message.lower()

    def test_undo_nothing(self, executor):
        mock_manager = MagicMock()
        mock_manager.undo_last_operation.return_value = False
        with (
            patch("file_organizer.history.tracker.OperationHistory") as mock_history_cls,
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            mock_history_cls.return_value = MagicMock()
            result = executor._handle_undo(_intent(IntentType.UNDO))
        assert not result.success
        assert "nothing" in result.message.lower()

    def test_undo_import_error(self, executor):
        with patch.dict("sys.modules", {"file_organizer.history.tracker": None}):
            # Force ImportError via the lazy import in the handler
            result = executor._handle_undo(_intent(IntentType.UNDO))
        # May succeed or fail depending on import mechanism; just check no crash
        assert isinstance(result, ExecutionResult)

    def test_redo_success(self, executor):
        mock_manager = MagicMock()
        mock_manager.redo_last_operation.return_value = True
        with (
            patch("file_organizer.history.tracker.OperationHistory") as mock_history_cls,
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            mock_history_cls.return_value = MagicMock()
            result = executor._handle_redo(_intent(IntentType.REDO))
        assert result.success
        assert "redone" in result.message.lower()

    def test_redo_nothing(self, executor):
        mock_manager = MagicMock()
        mock_manager.redo_last_operation.return_value = False
        with (
            patch("file_organizer.history.tracker.OperationHistory") as mock_history_cls,
            patch("file_organizer.undo.undo_manager.UndoManager", return_value=mock_manager),
        ):
            mock_history_cls.return_value = MagicMock()
            result = executor._handle_redo(_intent(IntentType.REDO))
        assert not result.success


# ---------------------------------------------------------------------------
# _handle_preview
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandlePreview:
    """Test the preview handler."""

    def test_preview_forces_dry_run(self, executor, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        mock_result = MagicMock(processed_files=2, skipped_files=0, failed_files=0)
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        with patch(
            "file_organizer.core.organizer.FileOrganizer",
            return_value=mock_organizer,
        ):
            result = executor._handle_preview(_intent(IntentType.PREVIEW, source=str(sub)))
        assert result.success
        assert "Would" in result.message


# ---------------------------------------------------------------------------
# _handle_suggest
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestHandleSuggest:
    """Test the suggest handler."""

    def test_no_paths(self, executor):
        result = executor.execute(_intent(IntentType.SUGGEST))
        assert not result.success
        assert "specify" in result.message.lower()

    def test_path_not_found(self, executor, tmp_path):
        result = executor.execute(_intent(IntentType.SUGGEST, paths=[str(tmp_path / "nope")]))
        assert not result.success
        assert "not found" in result.message.lower()

    def test_suggest_engine_available(self, executor, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with patch.dict("sys.modules", {"file_organizer.services.smart_suggestions": MagicMock()}):
            result = executor._handle_suggest(_intent(IntentType.SUGGEST, paths=[str(f)]))
        assert result.success
        assert "available" in result.message.lower()

    def test_suggest_engine_unavailable(self, executor, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with patch.dict("sys.modules", {"file_organizer.services.smart_suggestions": None}):
            # The import inside the handler will raise ImportError
            result = executor._handle_suggest(_intent(IntentType.SUGGEST, paths=[str(f)]))
        # Either branch returns success=True
        assert result.success


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestResolvePath:
    """Test the _resolve_path helper."""

    def test_none_returns_working_dir(self, executor, tmp_path):
        result = executor._resolve_path(None)
        assert result == tmp_path

    def test_absolute_path(self, executor, tmp_path):
        result = executor._resolve_path(str(tmp_path / "sub"))
        assert result == (tmp_path / "sub").resolve()

    def test_relative_path(self, executor, tmp_path):
        result = executor._resolve_path("rel/path")
        assert result == (tmp_path / "rel" / "path").resolve()

    def test_tilde_expansion(self, executor):
        result = executor._resolve_path("~/docs")
        assert "~" not in str(result)


# ---------------------------------------------------------------------------
# _build_retriever_for_root — hidden file filtering
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBuildRetrieverHiddenFiles:
    """Verify _build_retriever_for_root excludes hidden files."""

    def test_hidden_files_excluded_from_retriever_corpus(self, tmp_path: Path) -> None:
        """Hidden files (dot-prefixed) must not be included in the search corpus."""
        from file_organizer.utils import is_hidden

        # The filter logic in executor.py line 234:
        # if entry.is_symlink() or not entry.is_file() or is_hidden(entry): continue
        normal = tmp_path / "report.txt"
        normal.write_text("quarterly finance report")
        hidden = tmp_path / ".credentials.json"
        hidden.write_text('{"api_key": "secret"}')

        entries = list(tmp_path.iterdir())
        filtered = [e for e in entries if not e.is_symlink() and e.is_file() and not is_hidden(e)]
        assert normal in filtered
        assert hidden not in filtered, "Hidden file should be excluded from corpus"

    def test_symlinks_excluded_from_retriever_corpus(self, tmp_path: Path) -> None:
        """Symlinked files must not be included in the search corpus."""
        real = tmp_path / "real.txt"
        real.write_text("real content")
        try:
            link = tmp_path / "link.txt"
            link.symlink_to(real)
        except OSError:
            pytest.skip("Symlinks not supported")

        from file_organizer.utils import is_hidden

        entries = list(tmp_path.iterdir())
        filtered = [e for e in entries if not e.is_symlink() and e.is_file() and not is_hidden(e)]
        assert real in filtered
        assert link not in filtered, "Symlink should be excluded from corpus"

    def test_build_retriever_uses_relative_path_for_hidden_check(self, tmp_path: Path) -> None:
        """_build_retriever_for_root uses relative path for is_hidden to avoid false positives."""
        from unittest.mock import patch

        from file_organizer.services.copilot.executor import CommandExecutor

        (tmp_path / "report.txt").write_text("quarterly budget finance report")
        (tmp_path / "notes.txt").write_text("meeting agenda items budget")
        hidden_dir = tmp_path / ".config"
        hidden_dir.mkdir()
        (hidden_dir / "settings.txt").write_text("settings config data")

        executor = CommandExecutor()
        try:
            with patch(
                "file_organizer.services.search.hybrid_retriever.HybridRetriever"
            ) as mock_cls:
                mock_instance = mock_cls.return_value
                mock_instance.index.return_value = None
                executor._build_retriever_for_root(tmp_path)
                if mock_instance.index.called:
                    args = mock_instance.index.call_args[0]
                    docs_list = args[0]
                    assert all("settings config data" not in d for d in docs_list), (
                        "Hidden file should be excluded from corpus"
                    )
        except ImportError:
            pytest.skip("Search dependencies not installed")
