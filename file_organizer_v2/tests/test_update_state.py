"""Tests for update state tracking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from file_organizer.updater.state import UpdateState, UpdateStateStore


def test_update_state_due_when_missing_timestamp() -> None:
    state = UpdateState()
    now = datetime(2026, 2, 9, tzinfo=timezone.utc)
    assert state.due(24, now=now) is True


def test_update_state_due_when_interval_elapsed() -> None:
    now = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=25)
    state = UpdateState(last_checked=last.isoformat())
    assert state.due(24, now=now) is True


def test_update_state_not_due_when_interval_not_elapsed() -> None:
    now = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)
    state = UpdateState(last_checked=last.isoformat())
    assert state.due(24, now=now) is False


def test_state_store_round_trip(tmp_path) -> None:
    store = UpdateStateStore(state_path=tmp_path / "state.json")
    state = UpdateState(
        last_checked="2026-02-09T12:00:00+00:00",
        last_version="2.0.0-alpha.1",
    )
    store.save(state)
    loaded = store.load()
    assert loaded.last_checked == state.last_checked
    assert loaded.last_version == state.last_version


def test_state_store_record_check(tmp_path) -> None:
    store = UpdateStateStore(state_path=tmp_path / "state.json")
    now = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
    state = store.record_check("2.0.1", now=now)
    assert state.last_version == "2.0.1"
    assert state.last_checked.startswith("2026-02-09T12:00:00")
