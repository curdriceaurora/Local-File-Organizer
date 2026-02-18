"""JSON-serialisable IPC message schema for plugin subprocess communication.

This module defines the wire protocol used between the host process and
plugin worker subprocesses.  All messages are newline-delimited JSON
(NDJSON) so they can be safely written to and read from ``subprocess.Popen``
pipes without length-prefixing.

Only ``json`` is used — never ``pickle`` — to prevent code-execution attacks
from untrusted plugin payloads.

Wire format examples::

    # host → worker (PluginCall)
    {"method": "on_file", "args": ["/tmp/foo.txt"], "kwargs": {}}

    # worker → host (PluginResult — success)
    {"success": true, "return_value": null, "error": null}

    # worker → host (PluginResult — error)
    {"success": false, "return_value": null, "error": "PluginPermissionError: ..."}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginCall:
    """A request from the host to invoke a method on the plugin instance.

    Attributes:
        method: Name of the method to call on the plugin object.
        args: Positional arguments, all JSON-serialisable.
        kwargs: Keyword arguments, all JSON-serialisable.
    """

    method: str
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginResult:
    """The response from the plugin worker subprocess.

    Attributes:
        success: ``True`` when the call completed without error.
        return_value: The JSON-serialisable return value of the method, or
            ``None`` when the call raised an exception.
        error: Human-readable error message when ``success`` is ``False``,
            otherwise ``None``.
    """

    success: bool
    return_value: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def encode_call(call: PluginCall) -> bytes:
    """Serialise a :class:`PluginCall` to newline-terminated JSON bytes.

    Args:
        call: The call message to encode.

    Returns:
        UTF-8 encoded JSON followed by a newline character.
    """
    payload = {
        "method": call.method,
        "args": call.args,
        "kwargs": call.kwargs,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


def decode_call(data: bytes) -> PluginCall:
    """Deserialise a :class:`PluginCall` from raw bytes.

    Args:
        data: Raw bytes produced by :func:`encode_call`.

    Returns:
        The reconstructed :class:`PluginCall` instance.

    Raises:
        ValueError: If ``data`` is not valid JSON or is missing required keys.
    """
    try:
        payload = json.loads(data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid PluginCall bytes: {exc}") from exc

    try:
        return PluginCall(
            method=payload["method"],
            args=list(payload.get("args", [])),
            kwargs=dict(payload.get("kwargs", {})),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed PluginCall payload: {exc}") from exc


def encode_result(result: PluginResult) -> bytes:
    """Serialise a :class:`PluginResult` to newline-terminated JSON bytes.

    Args:
        result: The result message to encode.

    Returns:
        UTF-8 encoded JSON followed by a newline character.
    """
    payload = {
        "success": result.success,
        "return_value": result.return_value,
        "error": result.error,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


def decode_result(data: bytes) -> PluginResult:
    """Deserialise a :class:`PluginResult` from raw bytes.

    Args:
        data: Raw bytes produced by :func:`encode_result`.

    Returns:
        The reconstructed :class:`PluginResult` instance.

    Raises:
        ValueError: If ``data`` is not valid JSON or is missing required keys.
    """
    try:
        payload = json.loads(data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid PluginResult bytes: {exc}") from exc

    try:
        return PluginResult(
            success=bool(payload["success"]),
            return_value=payload.get("return_value"),
            error=payload.get("error"),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed PluginResult payload: {exc}") from exc
