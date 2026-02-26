"""Unit tests for browser extension integration helpers."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo

import pytest

from file_organizer.integrations import BrowserExtensionManager

pytestmark = pytest.mark.ci


def test_issue_token_prunes_expired_records(monkeypatch: pytest.MonkeyPatch) -> None:
    base = datetime(2026, 2, 9, 12, 0, 0, tzinfo=UTC)
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
    base = datetime(2026, 2, 9, 12, 0, 0, tzinfo=UTC)
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


def test_get_config_returns_bootstrap_dict() -> None:
    """get_config should return allowed_origins and token_ttl_seconds."""
    manager = BrowserExtensionManager(
        allowed_origins=["https://example.com", "https://other.com"],
        token_ttl_seconds=7200,
    )
    config = manager.get_config()
    assert config["allowed_origins"] == ["https://example.com", "https://other.com"]
    assert config["token_ttl_seconds"] == 7200


def test_get_config_deduplicates_origins() -> None:
    """Duplicate allowed_origins should be deduplicated in the constructor."""
    manager = BrowserExtensionManager(
        allowed_origins=["https://a.com", "https://a.com", "https://b.com"],
    )
    config = manager.get_config()
    assert config["allowed_origins"] == ["https://a.com", "https://b.com"]


def test_verify_token_valid() -> None:
    """verify_token should return True for a valid, non-expired token."""
    manager = BrowserExtensionManager(
        allowed_origins=["https://example.com"],
        token_ttl_seconds=3600,
    )
    record = manager.issue_token("ext-test")
    assert manager.verify_token(record.token) is True


def test_verify_token_invalid() -> None:
    """verify_token should return False for an unknown token."""
    manager = BrowserExtensionManager(
        allowed_origins=["https://example.com"],
    )
    assert manager.verify_token("nonexistent-token") is False


def test_issue_token_record_fields() -> None:
    """Issued token record should have correct fields."""
    manager = BrowserExtensionManager(
        allowed_origins=["https://example.com"],
        token_ttl_seconds=600,
    )
    record = manager.issue_token("my-ext")
    assert record.extension_id == "my-ext"
    assert len(record.token) > 0
    assert record.expires_at > record.created_at
