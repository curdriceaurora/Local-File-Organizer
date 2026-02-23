"""Subprocess-isolated plugin executor.

Each :class:`PluginExecutor` instance manages exactly one long-lived child
process that loads and runs a single plugin module.  Communication between
the host and the worker uses newline-delimited JSON (see :mod:`.ipc`) over
the child's ``stdin`` / ``stdout`` pipes.

No ``pickle`` is used at any point — only JSON — so a malicious plugin
cannot deserialise arbitrary Python objects inside the host process.

Typical usage::

    from pathlib import Path
    from file_organizer.plugins.executor import PluginExecutor
    from file_organizer.plugins.security import PluginSecurityPolicy

    policy = PluginSecurityPolicy.from_permissions(
        allowed_paths=["/data/uploads"],
        allowed_operations=["read"],
    )
    with PluginExecutor(
        plugin_path=Path("/path/to/my_plugin.py"),
        plugin_name="my_plugin",
        policy=policy,
    ) as executor:
        executor.call("on_load")
        result = executor.call("on_file", "/tmp/foo.txt", {})
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

from file_organizer.plugins.errors import PluginError, PluginLoadError
from file_organizer.plugins.ipc import (
    PluginCall,
    PluginResult,
    decode_result,
    encode_call,
)
from file_organizer.plugins.security import PluginSecurityPolicy

# ---------------------------------------------------------------------------
# Worker entrypoint (runs inside the child process)
# ---------------------------------------------------------------------------


def _worker(plugin_path: str, policy_dict: dict[str, Any]) -> None:  # pragma: no cover
    """Entry-point executed inside the sandboxed child process.

    This function is *not* called from the host process; it is invoked by
    the child process that :class:`PluginExecutor` spawns via
    ``sys.executable -c``.

    Steps performed inside the child:

    1. Apply ``resource`` limits (RLIMIT_NOFILE, RLIMIT_CPU) when the
       ``resource`` module is available (Linux/macOS only).
    2. Dynamically import the plugin module from *plugin_path*.
    3. Instantiate the first concrete :class:`~file_organizer.plugins.base.Plugin`
       subclass found in the module.
    4. Enter a read loop: read :class:`~.ipc.PluginCall` messages from
       ``stdin``, dispatch to the plugin instance, write
       :class:`~.ipc.PluginResult` responses to ``stdout``.

    Args:
        plugin_path: Filesystem path to the plugin ``.py`` file.
        policy_dict: JSON-safe dict representation of the security policy
            (currently used for future enforcement hooks; resource limits are
            applied unconditionally when available).
    """
    import importlib.util
    import sys
    from pathlib import Path

    # ------------------------------------------------------------------
    # 1. Apply resource limits (best-effort; Linux/macOS only)
    # ------------------------------------------------------------------
    try:
        import resource  # type: ignore[import-not-found]

        # Restrict open file descriptors to a safe minimum
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        # Limit CPU time to 60 seconds per child lifetime
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    except (ImportError, ValueError):
        pass  # Windows or kernel limit already tighter — silently skip
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 2. Dynamically load the plugin module
    # ------------------------------------------------------------------
    path = Path(plugin_path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"Cannot create module spec for plugin: {plugin_path}\n")
        sys.exit(1)

    module = types.ModuleType(path.stem)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        sys.stderr.write(f"Error loading plugin module '{plugin_path}': {exc}\n")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Find and instantiate the first concrete Plugin subclass
    # ------------------------------------------------------------------
    from file_organizer.plugins.base import Plugin

    plugin_instance: Plugin | None = None
    for _attr_name in dir(module):
        obj = getattr(module, _attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Plugin)
            and obj is not Plugin
        ):
            try:
                plugin_instance = obj()
            except Exception as exc:
                sys.stderr.write(
                    f"Error instantiating plugin class '{_attr_name}': {exc}\n"
                )
                sys.exit(1)
            break

    if plugin_instance is None:
        sys.stderr.write(f"No Plugin subclass found in: {plugin_path}\n")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. IPC loop — read PluginCall from stdin, write PluginResult to stdout
    # ------------------------------------------------------------------
    from file_organizer.plugins.ipc import PluginResult, decode_call, encode_result

    stdin_bin = sys.stdin.buffer
    stdout_bin = sys.stdout.buffer

    for raw_line in stdin_bin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            call = decode_call(raw_line)
        except ValueError as exc:
            result = PluginResult(success=False, error=f"IPC decode error: {exc}")
            stdout_bin.write(encode_result(result))
            stdout_bin.flush()
            continue

        try:
            method = getattr(plugin_instance, call.method)
            ret = method(*call.args, **call.kwargs)
            result = PluginResult(success=True, return_value=ret)
        except Exception as exc:
            result = PluginResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        try:
            stdout_bin.write(encode_result(result))
        except (TypeError, ValueError):
            # return_value was not JSON-serialisable — report gracefully
            result = PluginResult(
                success=False,
                error="Return value is not JSON-serialisable",
            )
            stdout_bin.write(encode_result(result))

        stdout_bin.flush()


# ---------------------------------------------------------------------------
# Host-side executor
# ---------------------------------------------------------------------------


class PluginExecutor:
    """Manages a sandboxed child process that runs a single plugin.

    The child process is spawned lazily via :meth:`start` and kept alive for
    the executor's lifetime.  :meth:`call` sends a :class:`~.ipc.PluginCall`
    over stdin and reads back the :class:`~.ipc.PluginResult` from stdout.

    Args:
        plugin_path: Path (or path string) to the plugin ``.py`` file.
        plugin_name: Human-readable name used for error messages.  Defaults
            to the plugin file's stem when not supplied.
        policy: Security policy serialised and forwarded to the worker.
            Defaults to :meth:`~.security.PluginSecurityPolicy.unrestricted`
            when not supplied.

    Raises:
        PluginLoadError: If :meth:`start` fails to spawn the worker.
        PluginError: If :meth:`call` receives an error result from the worker.
    """

    def __init__(
        self,
        plugin_path: Path | str,
        plugin_name: str | None = None,
        policy: PluginSecurityPolicy | None = None,
    ) -> None:
        self._plugin_path = Path(plugin_path)
        self._plugin_name = plugin_name or self._plugin_path.stem
        self._policy = policy or PluginSecurityPolicy.unrestricted()
        self._proc: subprocess.Popen[bytes] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the worker subprocess.

        The child process is started with ``stdin=PIPE`` and ``stdout=PIPE``
        so that the host can communicate over JSON-encoded messages.

        Raises:
            PluginLoadError: If the subprocess cannot be started.
        """
        if self._proc is not None:
            return  # Already started

        policy_dict: dict[str, Any] = {
            "allowed_paths": [str(p) for p in self._policy.allowed_paths],
            "allowed_operations": list(self._policy.allowed_operations),
            "allow_all_paths": self._policy.allow_all_paths,
            "allow_all_operations": self._policy.allow_all_operations,
        }

        # Build a self-contained bootstrap expression that:
        # 1. Imports _worker from this very module.
        # 2. Calls it with the plugin path and the JSON-encoded policy dict.
        # Using repr() for the string args ensures correct quoting and
        # escaping regardless of path content.
        bootstrap = (
            "import sys, json; "
            "from file_organizer.plugins.executor import _worker; "
            f"_worker({str(self._plugin_path)!r}, json.loads({json.dumps(policy_dict)!r}))"
        )

        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-c", bootstrap],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise PluginLoadError(
                f"Failed to spawn worker for plugin '{self._plugin_name}': {exc}"
            ) from exc

    def stop(self) -> None:
        """Terminate the worker subprocess and release resources.

        This method is idempotent; calling it on an already-stopped executor
        is a no-op.
        """
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        finally:
            self._proc = None

    def __enter__(self) -> PluginExecutor:
        """Start the executor as a context manager.

        Returns:
            This :class:`PluginExecutor` instance.
        """
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Stop the executor when exiting the context manager.

        Args:
            exc_type: Exception type, if any.
            exc_val: Exception value, if any.
            exc_tb: Traceback, if any.
        """
        self.stop()

    # ------------------------------------------------------------------
    # RPC
    # ------------------------------------------------------------------

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a method on the sandboxed plugin instance.

        Serialises a :class:`~.ipc.PluginCall`, writes it to the worker's
        stdin, reads back a :class:`~.ipc.PluginResult` from stdout, and
        returns the result's ``return_value``.

        Args:
            method: Name of the plugin method to invoke.
            *args: Positional arguments forwarded to the method.
            **kwargs: Keyword arguments forwarded to the method.

        Returns:
            The JSON-deserialised return value from the plugin method.

        Raises:
            RuntimeError: If :meth:`start` has not been called yet.
            PluginError: If the worker reports an error or the child process
                dies unexpectedly.
        """
        if self._proc is None:
            raise RuntimeError(
                f"PluginExecutor for '{self._plugin_name}' is not started. "
                "Call start() or use it as a context manager."
            )
        if self._proc.stdin is None or self._proc.stdout is None:
            raise PluginError(
                f"Worker pipes for '{self._plugin_name}' are unexpectedly closed."
            )

        call_msg = PluginCall(method=method, args=list(args), kwargs=kwargs)
        try:
            self._proc.stdin.write(encode_call(call_msg))
            self._proc.stdin.flush()
        except BrokenPipeError as exc:
            raise PluginError(
                f"Worker for '{self._plugin_name}' died before receiving "
                f"call '{method}'."
            ) from exc

        raw = self._proc.stdout.readline()
        if not raw:
            stderr_output = ""
            if self._proc.stderr:
                stderr_output = self._proc.stderr.read().decode(errors="replace")
            raise PluginError(
                f"Worker for '{self._plugin_name}' closed stdout unexpectedly "
                f"(method='{method}'). Stderr: {stderr_output!r}"
            )

        try:
            result: PluginResult = decode_result(raw)
        except ValueError as exc:
            raise PluginError(
                f"Corrupt IPC response from '{self._plugin_name}' "
                f"(method='{method}'): {exc}"
            ) from exc

        if not result.success:
            error_msg = (
                f"Plugin '{self._plugin_name}' raised an error in "
                f"'{method}': {result.error}"
            )
            # on_load failures surface as PluginLoadError so callers can
            # distinguish initialisation errors from runtime errors.
            if method == "on_load":
                raise PluginLoadError(error_msg)
            raise PluginError(error_msg)

        return result.return_value
