"""Update state persistence for throttling background checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from file_organizer.config.manager import DEFAULT_CONFIG_DIR


@dataclass
class UpdateState:
    """Persisted update check state."""

    last_checked: str = ""
    last_version: str = ""

    def last_checked_at(self) -> datetime | None:
        """Return the last check timestamp as a datetime, if available."""
        if not self.last_checked:
            return None
        try:
            return datetime.fromisoformat(self.last_checked.replace("Z", "+00:00"))
        except ValueError:
            return None

    def due(self, interval_hours: int, *, now: datetime | None = None) -> bool:
        """Return True if an update check is due based on the interval."""
        if interval_hours <= 0:
            return True
        last = self.last_checked_at()
        if last is None:
            return True
        now = now or datetime.now(UTC)
        return now - last >= timedelta(hours=interval_hours)


class UpdateStateStore:
    """Read/write update state to disk."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        """Create a state store for a given path (defaults to config dir)."""
        self._state_path = (
            Path(state_path) if state_path else DEFAULT_CONFIG_DIR / "update_state.json"
        )

    @property
    def state_path(self) -> Path:
        """Return the underlying state file path."""
        return self._state_path

    def load(self) -> UpdateState:
        """Load update state from disk, returning defaults on failure."""
        if not self._state_path.exists():
            return UpdateState()
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return UpdateState()
        if not isinstance(data, dict):
            return UpdateState()
        return UpdateState(
            last_checked=str(data.get("last_checked", "")),
            last_version=str(data.get("last_version", "")),
        )

    def save(self, state: UpdateState) -> None:
        """Persist update state to disk."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_checked": state.last_checked,
            "last_version": state.last_version,
        }
        self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_check(self, version: str, *, now: datetime | None = None) -> UpdateState:
        """Record a successful check and return the updated state."""
        timestamp = (now or datetime.now(UTC)).isoformat()
        state = UpdateState(last_checked=timestamp, last_version=version)
        self.save(state)
        return state
