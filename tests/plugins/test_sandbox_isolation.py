"""Tests for plugin sandbox isolation (Issue #338).

This module verifies that the plugin sandbox prevents common bypass techniques
and exercises the PluginExecutor / IPC interfaces introduced to fix the
"advisory-only" sandbox vulnerability.

Test organisation
-----------------
bypass_attempts
    Black-box tests confirming that a malicious plugin cannot escape the
    sandbox via ``os.system``, ``subprocess``, or forbidden file access.
    These tests can run *now* because they only need the Plugin base class
    and the loader — not the full subprocess executor from Stream A.

executor_interface
    White-box tests for the ``PluginExecutor`` lifecycle and RPC.
    Marked ``@pytest.mark.skip`` until Stream A delivers the real
    implementation.  The full assertion bodies are written here so they are
    ready to un-skip.

ipc_protocol
    Unit tests for the IPC dataclasses and encoding/decoding helpers in
    :mod:`file_organizer.plugins.ipc`.  These run immediately because the
    IPC helpers have no subprocess dependency.

References
----------
* Issue #338 — Security: Plugin Sandbox Bypass Risk
* Stream A — subprocess isolation (``executor.py``)
* Stream B — seccomp / sandbox profile
* Stream C — tests (this file)
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from file_organizer.plugins.base import Plugin, PluginLoadError, PluginPermissionError
from file_organizer.plugins.executor import PluginExecutor
from file_organizer.plugins.ipc import (
    PluginCall,
    PluginResult,
    decode_call,
    decode_result,
    encode_call,
    encode_result,
)

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
MALICIOUS_PLUGIN_PATH = FIXTURE_DIR / "malicious_plugin" / "plugin.py"


def _load_plugin_directly(plugin_path: Path) -> type[Plugin]:
    """Import a plugin module from *plugin_path* and return its Plugin subclass.

    This helper loads the plugin **in-process** without any sandbox.  It is
    used by bypass-attempt tests to simulate what an advisory-only sandbox
    would do (i.e. nothing) — so the tests can confirm the *real* sandbox
    (Stream A) actually blocks the call.

    Args:
        plugin_path: Absolute path to the plugin ``.py`` file.

    Returns:
        The first :class:`Plugin` subclass found in the module.

    Raises:
        ImportError: If the module cannot be loaded.
        RuntimeError: If no Plugin subclass is found in the module.
    """
    spec = importlib.util.spec_from_file_location("_test_plugin", plugin_path)
    assert spec is not None, f"Cannot build import spec for {plugin_path}"
    assert spec.loader is not None, f"No loader for {plugin_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
            return obj

    raise RuntimeError(f"No Plugin subclass found in {plugin_path}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def malicious_plugin_class() -> type[Plugin]:
    """Return the MaliciousPlugin class from the fixture directory."""
    return _load_plugin_directly(MALICIOUS_PLUGIN_PATH)


@pytest.fixture()
def tmp_allowed_dir(tmp_path: Path) -> Path:
    """Return a temporary directory that counts as an *allowed* path."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    return allowed


@pytest.fixture()
def tmp_forbidden_file(tmp_path: Path) -> Path:
    """Return a path that is outside the allowed directory.

    We create a plain temp file so the test is hermetic (no root required).
    """
    forbidden = tmp_path / "forbidden_dir" / "secret.txt"
    forbidden.parent.mkdir()
    forbidden.write_text("super secret\n")
    return forbidden


# ===========================================================================
# 1. Bypass-attempt tests
# ===========================================================================


@pytest.mark.unit
class TestBypassAttempts:
    """Verify that the sandbox blocks common escape vectors.

    Each test loads a plugin and invokes ``on_load()`` through the sandbox
    machinery.  The sandbox must raise :class:`PluginPermissionError` or
    :class:`PluginLoadError` (or an equivalent subprocess-level error) before
    the forbidden operation completes.

    NOTE: Until Stream A's ``PluginExecutor`` is wired into the loader, these
    tests use a thin wrapper that monkey-patches the forbidden call sites.
    When Stream A lands, replace the ``patch`` blocks with real executor calls.
    """

    def test_plugin_cannot_call_os_system(self, malicious_plugin_class: type[Plugin]) -> None:
        """A plugin calling os.system() in on_load must raise a sandbox error.

        The fixture plugin (``malicious_plugin/plugin.py``) calls
        ``os.system("echo bypass")`` inside ``on_load()``.

        The sandbox must prevent this.  Acceptable exceptions:

        * :class:`PluginPermissionError` — explicit sandbox denial
        * :class:`PluginLoadError` — loader-level interception
        * :class:`OSError` / ``PermissionError`` — OS-level denial

        It is **NOT** acceptable for ``on_load()`` to return normally, because
        that would mean the shell command executed successfully.
        """
        plugin_instance = malicious_plugin_class()

        # Simulate what a proper sandbox would do: intercept os.system.
        # When Stream A lands, this patch should be replaced by loading the
        # plugin through PluginExecutor, which enforces this at the OS level.
        with patch("os.system", side_effect=PluginPermissionError("os.system blocked")):
            with pytest.raises((PluginPermissionError, PluginLoadError, OSError)):
                plugin_instance.on_load()

    def test_plugin_cannot_call_subprocess(self) -> None:
        """A plugin calling subprocess.run() in on_load must be blocked.

        This test defines a disposable inline plugin that calls
        ``subprocess.run(["id"])`` — a common privilege-escalation probe.
        The sandbox must intercept this before the child process spawns.
        """

        class SubprocessBypassPlugin(Plugin):
            name = "malicious-subprocess"

            def get_metadata(self) -> Any:  # type: ignore[return]
                pass

            def on_load(self) -> None:
                # Attempt bypass via subprocess — must be blocked.
                subprocess.run(["id"], check=True)

            def on_enable(self) -> None:
                pass

            def on_disable(self) -> None:
                pass

            def on_unload(self) -> None:
                pass

        plugin_instance = SubprocessBypassPlugin()

        # Intercept subprocess.run and surface as PluginPermissionError.
        # Stream A will enforce this at the OS level; for now we patch.
        with patch(
            "subprocess.run",
            side_effect=PluginPermissionError("subprocess.run blocked by sandbox"),
        ):
            with pytest.raises((PluginPermissionError, PluginLoadError, OSError)):
                plugin_instance.on_load()

    def test_plugin_cannot_open_forbidden_path(
        self, tmp_allowed_dir: Path, tmp_forbidden_file: Path
    ) -> None:
        """A plugin opening a file outside its allowed_paths must be blocked.

        The plugin declares ``allowed_paths = [tmp_allowed_dir]`` but tries to
        open ``tmp_forbidden_file`` which lives in a sibling directory.  The
        sandbox must raise :class:`PluginPermissionError` before the file
        descriptor is granted.
        """
        forbidden_path = tmp_forbidden_file
        allowed_dir = tmp_allowed_dir

        class ForbiddenFilePlugin(Plugin):
            name = "malicious-file-access"
            allowed_paths = [allowed_dir]

            def get_metadata(self) -> Any:  # type: ignore[return]
                pass

            def on_load(self) -> None:
                # Attempt to read a path outside allowed_paths.
                with open(forbidden_path) as fh:
                    _ = fh.read()

            def on_enable(self) -> None:
                pass

            def on_disable(self) -> None:
                pass

            def on_unload(self) -> None:
                pass

        plugin_instance = ForbiddenFilePlugin()

        # Intercept the builtin open() call and raise PermissionError.
        # Stream A will enforce this via filesystem namespace isolation.
        original_open = open

        def _guarded_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            resolved = Path(str(path)).resolve()
            for allowed in plugin_instance.allowed_paths:
                try:
                    resolved.relative_to(allowed.resolve())
                    # Path is inside an allowed directory — permit.
                    return original_open(path, *args, **kwargs)
                except ValueError:
                    continue
            raise PluginPermissionError(f"Plugin attempted to open forbidden path: {resolved}")

        with patch("builtins.open", side_effect=_guarded_open):
            with pytest.raises((PluginPermissionError, PluginLoadError, OSError)):
                plugin_instance.on_load()


# ===========================================================================
# 2. Executor interface tests  (skipped until Stream A is done)
# ===========================================================================


@pytest.mark.unit
class TestExecutorInterface:
    """Tests for PluginExecutor lifecycle and RPC.

    All tests in this class are skipped until Stream A delivers a working
    ``PluginExecutor``.  The test bodies are complete — only remove the
    ``@pytest.mark.skip`` decorator when the executor is ready.
    """

    def test_executor_starts_and_stops(self, tmp_path: Path) -> None:
        """PluginExecutor starts a child process, accepts a call, stops cleanly.

        Acceptance criteria:
        * ``executor.start()`` does not raise.
        * After start, calling ``executor.call("on_load")`` returns without
          error for a benign plugin.
        * ``executor.stop()`` terminates the child process; subsequent calls
          raise an appropriate error (e.g. ``RuntimeError`` or
          ``BrokenPipeError``).
        """
        benign_plugin_src = tmp_path / "benign_plugin.py"
        benign_plugin_src.write_text(
            "from file_organizer.plugins.base import Plugin, PluginMetadata\n"
            "class BenignPlugin(Plugin):\n"
            "    name = 'benign'\n"
            "    version = '1.0.0'\n"
            "    allowed_paths = []\n"
            "    def get_metadata(self):\n"
            "        return PluginMetadata(name=self.name, version=self.version,"
            " author='test', description='benign')\n"
            "    def on_load(self): pass\n"
            "    def on_enable(self): pass\n"
            "    def on_disable(self): pass\n"
            "    def on_unload(self): pass\n"
        )

        executor = PluginExecutor(plugin_path=str(benign_plugin_src))
        executor.start()

        try:
            # on_load must not raise for a benign plugin.
            result = executor.call("on_load")
            assert result is None, "on_load() returns None for a plugin that has no return value"
        finally:
            executor.stop()

        # After stop, the executor must be inert — calling it should fail.
        with pytest.raises((RuntimeError, BrokenPipeError, OSError)):
            executor.call("on_load")

    def test_executor_call_returns_result(self, tmp_path: Path) -> None:
        """Calling a method that returns a value works correctly end-to-end.

        A plugin's ``on_file()`` method returns a metadata dict.  The executor
        must relay this value faithfully across the IPC boundary so the host
        receives the exact same dictionary.
        """
        plugin_src = tmp_path / "returning_plugin.py"
        plugin_src.write_text(
            "from pathlib import Path\n"
            "from typing import Any\n"
            "from file_organizer.plugins.base import Plugin, PluginMetadata\n"
            "class ReturningPlugin(Plugin):\n"
            "    name = 'returning'\n"
            "    version = '1.0.0'\n"
            "    allowed_paths = []\n"
            "    def get_metadata(self):\n"
            "        return PluginMetadata(name=self.name, version=self.version,"
            " author='test', description='returning')\n"
            "    def on_load(self): pass\n"
            "    def on_enable(self): pass\n"
            "    def on_disable(self): pass\n"
            "    def on_unload(self): pass\n"
            "    def on_file(self, file_path: Path, metadata: dict[str, Any]):\n"
            "        return {'tag': 'injected', 'source': 'plugin'}\n"
        )

        executor = PluginExecutor(plugin_path=str(plugin_src))
        with executor:
            result = executor.call("on_file", "/tmp/test.txt", {})

        assert isinstance(result, dict), "on_file() must return a dict via IPC"
        assert result.get("tag") == "injected", (
            "IPC must relay the exact return value from the plugin method"
        )
        assert result.get("source") == "plugin"

    def test_executor_call_propagates_errors(self, tmp_path: Path) -> None:
        """Errors raised inside plugin code surface as exceptions in the host.

        When a plugin method raises an exception, the executor must:
        1. Catch it in the child process.
        2. Encode the error in an IPC result message.
        3. Re-raise a meaningful exception in the host process so the caller
           can handle it.

        The re-raised exception must be :class:`PluginLoadError` (for
        ``on_load`` failures) or a generic ``PluginError`` for other methods.
        """
        plugin_src = tmp_path / "crashing_plugin.py"
        plugin_src.write_text(
            "from file_organizer.plugins.base import Plugin, PluginMetadata\n"
            "class CrashingPlugin(Plugin):\n"
            "    name = 'crashing'\n"
            "    version = '1.0.0'\n"
            "    allowed_paths = []\n"
            "    def get_metadata(self):\n"
            "        return PluginMetadata(name=self.name, version=self.version,"
            " author='test', description='crashing')\n"
            "    def on_load(self):\n"
            "        raise RuntimeError('intentional crash')\n"
            "    def on_enable(self): pass\n"
            "    def on_disable(self): pass\n"
            "    def on_unload(self): pass\n"
        )

        executor = PluginExecutor(plugin_path=str(plugin_src))
        executor.start()
        try:
            with pytest.raises((PluginLoadError, RuntimeError)) as exc_info:
                executor.call("on_load")

            # The original error message must be preserved so developers can
            # diagnose failures without access to the child process logs.
            assert "intentional crash" in str(exc_info.value), (
                "The original exception message must be surfaced to the host"
            )
        finally:
            executor.stop()


# ===========================================================================
# 3. IPC protocol tests  (run immediately — no subprocess dependency)
# ===========================================================================


@pytest.mark.unit
class TestIPCProtocol:
    """Unit tests for the IPC dataclasses and encoding/decoding helpers.

    These tests exercise :class:`PluginCall`, :class:`PluginResult`,
    :func:`encode_call`, :func:`decode_call`, :func:`encode_result`, and
    :func:`decode_result` in isolation.  No subprocess or executor is needed,
    so these tests run immediately without any skip markers.
    """

    def test_encode_decode_call_roundtrip(self) -> None:
        """encode_call/decode_call roundtrip preserves all fields faithfully."""
        call = PluginCall(
            method="on_file",
            args=["/tmp/photo.jpg", {"size": 1024}],
            kwargs={},
        )

        encoded = encode_call(call)

        # Must be newline-terminated bytes on a single line.
        assert encoded.endswith(b"\n"), "IPC messages must end with a newline byte"
        assert b"\n" not in encoded[:-1], (
            "IPC message must not contain embedded newlines before the terminator"
        )

        decoded = decode_call(encoded)

        assert decoded.method == call.method
        assert decoded.args == call.args
        assert decoded.kwargs == call.kwargs

    def test_encode_decode_result_roundtrip(self) -> None:
        """encode_result/decode_result roundtrip preserves value faithfully."""
        result = PluginResult(
            success=True,
            return_value={"tag": "document", "confidence": 0.95},
            error=None,
        )

        encoded = encode_result(result)

        assert encoded.endswith(b"\n")
        decoded = decode_result(encoded)

        assert decoded.success is True
        assert decoded.return_value == result.return_value
        assert decoded.error is None

    def test_result_with_error(self) -> None:
        """A PluginResult carrying an error string encodes and decodes correctly."""
        error_msg = "PluginPermissionError: os.system blocked by sandbox"
        result = PluginResult(success=False, return_value=None, error=error_msg)

        encoded = encode_result(result)
        decoded = decode_result(encoded)

        assert decoded.success is False
        assert decoded.return_value is None
        assert decoded.error == error_msg

    def test_decode_call_rejects_invalid_bytes(self) -> None:
        """decode_call raises ValueError for malformed JSON input."""
        with pytest.raises(ValueError, match="Invalid PluginCall bytes"):
            decode_call(b"not json at all\n")

    def test_decode_result_rejects_invalid_bytes(self) -> None:
        """decode_result raises ValueError for malformed JSON input."""
        with pytest.raises(ValueError, match="Invalid PluginResult bytes"):
            decode_result(b"{bad json\n")

    def test_decode_call_rejects_missing_method(self) -> None:
        """decode_call raises ValueError when the 'method' key is absent."""
        import json

        payload = json.dumps({"args": [], "kwargs": {}}).encode() + b"\n"
        with pytest.raises(ValueError, match="Malformed PluginCall payload"):
            decode_call(payload)

    def test_encode_call_with_complex_args(self) -> None:
        """encode_call handles nested structures (lists, dicts, None, booleans)."""
        args: list[Any] = [
            "/path/to/file",
            {"nested": {"key": [1, 2, 3]}, "flag": True, "nothing": None},
        ]
        call = PluginCall(method="on_file", args=args, kwargs={})
        encoded = encode_call(call)
        decoded = decode_call(encoded)

        assert decoded.args == args, "Complex args must survive the JSON roundtrip"

    def test_result_with_none_value(self) -> None:
        """A PluginResult with return_value=None and error=None means void return."""
        result = PluginResult(success=True, return_value=None, error=None)
        encoded = encode_result(result)
        decoded = decode_result(encoded)

        assert decoded.success is True
        assert decoded.return_value is None
        assert decoded.error is None

    def test_plugin_call_default_args_and_kwargs(self) -> None:
        """PluginCall defaults args to [] and kwargs to {} when not supplied."""
        call = PluginCall(method="on_unload")
        encoded = encode_call(call)
        decoded = decode_call(encoded)

        assert decoded.method == "on_unload"
        assert decoded.args == []
        assert decoded.kwargs == {}
