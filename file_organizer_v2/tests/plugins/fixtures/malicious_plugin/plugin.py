"""Malicious plugin fixture used to verify sandbox bypass prevention.

This plugin intentionally attempts forbidden operations inside ``on_load()``.
The sandbox executor (Stream A) is expected to detect these attempts and raise
:class:`~file_organizer.plugins.base.PluginPermissionError` or
:class:`~file_organizer.plugins.base.PluginLoadError` before any damage is done.

.. warning::
    **This file exists solely as a negative test fixture.**
    Do NOT load it outside of the test suite — it is designed to
    demonstrate an attack pattern, not to be used as a real plugin.

Issue reference: #338 — Security: Plugin Sandbox Bypass Risk
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from file_organizer.plugins.base import Plugin


class MaliciousPlugin(Plugin):
    """A plugin that attempts to escape the sandbox via ``os.system``.

    The ``on_load`` method calls ``os.system("echo bypass")`` which is the
    canonical bypass vector identified in Issue #338.  A correctly implemented
    sandbox must intercept this call and raise an appropriate exception
    *before* the shell command executes.
    """

    name = "malicious-os-system"
    version = "0.0.1"
    allowed_paths: list[Path] = []

    def get_metadata(self) -> Any:  # type: ignore[override]
        """Return minimal plugin metadata for testing purposes."""
        from file_organizer.plugins.base import PluginMetadata
        return PluginMetadata(
            name=self.name,
            version=self.version,
            author="test",
            description="Malicious test fixture",
        )

    def on_load(self) -> None:
        """Attempt sandbox bypass via os.system — MUST be blocked by executor.

        Raises:
            PluginPermissionError: Expected — the sandbox must raise this.
            PluginLoadError: Acceptable alternative from the sandbox layer.
        """
        # This is the exact bypass pattern from Issue #338.
        # A sandbox that merely marks operations as "advisory" would allow
        # this to execute, printing "bypass" to the terminal.
        os.system("echo bypass")  # noqa: S605 — intentional test attack

    def on_enable(self) -> None:
        """No-op enable handler."""

    def on_disable(self) -> None:
        """No-op disable handler."""

    def on_unload(self) -> None:
        """No-op unload handler."""

    def on_file(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
        """No-op for file processing (bypass happens in on_load)."""
        return None
