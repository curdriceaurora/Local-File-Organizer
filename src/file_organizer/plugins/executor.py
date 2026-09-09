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
import logging
import os
import queue
import select
import subprocess
import sys
import threading
import types
from collections import deque
from pathlib import Path
from typing import Any, BinaryIO, NoReturn

from file_organizer.plugins.errors import PluginError, PluginLoadError
from file_organizer.plugins.ipc import (
    PluginCall,
    PluginResult,
    decode_result,
    encode_call,
)
from file_organizer.plugins.security import PluginSecurityPolicy

logger = logging.getLogger(__name__)

# First line the worker writes to stdout, before entering the IPC loop.
# ``start()`` blocks until it arrives, so per-call timeouts in ``call()``
# measure call latency — never the child's multi-second (and, under
# pytest-cov subprocess instrumentation, several-times-slower) startup.
_READY_LINE = b'{"ready": true}\n'
_STDERR_BUFFER_LIMIT = 64 * 1024
_STDERR_READ_SIZE = 4096


def _build_worker_bootstrap(plugin_path: str, policy_dict: dict[str, Any]) -> str:
    """Build child startup code that reserves stdout before package imports.

    Importing this package can itself load noisy dependencies, so redirecting
    inside ``_worker`` is too late. Keep fd 1 on stderr for the child's entire
    lifetime; only the saved descriptor can write readiness and IPC responses.
    This also catches buffered native output flushed after plugin startup.

    Args:
        plugin_path: Path to the plugin module.
        policy_dict: JSON-safe security policy passed to the worker.

    Returns:
        Python source for ``sys.executable -c``.
    """
    # repr protects paths and policy strings from being interpreted as code.
    # The context manager closes the saved descriptor even if imports fail.
    return (
        "import os, sys, json\n"
        "with os.fdopen(os.dup(1), 'wb') as ipc_stdout:\n"
        "    os.dup2(2, 1)\n"
        "    sys.stdout = sys.stderr\n"
        "    from file_organizer.plugins.executor import _worker\n"
        f"    _worker({plugin_path!r}, json.loads({json.dumps(policy_dict)!r}), ipc_stdout)\n"
    )


# ---------------------------------------------------------------------------
# Worker entrypoint (runs inside the child process)
# ---------------------------------------------------------------------------


def _worker(
    plugin_path: str, policy_dict: dict[str, Any], stdout_bin: BinaryIO
) -> None:  # pragma: no cover
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
        stdout_bin: Dedicated IPC stream saved by the bootstrap before it
            redirects stdout. The bootstrap owns and closes this stream.
    """
    import importlib.util
    import sys
    from pathlib import Path

    stdin_bin = sys.stdin.buffer
    # ------------------------------------------------------------------
    # 1. Apply resource limits (best-effort; Linux/macOS only)
    # ------------------------------------------------------------------
    try:
        import resource

        # Restrict open file descriptors to a safe minimum
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        # Limit CPU time to 60 seconds per child lifetime
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    except (ImportError, ValueError):
        pass  # Windows or kernel limit already tighter — silently skip
    except Exception:
        logger.debug("Failed to apply plugin worker resource limits", exc_info=True)

    # --------------------------------------------------------------
    # 2. Dynamically load the plugin module
    # --------------------------------------------------------------
    path = Path(plugin_path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"Cannot create module spec for plugin: {plugin_path}\n")
        sys.exit(1)

    loader = spec.loader
    module = types.ModuleType(path.stem)
    try:
        loader.exec_module(module)
    except Exception as exc:
        sys.stderr.write(f"Error loading plugin module '{plugin_path}': {exc}\n")
        sys.exit(1)

    # --------------------------------------------------------------
    # 3. Find and instantiate the first concrete Plugin subclass
    # --------------------------------------------------------------
    from file_organizer.plugins.base import Plugin

    plugin_instance: Plugin | None = None
    for _attr_name in dir(module):
        obj = getattr(module, _attr_name)
        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
            try:
                plugin_instance = obj()
            except Exception as exc:
                sys.stderr.write(f"Error instantiating plugin class '{_attr_name}': {exc}\n")
                sys.exit(1)
            break

    if plugin_instance is None:
        sys.stderr.write(f"No Plugin subclass found in: {plugin_path}\n")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. IPC loop — read PluginCall from stdin, write PluginResult to stdout
    # ------------------------------------------------------------------
    from file_organizer.plugins.ipc import PluginResult, decode_call, encode_result

    # Readiness handshake — MUST be the first bytes on stdout. The parent's
    # start() blocks on this line; see _READY_LINE.
    stdout_bin.write(_READY_LINE)
    stdout_bin.flush()

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
            Defaults to deny-by-default when not supplied.

    Raises:
        PluginLoadError: If :meth:`start` fails to spawn the worker.
        PluginError: If :meth:`call` receives an error result from the worker.
    """

    def __init__(
        self,
        plugin_path: Path | str,
        plugin_name: str | None = None,
        policy: PluginSecurityPolicy | None = None,
        startup_timeout: float = 30.0,
    ) -> None:
        """Set up the executor for the plugin at the given path.

        Args:
            plugin_path: Path (or path string) to the plugin ``.py`` file.
            plugin_name: Human-readable name for error messages; defaults to
                the plugin file's stem.
            policy: Security policy forwarded to the worker; defaults to
                the default :class:`PluginSecurityPolicy`.
            startup_timeout: Maximum seconds :meth:`start` waits for the
                worker's readiness line. Generous by default because the
                child pays the full package-import cost before it can
                answer, and instrumented runs (e.g. subprocess coverage)
                multiply that cost.
        """
        self._plugin_path = Path(plugin_path)
        self._plugin_name = plugin_name or self._plugin_path.stem
        self._policy = policy or PluginSecurityPolicy()
        self._startup_timeout = startup_timeout
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_buffer: deque[bytes] = deque()
        self._stderr_buffer_size = 0
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

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

        bootstrap = _build_worker_bootstrap(str(self._plugin_path), policy_dict)

        # The child must execute the same file_organizer tree as this
        # process. A bare ``sys.executable -c`` child resolves imports
        # through the interpreter environment, where a stale editable
        # install can silently substitute another checkout's code; putting
        # this package's own root first makes parent and child agree.
        package_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{package_root}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else str(package_root)
        )

        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-c", bootstrap],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            self._start_stderr_drainer()
        except OSError as exc:
            raise PluginLoadError(
                f"Failed to spawn worker for plugin '{self._plugin_name}': {exc}"
            ) from exc

        # Block until the worker signals readiness (see _READY_LINE). This
        # also converts a child that crashes during startup — e.g. a plugin
        # that raises at import — into an immediate PluginLoadError carrying
        # the child's stderr, instead of an opaque pipe error at first call.
        first_line = b""
        try:
            first_line = self._readline_with_timeout(timeout=self._startup_timeout)
        except PluginError as exc:
            self._abort_startup(
                f"did not signal readiness within {self._startup_timeout:.1f}s ({exc})"
            )
        if first_line.strip() != _READY_LINE.strip():
            self._abort_startup(
                "exited during startup without signalling readiness"
                if not first_line
                else f"sent unexpected first stdout line {first_line!r}"
            )

    def _start_stderr_drainer(self) -> None:
        """Drain worker stderr continuously into a bounded diagnostic buffer.

        The worker is allowed to write diagnostics independently of the IPC
        protocol. Reading stderr only after startup failure leaves the OS pipe
        able to fill, which can block the worker before it writes its next IPC
        response. The bounded buffer retains recent diagnostics without
        allowing an untrusted plugin to consume host memory indefinitely.
        """
        proc = self._proc
        if proc is None or proc.stderr is None:
            return

        stderr = proc.stderr

        def drain() -> None:
            """Copy stderr chunks until the worker closes its pipe."""
            nonlocal stderr
            try:
                while True:
                    chunk = stderr.read(_STDERR_READ_SIZE)
                    if not chunk:
                        return
                    if not isinstance(chunk, bytes):
                        return
                    with self._stderr_lock:
                        self._stderr_buffer.append(chunk)
                        self._stderr_buffer_size += len(chunk)
                        while self._stderr_buffer_size > _STDERR_BUFFER_LIMIT:
                            removed = self._stderr_buffer.popleft()
                            self._stderr_buffer_size -= len(removed)
            except (OSError, ValueError):
                logger.debug("Failed while draining plugin worker stderr", exc_info=True)

        self._stderr_thread = threading.Thread(
            target=drain,
            name=f"plugin-stderr-{self._plugin_name}",
            daemon=True,
        )
        self._stderr_thread.start()

    def _stderr_snapshot(self) -> str:
        """Return the recent worker diagnostics captured by the drainer."""
        with self._stderr_lock:
            return b"".join(self._stderr_buffer).decode(errors="replace")

    def _abort_startup(self, detail: str) -> NoReturn:
        """Kill a worker that failed its readiness handshake and raise.

        Kills the child before taking the final snapshot. A background
        drainer has already consumed stderr while the worker was running.

        Args:
            detail: Failure description embedded in the raised error.

        Raises:
            PluginLoadError: Always; carries ``detail`` and the child's
                stderr (best effort).
        """
        proc = self._proc
        stderr_output = ""
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except OSError:
                logger.debug("Failed to reap worker during startup abort", exc_info=True)
            except subprocess.TimeoutExpired:
                logger.debug("Worker did not exit after kill during startup abort")
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=1)
            stderr_output = self._stderr_snapshot()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        logger.debug("Failed to close worker pipe during startup abort")
        self._proc = None
        raise PluginLoadError(
            f"Worker for plugin '{self._plugin_name}' {detail}. Stderr: {stderr_output!r}"
        )

    def stop(self) -> None:
        """Terminate the worker subprocess and release resources.

        This method is idempotent; calling it on an already-stopped executor
        is a no-op.
        """
        proc = self._proc
        if proc is None:
            return
        try:
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except Exception:
                        logger.debug("Failed to close plugin worker pipe cleanly", exc_info=True)
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        finally:
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=1)
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

    def _readline_with_timeout(self, timeout: float = 10.0) -> bytes:
        """Read a line from stdout with a timeout.

        Args:
            timeout: Maximum seconds to wait for a line (default: 10.0).

        Returns:
            The line read from stdout (including newline).

        Raises:
            PluginError: If timeout occurs or stdout is not available.
        """
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise PluginError("Worker process is not running.")

        stdout = proc.stdout

        if sys.platform == "win32":
            # select() doesn't work with pipes on Windows; use a daemon
            # thread to perform the blocking read and a queue to enforce
            # the timeout.
            result_queue: queue.Queue[bytes | Exception] = queue.Queue()

            def _reader() -> None:
                """Read one line from subprocess stdout, placing result or exception in queue."""
                try:
                    result_queue.put(stdout.readline())
                except Exception as exc:
                    result_queue.put(exc)

            thread = threading.Thread(target=_reader, daemon=True)
            thread.start()
            try:
                value = result_queue.get(timeout=timeout)
            except queue.Empty:
                # The daemon reader thread is still blocked on readline().
                # It will be cleaned up when stop() kills the subprocess.
                raise PluginError(
                    f"Worker process did not respond within {timeout}s (possible hang or timeout)."
                ) from None
            if isinstance(value, Exception):
                raise PluginError(f"Failed to read from worker: {value}") from value
            return value
        else:
            # On Unix, use select.select() for proper timeout handling
            ready, _, _ = select.select([stdout], [], [], timeout)
            if not ready:
                raise PluginError(
                    f"Worker process did not respond within {timeout}s (possible hang or timeout)."
                )
            return stdout.readline()

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
        proc = self._proc
        if proc is None:
            raise RuntimeError(
                f"PluginExecutor for '{self._plugin_name}' is not started. "
                "Call start() or use it as a context manager."
            )
        stdin = proc.stdin
        stdout = proc.stdout
        if stdin is None or stdout is None:
            raise PluginError(f"Worker pipes for '{self._plugin_name}' are unexpectedly closed.")

        call_msg = PluginCall(method=method, args=list(args), kwargs=kwargs)
        try:
            stdin.write(encode_call(call_msg))
            stdin.flush()
        except BrokenPipeError as exc:
            raise PluginError(
                f"Worker for '{self._plugin_name}' died before receiving call '{method}'."
            ) from exc

        raw = self._readline_with_timeout(timeout=30.0)
        if not raw:
            stderr_output = self._stderr_snapshot()
            raise PluginError(
                f"Worker for '{self._plugin_name}' closed stdout unexpectedly "
                f"(method='{method}'). Stderr: {stderr_output!r}"
            )

        try:
            result: PluginResult = decode_result(raw)
        except ValueError as exc:
            raise PluginError(
                f"Corrupt IPC response from '{self._plugin_name}' (method='{method}'): {exc}"
            ) from exc

        if not result.success:
            error_msg = (
                f"Plugin '{self._plugin_name}' raised an error in '{method}': {result.error}"
            )
            # on_load failures surface as PluginLoadError so callers can
            # distinguish initialisation errors from runtime errors.
            if method == "on_load":
                raise PluginLoadError(error_msg)
            raise PluginError(error_msg)

        return result.return_value
