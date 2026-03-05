"""Comprehensive tests for PluginExecutor: _readline_with_timeout, call() error paths,
context manager cleanup, and subprocess management."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.errors import PluginError, PluginLoadError
from file_organizer.plugins.executor import PluginExecutor
from file_organizer.plugins.ipc import PluginResult, encode_result
from file_organizer.plugins.security import PluginSecurityPolicy

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(
    plugin_path: str = "fake/plugin.py",
    plugin_name: str = "fake-plugin",
) -> PluginExecutor:
    """Create an executor without starting it."""
    return PluginExecutor(
        plugin_path=Path(plugin_path),
        plugin_name=plugin_name,
        policy=PluginSecurityPolicy.unrestricted(),
    )


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestExecutorInit:
    """Tests for PluginExecutor.__init__."""

    def test_default_name_from_path(self) -> None:
        ex = PluginExecutor(plugin_path=Path("foo/bar/my_plugin.py"))
        assert ex._plugin_name == "my_plugin"

    def test_explicit_name(self) -> None:
        ex = PluginExecutor(plugin_path=Path("foo/plugin.py"), plugin_name="custom")
        assert ex._plugin_name == "custom"

    def test_default_policy_is_unrestricted(self) -> None:
        ex = PluginExecutor(plugin_path=Path("foo/plugin.py"))
        assert ex._policy.allow_all_paths is True
        assert ex._policy.allow_all_operations is True

    def test_proc_starts_none(self) -> None:
        ex = _make_executor()
        assert ex._proc is None


# ---------------------------------------------------------------------------
# _readline_with_timeout
# ---------------------------------------------------------------------------


class TestReadlineWithTimeout:
    """Tests for _readline_with_timeout edge cases."""

    def test_raises_when_proc_is_none(self) -> None:
        ex = _make_executor()
        with pytest.raises(PluginError, match="not running"):
            ex._readline_with_timeout()

    def test_raises_when_stdout_is_none(self) -> None:
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdout = None
        with pytest.raises(PluginError, match="not running"):
            ex._readline_with_timeout()

    @patch("file_organizer.plugins.executor.sys")
    @patch("file_organizer.plugins.executor.select")
    def test_timeout_on_unix(self, mock_select: MagicMock, mock_sys: MagicMock) -> None:
        """When select returns empty ready-list, should raise timeout error."""
        mock_sys.platform = "linux"
        mock_select.select.return_value = ([], [], [])

        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdout = MagicMock()

        with pytest.raises(PluginError, match="did not respond within"):
            ex._readline_with_timeout(timeout=0.1)

    @patch("file_organizer.plugins.executor.sys")
    @patch("file_organizer.plugins.executor.select")
    def test_successful_read_on_unix(self, mock_select: MagicMock, mock_sys: MagicMock) -> None:
        """When select says ready, readline should be called and returned."""
        mock_sys.platform = "linux"
        stdout_mock = MagicMock()
        stdout_mock.readline.return_value = b'{"success":true}\n'
        mock_select.select.return_value = ([stdout_mock], [], [])

        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdout = stdout_mock

        result = ex._readline_with_timeout(timeout=5.0)
        assert result == b'{"success":true}\n'


# ---------------------------------------------------------------------------
# call() error paths
# ---------------------------------------------------------------------------


class TestCallErrors:
    """Tests for PluginExecutor.call() error paths."""

    def test_call_before_start_raises_runtime_error(self) -> None:
        ex = _make_executor()
        with pytest.raises(RuntimeError, match="not started"):
            ex.call("on_load")

    def test_call_with_closed_stdin_raises(self) -> None:
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = None
        ex._proc.stdout = MagicMock()
        with pytest.raises(PluginError, match="unexpectedly closed"):
            ex.call("on_load")

    def test_call_with_closed_stdout_raises(self) -> None:
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = None
        with pytest.raises(PluginError, match="unexpectedly closed"):
            ex.call("on_load")

    def test_broken_pipe_raises_plugin_error(self) -> None:
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin.write.side_effect = BrokenPipeError("pipe broken")
        ex._proc.stdout = MagicMock()
        with pytest.raises(PluginError, match="died before receiving"):
            ex.call("some_method")

    def test_empty_response_raises_plugin_error(self) -> None:
        """When worker closes stdout (returns empty bytes), raise PluginError."""
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = MagicMock()
        ex._proc.stderr = MagicMock()
        ex._proc.stderr.read.return_value = b"some stderr"

        with patch.object(ex, "_readline_with_timeout", return_value=b""):
            with pytest.raises(PluginError, match="closed stdout unexpectedly"):
                ex.call("on_load")

    def test_corrupt_response_raises_plugin_error(self) -> None:
        """When response is not valid JSON, raise PluginError."""
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = MagicMock()

        with patch.object(ex, "_readline_with_timeout", return_value=b"not json\n"):
            with pytest.raises(PluginError, match="Corrupt IPC response"):
                ex.call("on_load")

    def test_error_result_on_load_raises_load_error(self) -> None:
        """on_load failures should surface as PluginLoadError."""
        result = PluginResult(success=False, error="init failed")
        raw = encode_result(result)
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = MagicMock()

        with patch.object(ex, "_readline_with_timeout", return_value=raw):
            with pytest.raises(PluginLoadError, match="init failed"):
                ex.call("on_load")

    def test_error_result_on_other_method_raises_plugin_error(self) -> None:
        """Non-on_load failures should raise PluginError (not PluginLoadError)."""
        result = PluginResult(success=False, error="runtime fail")
        raw = encode_result(result)
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = MagicMock()

        with patch.object(ex, "_readline_with_timeout", return_value=raw):
            with pytest.raises(PluginError, match="runtime fail"):
                ex.call("on_enable")

    def test_successful_call_returns_value(self) -> None:
        result = PluginResult(success=True, return_value={"key": "val"})
        raw = encode_result(result)
        ex = _make_executor()
        ex._proc = MagicMock()
        ex._proc.stdin = MagicMock()
        ex._proc.stdout = MagicMock()

        with patch.object(ex, "_readline_with_timeout", return_value=raw):
            ret = ex.call("process_file", "tmp/x.txt")
        assert ret == {"key": "val"}


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    """Tests for __enter__/__exit__ context manager protocol."""

    def test_enter_calls_start(self) -> None:
        ex = _make_executor()
        with patch.object(ex, "start") as mock_start, patch.object(ex, "stop"):
            with ex:
                mock_start.assert_called_once()

    def test_exit_calls_stop(self) -> None:
        ex = _make_executor()
        with patch.object(ex, "start"), patch.object(ex, "stop") as mock_stop:
            with ex:
                pass
        mock_stop.assert_called_once()

    def test_exit_calls_stop_on_exception(self) -> None:
        ex = _make_executor()
        with patch.object(ex, "start"), patch.object(ex, "stop") as mock_stop:
            with pytest.raises(ValueError, match="boom"):
                with ex:
                    raise ValueError("boom")
        mock_stop.assert_called_once()


# ---------------------------------------------------------------------------
# stop() idempotency
# ---------------------------------------------------------------------------


class TestStop:
    """Tests for PluginExecutor.stop() cleanup."""

    def test_stop_when_not_started_is_noop(self) -> None:
        ex = _make_executor()
        ex.stop()  # Should not raise

    def test_stop_terminates_and_clears_proc(self) -> None:
        ex = _make_executor()
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        ex._proc = mock_proc

        ex.stop()
        mock_proc.terminate.assert_called_once()
        assert ex._proc is None

    def test_stop_kills_on_timeout(self) -> None:
        ex = _make_executor()
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        ex._proc = mock_proc

        ex.stop()
        mock_proc.kill.assert_called_once()
        assert ex._proc is None

    def test_double_stop_is_noop(self) -> None:
        ex = _make_executor()
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        ex._proc = mock_proc

        ex.stop()
        ex.stop()  # Second call is noop
        assert ex._proc is None


# ---------------------------------------------------------------------------
# start() idempotency
# ---------------------------------------------------------------------------


class TestStart:
    """Tests for PluginExecutor.start()."""

    def test_start_already_started_is_noop(self) -> None:
        ex = _make_executor()
        ex._proc = MagicMock()  # Pretend already started
        ex.start()  # Should not spawn another process

    @patch("file_organizer.plugins.executor.subprocess.Popen")
    def test_start_oserror_raises_load_error(self, mock_popen: MagicMock) -> None:
        mock_popen.side_effect = OSError("cannot spawn")
        ex = _make_executor()
        with pytest.raises(PluginLoadError, match="Failed to spawn worker"):
            ex.start()
