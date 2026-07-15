"""Shared TUI status-bar helpers."""

from __future__ import annotations

import logging
from typing import Any, cast

logger = logging.getLogger(__name__)


class StatusMixin:
    """Mixin for views that update the app-level status bar."""

    def _set_status(self, message: str) -> None:
        """Update the app status bar if one is mounted."""
        try:
            from file_organizer.tui.app import StatusBar

            app = cast(Any, self).app
            app.query_one(StatusBar).set_status(message)
        except Exception:
            logger.debug("Status bar unavailable for %s.", type(self).__name__, exc_info=True)
