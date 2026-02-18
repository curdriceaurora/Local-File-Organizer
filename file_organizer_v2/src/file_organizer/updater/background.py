"""Background update checks respecting user preferences."""

from __future__ import annotations

import os
from datetime import datetime

from file_organizer.config import ConfigManager
from file_organizer.updater.manager import UpdateManager, UpdateStatus
from file_organizer.updater.state import UpdateStateStore


def maybe_check_for_updates(
    *,
    profile: str = "default",
    state_store: UpdateStateStore | None = None,
    now: datetime | None = None,
) -> UpdateStatus | None:
    """Check for updates if user preferences allow it.

    Returns:
        UpdateStatus if a check was performed, otherwise None.
    """
    if os.environ.get("FO_DISABLE_UPDATE_CHECK") or os.environ.get("PYTEST_CURRENT_TEST"):
        return None

    cfg = ConfigManager().load(profile=profile)
    policy = cfg.updates
    if not policy.check_on_startup:
        return None

    store = state_store or UpdateStateStore()
    state = store.load()
    if not state.due(policy.interval_hours, now=now):
        return None

    mgr = UpdateManager(repo=policy.repo, include_prereleases=policy.include_prereleases)
    status = mgr.check()
    store.record_check(
        status.latest_version if status.available else status.current_version,
        now=now,
    )
    return status
