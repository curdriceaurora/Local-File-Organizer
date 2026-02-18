"""Plugin hook registry."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable

from file_organizer.plugins.errors import HookExecutionError

HookCallback = Callable[..., Any]


@dataclass
class HookExecutionResult:
    """Result of one callback invocation."""

    callback_name: str
    value: Any = None
    error: Exception | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


class HookRegistry:
    """Thread-safe hook registration and trigger orchestration."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookCallback]] = {}
        self._lock = RLock()

    def register_hook(self, hook_name: str, callback: HookCallback) -> None:
        """Register callback for a hook."""
        with self._lock:
            callbacks = self._hooks.setdefault(hook_name, [])
            if callback not in callbacks:
                callbacks.append(callback)

    def unregister_hook(self, hook_name: str, callback: HookCallback) -> None:
        """Unregister callback from a hook."""
        with self._lock:
            callbacks = self._hooks.get(hook_name)
            if not callbacks:
                return
            try:
                callbacks.remove(callback)
            except ValueError:
                return
            if not callbacks:
                self._hooks.pop(hook_name, None)

    def trigger_hook(
        self,
        hook_name: str,
        *args: Any,
        stop_on_error: bool = False,
        **kwargs: Any,
    ) -> list[HookExecutionResult]:
        """Invoke all callbacks registered for a hook."""
        with self._lock:
            callbacks = list(self._hooks.get(hook_name, []))
        results: list[HookExecutionResult] = []
        for callback in callbacks:
            callback_name = getattr(callback, "__name__", repr(callback))
            try:
                value = callback(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - behavior verified by tests
                result = HookExecutionResult(callback_name=callback_name, error=exc)
                results.append(result)
                if stop_on_error:
                    raise HookExecutionError(
                        f"Hook '{hook_name}' callback '{callback_name}' failed."
                    ) from exc
            else:
                results.append(HookExecutionResult(callback_name=callback_name, value=value))
        return results

    def list_hooks(self) -> dict[str, int]:
        """Return callback count per hook."""
        with self._lock:
            return {hook_name: len(callbacks) for hook_name, callbacks in self._hooks.items()}
