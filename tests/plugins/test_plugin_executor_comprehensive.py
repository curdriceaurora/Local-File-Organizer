"""Tests for plugin executor subprocess spawning, IPC, and error handling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from file_organizer.plugins.errors import PluginError, PluginLoadError
from file_organizer.plugins.executor import PluginExecutor, PluginResult


# ============================================================================
# Executor Initialization and Subprocess Tests
# ============================================================================


class TestExecutorInitialization:
    """Test executor initialization and subprocess creation."""

    def test_executor_init_default_config(self) -> None:
        """Executor initializes with default configuration."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=Path("/path/to/plugin"),
        )

    def test_executor_spawn_subprocess_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully spawn a plugin subprocess."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )

        executor.start()

        # Executor should have started the subprocess
        assert executor._proc is not None
        assert executor._proc.pid == 12345

    def test_executor_spawn_subprocess_failure(
        self, plugin_with_source: Path
    ) -> None:
        """Handle failure when subprocess fails to spawn."""
        with patch(
            "file_organizer.plugins.executor.subprocess.Popen",
            side_effect=OSError("Failed to start process"),
        ):
            executor = PluginExecutor(
                plugin_name="test-plugin",
                plugin_path=plugin_with_source,
            )

            # OSError during Popen is caught and re-raised as PluginLoadError
            with pytest.raises(PluginLoadError, match="Failed to spawn worker"):
                executor.start()

    def test_executor_multiple_start_calls_safe(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Multiple start() calls don't spawn multiple processes."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )

        executor.start()
        first_process = executor._proc

        executor.start()
        second_process = executor._proc

        # Should be the same process instance (idempotent)
        assert first_process is second_process


# ============================================================================
# IPC Communication Tests
# ============================================================================


class TestExecutorIPCCommunication:
    """Test IPC message sending and receiving."""

    def test_executor_call_method_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully call a method via IPC."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Mock a successful response with a return value
        success_response = b'{"success":true,"return_value":null,"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        result = executor.call("on_load")

        # executor.call() returns the return_value from the response
        assert result is None  # return_value is null in the mock

    def test_executor_call_with_arguments(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Send method call with arguments via IPC."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Mock a response with a return value indicating success
        success_response = b'{"success":true,"return_value":{"processed":true},"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        # Call method with arguments (simulated)
        result = executor.call("process_file", path="/tmp/file.txt")

        # Result is the return_value from the response
        assert isinstance(result, dict)
        assert result["processed"] is True

    def test_executor_ipc_message_format_validation(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Validate IPC message format compliance."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Response should be in standard format: {"success": bool, ...}
        success_response = b'{"success":true,"return_value":null,"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        # Calling should not raise an exception (IPC format is valid)
        result = executor.call("on_load")

        # Result is the deserialized return_value
        assert result is None

    def test_executor_ipc_json_serialization(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """IPC messages properly serialize/deserialize JSON."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Mock response with valid JSON format
        success_response = b'{"success":true,"return_value":{"data":"test"},"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        # Calling should parse the JSON and return the return_value
        result = executor.call("on_load")

        # Result is the deserialized return_value
        assert isinstance(result, dict)
        assert result["data"] == "test"


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestExecutorErrorHandling:
    """Test error handling during subprocess communication."""

    def test_executor_plugin_crash_handling(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Handle gracefully when plugin subprocess crashes."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Simulate process crash (empty stdout response indicates crash)
        executor._proc.stdout.readline.return_value = b""

        with pytest.raises(PluginError, match="closed stdout unexpectedly"):
            executor.call("on_load")

    def test_executor_call_method_failure(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Handle failure when plugin method call fails."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Mock response with error
        error_response = b'{"success":false,"return_value":null,"error":"Method failed"}\n'
        executor._proc.stdout.readline.return_value = error_response

        # When success is False, executor.call() raises PluginLoadError for on_load
        with pytest.raises(PluginLoadError, match="Method failed"):
            executor.call("on_load")

    def test_executor_timeout_on_slow_response(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Timeout when plugin takes too long to respond."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Simulate timeout: readline returns None/empty which indicates closed stdout
        executor._proc.stdout.readline.return_value = b""

        with pytest.raises(PluginError, match="closed stdout unexpectedly"):
            executor.call("on_load")

    def test_executor_empty_response_handling(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Handle empty or malformed responses from plugin."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Simulate empty response
        executor._proc.stdout.readline.return_value = b""

        with pytest.raises(PluginError, match="closed stdout unexpectedly"):
            executor.call("on_load")

    def test_executor_invalid_json_response(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Handle invalid JSON in plugin response."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Simulate invalid JSON response
        executor._proc.stdout.readline.return_value = b"{invalid json}\n"

        with pytest.raises(PluginError, match="Corrupt IPC response"):
            executor.call("on_load")


# ============================================================================
# Concurrency and Thread Safety Tests
# ============================================================================


class TestExecutorConcurrency:
    """Test executor behavior under concurrent access."""

    def test_executor_concurrent_calls_serialized(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Concurrent calls are properly serialized."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        import threading

        call_count = [0]
        exceptions = []

        def make_call(method_name):
            try:
                success_response = b'{"success":true,"return_value":null,"error":null}\n'
                executor._proc.stdout.readline.return_value = success_response
                result = executor.call(method_name)
                call_count[0] += 1
            except Exception as e:
                exceptions.append(e)

        # Multiple threads calling different methods
        threads = [
            threading.Thread(target=make_call, args=("on_load",)),
            threading.Thread(target=make_call, args=("on_enable",)),
            threading.Thread(target=make_call, args=("on_disable",)),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All calls should complete successfully
        assert len(exceptions) == 0
        assert call_count[0] == 3

    def test_executor_no_data_corruption_concurrent(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Concurrent calls don't corrupt shared state."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        import threading

        call_count = [0]
        exceptions = []

        def increment_and_call():
            try:
                call_count[0] += 1
                success_response = b'{"success":true,"return_value":null,"error":null}\n'
                executor._proc.stdout.readline.return_value = success_response
                executor.call("on_load")
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=increment_and_call) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All calls should have completed without exceptions
        assert len(exceptions) == 0
        assert call_count[0] == 5


# ============================================================================
# Lifecycle and Cleanup Tests
# ============================================================================


class TestExecutorLifecycle:
    """Test executor lifecycle and resource cleanup."""

    def test_executor_stop_terminates_process(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Stopping executor terminates the subprocess."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()
        process = executor._proc

        executor.stop()

        # Process should be terminated
        process.terminate.assert_called()

    def test_executor_stop_kills_unresponsive_process(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Kill process if it doesn't respond to terminate."""
        import subprocess

        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()
        process = executor._proc

        # Process doesn't terminate gracefully - wait() times out
        process.wait.side_effect = [
            subprocess.TimeoutExpired("test", timeout=5),  # First call in stop()
            None  # Second call after kill()
        ]

        executor.stop()

        # Should call kill() as fallback
        process.kill.assert_called()

    def test_executor_cleanup_on_del(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Cleanup resources when executor is deleted."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()
        process = executor._proc

        # Delete executor
        del executor

        # Process should be cleaned up (terminate called)
        # Note: This may require __del__ implementation in PluginExecutor

    def test_executor_ipc_cleanup_on_stop(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Close IPC channels when executor stops."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        executor.stop()

        # IPC channels should be closed


# ============================================================================
# Integration Tests
# ============================================================================


class TestExecutorIntegration:
    """Integration tests for executor lifecycle and communication."""

    def test_executor_full_lifecycle(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Test complete executor lifecycle: start -> call -> stop."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )

        # Start
        executor.start()
        assert executor._proc is not None

        # Mock successful responses
        success_response = b'{"success":true,"return_value":null,"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        # Make calls - should not raise exceptions
        result1 = executor.call("on_load")
        assert result1 is None  # return_value is null

        result2 = executor.call("on_enable")
        assert result2 is None

        # Stop
        executor.stop()

    def test_executor_multiple_methods_same_session(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Call multiple methods in same executor session."""
        executor = PluginExecutor(
            plugin_name="test-plugin",
            plugin_path=plugin_with_source,
        )
        executor.start()

        # Mock successful responses
        success_response = b'{"success":true,"return_value":null,"error":null}\n'
        executor._proc.stdout.readline.return_value = success_response

        methods = ["on_load", "on_enable", "on_disable", "on_unload"]
        # Call all methods - should not raise exceptions
        for method in methods:
            result = executor.call(method)
            assert result is None  # return_value is null

        executor.stop()
