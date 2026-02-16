"""Unit tests for browser extension integration helpers."""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo

import pytest

from file_organizer.integrations import BrowserExtensionManager

pytestmark = pytest.mark.ci


def test_issue_token_prunes_expired_records(monkeypatch: pytest.MonkeyPatch) -> None:
    base = datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc)
    ticks = iter([base, base.replace(second=2)])

    class _FakeDateTime:
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            value = next(ticks)
            if tz is None:
                return value
            return value.astimezone(tz)

    monkeypatch.setattr("file_organizer.integrations.browser.datetime", _FakeDateTime)

    manager = BrowserExtensionManager(allowed_origins=["https://example.com"], token_ttl_seconds=1)
    first = manager.issue_token("ext-a")
    second = manager.issue_token("ext-b")

    assert first.token not in manager._tokens
    assert second.token in manager._tokens


def test_verify_token_prunes_expired_records(monkeypatch: pytest.MonkeyPatch) -> None:
    base = datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc)
    ticks = iter([base, base.replace(second=2)])

    class _FakeDateTime:
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            value = next(ticks)
            if tz is None:
                return value
            return value.astimezone(tz)

    monkeypatch.setattr("file_organizer.integrations.browser.datetime", _FakeDateTime)

    manager = BrowserExtensionManager(allowed_origins=["https://example.com"], token_ttl_seconds=1)
    token = manager.issue_token("ext-a").token
    assert token in manager._tokens

    assert manager.verify_token("missing-token") is False
    assert token not in manager._tokens
