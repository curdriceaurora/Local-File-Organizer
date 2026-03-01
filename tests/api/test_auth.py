"""Tests for file_organizer.api.auth module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from file_organizer.api.auth import (
    TokenBundle,
    TokenError,
    create_token_bundle,
    decode_token,
    hash_password,
    is_access_token,
    is_refresh_token,
    validate_password,
    verify_password,
)
from file_organizer.api.config import ApiSettings, load_settings


@pytest.fixture()
def settings() -> ApiSettings:
    """Return default ApiSettings for testing."""
    return load_settings()


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------


class TestVerifyPassword:
    """Tests for verify_password."""

    def test_correct_password(self) -> None:
        hashed = hash_password("my-secret-pass")
        assert verify_password("my-secret-pass", hashed) is True

    def test_wrong_password(self) -> None:
        hashed = hash_password("my-secret-pass")
        assert verify_password("wrong-pass", hashed) is False

    def test_empty_password_does_not_match(self) -> None:
        hashed = hash_password("non-empty")
        assert verify_password("", hashed) is False


# ---------------------------------------------------------------------------
# hash_password
# ---------------------------------------------------------------------------


class TestHashPassword:
    """Tests for hash_password."""

    def test_returns_bcrypt_hash(self) -> None:
        hashed = hash_password("test-password")
        assert hashed.startswith("$2")

    def test_different_salt_each_call(self) -> None:
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2

    def test_roundtrip_with_verify(self) -> None:
        password = "roundtrip-test-1234!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True


# ---------------------------------------------------------------------------
# validate_password
# ---------------------------------------------------------------------------


class TestValidatePassword:
    """Tests for validate_password."""

    def test_too_short(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("Ab1!", settings)
        assert ok is False
        assert "at least" in msg

    def test_missing_letter(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("123456789012!", settings)
        assert ok is False
        assert "letter" in msg

    def test_missing_number(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("Abcdefghijkl!", settings)
        assert ok is False
        assert "number" in msg

    def test_missing_uppercase(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("abcdefghijk1!", settings)
        assert ok is False
        assert "uppercase" in msg

    def test_missing_special(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("Abcdefghijk12", settings)
        assert ok is False
        assert "special" in msg

    def test_common_password(self, settings: ApiSettings) -> None:
        # "password" is in common list; pad to meet length requirement
        s = settings.model_copy(update={"auth_password_min_length": 4})
        s = s.model_copy(
            update={
                "auth_password_require_number": False,
                "auth_password_require_special": False,
                "auth_password_require_uppercase": False,
            }
        )
        ok, msg = validate_password("password", s)
        assert ok is False
        assert "common" in msg

    def test_all_rules_disabled(self) -> None:
        s = ApiSettings(
            auth_password_min_length=1,
            auth_password_require_number=False,
            auth_password_require_letter=False,
            auth_password_require_special=False,
            auth_password_require_uppercase=False,
        )
        ok, msg = validate_password("x", s)
        assert ok is True
        assert msg == ""

    def test_valid_password(self, settings: ApiSettings) -> None:
        ok, msg = validate_password("StrongP@ss1234", settings)
        assert ok is True
        assert msg == ""


# ---------------------------------------------------------------------------
# create_token_bundle
# ---------------------------------------------------------------------------


class TestCreateTokenBundle:
    """Tests for create_token_bundle."""

    def test_returns_token_bundle(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        assert isinstance(bundle, TokenBundle)

    def test_access_and_refresh_tokens_differ(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        assert bundle.access_token != bundle.refresh_token

    def test_jtis_are_unique(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        assert bundle.access_jti != bundle.refresh_jti

    def test_access_token_type(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        payload = decode_token(bundle.access_token, settings)
        assert is_access_token(payload) is True
        assert is_refresh_token(payload) is False

    def test_refresh_token_type(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        payload = decode_token(bundle.refresh_token, settings)
        assert is_refresh_token(payload) is True
        assert is_access_token(payload) is False

    def test_expiry_times_reasonable(self, settings: ApiSettings) -> None:
        before = datetime.now(UTC)
        bundle = create_token_bundle("uid-1", "alice", settings)
        after = datetime.now(UTC)

        access_delta = timedelta(minutes=settings.auth_access_token_minutes)
        assert before + access_delta <= bundle.access_expires_at <= after + access_delta + timedelta(seconds=2)

        refresh_delta = timedelta(days=settings.auth_refresh_token_days)
        assert before + refresh_delta <= bundle.refresh_expires_at <= after + refresh_delta + timedelta(seconds=2)

    def test_payload_contains_subject(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        payload = decode_token(bundle.access_token, settings)
        assert payload["sub"] == "alice"
        assert payload["user_id"] == "uid-1"

    def test_successive_bundles_have_different_jtis(self, settings: ApiSettings) -> None:
        b1 = create_token_bundle("uid-1", "alice", settings)
        b2 = create_token_bundle("uid-1", "alice", settings)
        assert b1.access_jti != b2.access_jti
        assert b1.refresh_jti != b2.refresh_jti


# ---------------------------------------------------------------------------
# decode_token
# ---------------------------------------------------------------------------


class TestDecodeToken:
    """Tests for decode_token."""

    def test_valid_token(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        payload = decode_token(bundle.access_token, settings)
        assert payload["sub"] == "alice"

    def test_invalid_token_string(self, settings: ApiSettings) -> None:
        with pytest.raises(TokenError):
            decode_token("not-a-jwt", settings)

    def test_expired_token(self, settings: ApiSettings) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        with patch("file_organizer.api.auth._now", return_value=past):
            bundle = create_token_bundle("uid-1", "alice", settings)
        with pytest.raises(TokenError):
            decode_token(bundle.access_token, settings)

    def test_tampered_token(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        tampered = bundle.access_token[:-4] + "XXXX"
        with pytest.raises(TokenError):
            decode_token(tampered, settings)

    def test_wrong_secret(self, settings: ApiSettings) -> None:
        bundle = create_token_bundle("uid-1", "alice", settings)
        other_settings = settings.model_copy(
            update={"auth_jwt_secret": SecretStr("different-secret")}
        )
        with pytest.raises(TokenError):
            decode_token(bundle.access_token, other_settings)


# ---------------------------------------------------------------------------
# is_access_token / is_refresh_token
# ---------------------------------------------------------------------------


class TestTokenTypeChecks:
    """Tests for is_access_token and is_refresh_token."""

    def test_access_payload(self) -> None:
        payload: dict[str, Any] = {"type": "access"}
        assert is_access_token(payload) is True
        assert is_refresh_token(payload) is False

    def test_refresh_payload(self) -> None:
        payload: dict[str, Any] = {"type": "refresh"}
        assert is_access_token(payload) is False
        assert is_refresh_token(payload) is True

    def test_empty_payload(self) -> None:
        payload: dict[str, Any] = {}
        assert is_access_token(payload) is False
        assert is_refresh_token(payload) is False

    def test_unknown_type(self) -> None:
        payload: dict[str, Any] = {"type": "other"}
        assert is_access_token(payload) is False
        assert is_refresh_token(payload) is False


# ---------------------------------------------------------------------------
# TokenError
# ---------------------------------------------------------------------------


class TestTokenError:
    """Tests for TokenError exception."""

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(TokenError, match="bad token"):
            raise TokenError("bad token")

    def test_is_exception(self) -> None:
        assert issubclass(TokenError, Exception)
