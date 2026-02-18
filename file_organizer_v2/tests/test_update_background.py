"""Tests for background update checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from file_organizer.config.schema import AppConfig, UpdateSettings
from file_organizer.updater.background import maybe_check_for_updates
from file_organizer.updater.manager import UpdateStatus
from file_organizer.updater.state import UpdateState, UpdateStateStore


class DummyStore(UpdateStateStore):
    def __init__(self, state: UpdateState) -> None:
        self._state = state
        self.recorded: tuple[str, datetime | None] | None = None

    def load(self) -> UpdateState:  # type: ignore[override]
        return self._state

    def record_check(self, version: str, *, now: datetime | None = None) -> UpdateState:  # type: ignore[override]
        self.recorded = (version, now)
        return UpdateState(
            last_checked=(now or datetime.now(timezone.utc)).isoformat(),
            last_version=version,
        )


def _stub_config(updates: UpdateSettings) -> AppConfig:
    return AppConfig(updates=updates)


def test_skips_when_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FO_DISABLE_UPDATE_CHECK", "1")
    status = maybe_check_for_updates()
    assert status is None


def test_skips_when_interval_not_due(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    now = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
    state = UpdateState(last_checked=(now - timedelta(hours=1)).isoformat())
    store = DummyStore(state)

    monkeypatch.setattr(
        "file_organizer.updater.background.ConfigManager.load",
        lambda *_args, **_kwargs: _stub_config(UpdateSettings(interval_hours=24)),
    )

    status = maybe_check_for_updates(state_store=store, now=now)
    assert status is None
    assert store.recorded is None


def test_runs_when_due_and_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    now = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
    state = UpdateState(last_checked=(now - timedelta(hours=48)).isoformat())
    store = DummyStore(state)

    monkeypatch.setattr(
        "file_organizer.updater.background.ConfigManager.load",
        lambda *_args, **_kwargs: _stub_config(
            UpdateSettings(interval_hours=24, include_prereleases=True, repo="owner/repo")
        ),
    )

    captured: dict[str, object] = {}

    class DummyManager:
        def __init__(self, repo: str, include_prereleases: bool) -> None:
            captured["repo"] = repo
            captured["include_prereleases"] = include_prereleases

        def check(self) -> UpdateStatus:
            return UpdateStatus(
                available=True,
                current_version="1.0.0",
                latest_version="2.0.0",
            )

    monkeypatch.setattr("file_organizer.updater.background.UpdateManager", DummyManager)

    status = maybe_check_for_updates(state_store=store, now=now)
    assert status is not None
    assert status.available is True
    assert store.recorded == ("2.0.0", now)
    assert captured["repo"] == "owner/repo"
    assert captured["include_prereleases"] is True
