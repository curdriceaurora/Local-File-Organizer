"""Shared journal-path resolution for the undo subsystem.

F7/F8: both :class:`RollbackExecutor` and :class:`OperationValidator`
need to reach the same ``durable_move.journal`` path. The resolution
is deliberately *lazy* so tests setting ``XDG_STATE_HOME`` per-test
(via the integration conftest's ``_isolate_user_env`` fixture) pick
up the isolated path instead of a module-import-time snapshot of
the real user state dir.

Do not re-export :data:`DEFAULT_JOURNAL_PATH` as a module-level
constant — evaluating it at import would defeat the whole point.
Always call :func:`default_journal_path`.
"""

from __future__ import annotations

from pathlib import Path


def default_journal_path() -> Path:
    """Return the path to the shared ``durable_move.journal``.

    Lazy: resolves ``get_state_dir()`` at each call so tests that
    monkeypatch ``XDG_STATE_HOME`` after import still see an isolated
    location.
    """
    from file_organizer.config.path_manager import get_state_dir

    return get_state_dir() / "undo" / "durable_move.journal"
