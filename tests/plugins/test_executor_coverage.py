"""Coverage tests for plugins.executor module."""

from __future__ import annotations

import queue
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.errors import PluginError, PluginLoadError
from file_organizer.plugins.executor import PluginExecutor
from file_organizer.plugins.ipc import PluginResult

pytestmark = pytest.mark.unit


class TestPluginExecutorInit:
    def test_default_name_from_path(self):
        executor = PluginExecutor(plugin_path=Path("/plugins/my_plugin.py"))
        assert executor._plugin_name == "my_plugin"

    def test_custom_name(self):
        executor = PluginExecutor(
            plugin_path=Path("/plugins/foo.py"),
            plugin_name="custom",
        )
        assert executor._plugin_name == "custom"

    def test_default_policy_is_unrestricted(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        assert executor._policy.allow_all_paths is True


class TestPluginExecutorStart:
    def test_start_noop_when_already_started(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = MagicMock()
        executor.start()
        # Should not spawn another process

    @patch("file_organizer.plugins.executor.subprocess.Popen")
    def test_start_spawns_subprocess(self, mock_popen):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor.start()

        mock_popen.assert_called_once()
        assert executor._proc is mock_proc

    @patch("file_organizer.plugins.executor.subprocess.Popen")
    def test_start_raises_plugin_load_error_on_os_error(self, mock_popen):
        mock_popen.side_effect = OSError("no such file")

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        with pytest.raises(PluginLoadError, match="Failed to spawn worker"):
            executor.start()


class TestPluginExecutorStop:
    def test_stop_noop_when_not_started(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor.stop()
        assert executor._proc is None

    def test_stop_terminates_process(self):
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = mock_proc

        executor.stop()

        mock_proc.terminate.assert_called_once()
        assert executor._proc is None

    def test_stop_kills_on_timeout(self):
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), 0]
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = mock_proc

        executor.stop()

        mock_proc.kill.assert_called_once()
        assert executor._proc is None

    def test_stop_handles_pipe_close_errors(self):
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_stdin = MagicMock()
        mock_stdin.close.side_effect = OSError("broken")
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = mock_proc

        # Should not raise
        executor.stop()
        assert executor._proc is None


class TestPluginExecutorContextManager:
    @patch("file_organizer.plugins.executor.subprocess.Popen")
    def test_context_manager_starts_and_stops(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_popen.return_value = mock_proc

        executor = PluginExecutor(plugin_path=Path("/x.py"))
        with executor as ex:
            assert ex is executor
            assert executor._proc is not None

        assert executor._proc is None


class TestPluginExecutorCall:
    def test_call_raises_when_not_started(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        with pytest.raises(RuntimeError, match="not started"):
            executor.call("on_load")

    def test_call_raises_when_pipes_closed(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor._proc = MagicMock()
        executor._proc.stdin = None
        executor._proc.stdout = None

        with pytest.raises(PluginError, match="unexpectedly closed"):
            executor.call("on_load")

    def test_call_raises_on_broken_pipe(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        mock_proc = MagicMock()
        mock_proc.stdin.write.side_effect = BrokenPipeError("broken")
        executor._proc = mock_proc

        with pytest.raises(PluginError, match="died before receiving"):
            executor.call("some_method")

    @patch.object(PluginExecutor, "_readline_with_timeout")
    def test_call_raises_on_empty_response(self, mock_readline):
        mock_readline.return_value = b""
        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        mock_proc = MagicMock()
        mock_proc.stderr.read.return_value = b"error output"
        executor._proc = mock_proc

        with pytest.raises(PluginError, match="closed stdout unexpectedly"):
            executor.call("method")

    @patch("file_organizer.plugins.executor.decode_result")
    @patch.object(PluginExecutor, "_readline_with_timeout")
    def test_call_raises_on_corrupt_ipc(self, mock_readline, mock_decode):
        mock_readline.return_value = b"bad json\n"
        mock_decode.side_effect = ValueError("invalid")

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor._proc = MagicMock()

        with pytest.raises(PluginError, match="Corrupt IPC response"):
            executor.call("method")

    @patch("file_organizer.plugins.executor.decode_result")
    @patch.object(PluginExecutor, "_readline_with_timeout")
    def test_call_returns_value_on_success(self, mock_readline, mock_decode):
        mock_readline.return_value = b'{"ok":true}\n'
        mock_decode.return_value = PluginResult(success=True, return_value=42)

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor._proc = MagicMock()

        result = executor.call("method")
        assert result == 42

    @patch("file_organizer.plugins.executor.decode_result")
    @patch.object(PluginExecutor, "_readline_with_timeout")
    def test_call_raises_plugin_error_on_failure(self, mock_readline, mock_decode):
        mock_readline.return_value = b'{"ok":false}\n'
        mock_decode.return_value = PluginResult(success=False, error="something went wrong")

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor._proc = MagicMock()

        with pytest.raises(PluginError, match="raised an error"):
            executor.call("some_method")

    @patch("file_organizer.plugins.executor.decode_result")
    @patch.object(PluginExecutor, "_readline_with_timeout")
    def test_call_raises_load_error_for_on_load(self, mock_readline, mock_decode):
        mock_readline.return_value = b'{"ok":false}\n'
        mock_decode.return_value = PluginResult(success=False, error="init failed")

        executor = PluginExecutor(plugin_path=Path("/x.py"), plugin_name="test")
        executor._proc = MagicMock()

        with pytest.raises(PluginLoadError, match="raised an error"):
            executor.call("on_load")


class TestReadlineWithTimeout:
    def test_raises_when_proc_none(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = None

        with pytest.raises(PluginError, match="not running"):
            executor._readline_with_timeout()

    def test_raises_when_stdout_none(self):
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        executor._proc = MagicMock()
        executor._proc.stdout = None

        with pytest.raises(PluginError, match="not running"):
            executor._readline_with_timeout()

    @patch("file_organizer.plugins.executor.sys")
    def test_windows_timeout_raises(self, mock_sys):
        mock_sys.platform = "win32"
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        mock_proc = MagicMock()
        mock_stdout = MagicMock()

        # Simulate queue timeout
        executor._proc = mock_proc
        executor._proc.stdout = mock_stdout

        with patch("file_organizer.plugins.executor.queue.Queue") as mock_queue_cls:
            mock_q = MagicMock()
            mock_q.get.side_effect = queue.Empty
            mock_queue_cls.return_value = mock_q

            with patch("file_organizer.plugins.executor.threading.Thread") as mock_thread:
                thread_instance = MagicMock()
                mock_thread.return_value = thread_instance

                with pytest.raises(PluginError, match="did not respond"):
                    executor._readline_with_timeout(timeout=0.01)

    @patch("file_organizer.plugins.executor.sys")
    @patch("file_organizer.plugins.executor.select.select")
    def test_unix_timeout_raises(self, mock_select, mock_sys):
        mock_sys.platform = "linux"
        mock_select.return_value = ([], [], [])

        executor = PluginExecutor(plugin_path=Path("/x.py"))
        mock_proc = MagicMock()
        executor._proc = mock_proc

        with pytest.raises(PluginError, match="did not respond"):
            executor._readline_with_timeout(timeout=0.01)

    @patch("file_organizer.plugins.executor.sys")
    @patch("file_organizer.plugins.executor.select.select")
    def test_unix_success(self, mock_select, mock_sys):
        mock_sys.platform = "linux"
        executor = PluginExecutor(plugin_path=Path("/x.py"))
        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = b"data\n"
        executor._proc = mock_proc
        mock_select.return_value = ([mock_proc.stdout], [], [])

        result = executor._readline_with_timeout()
        assert result == b"data\n"
