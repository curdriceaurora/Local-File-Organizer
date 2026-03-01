"""Tests for authentication helpers (auth.py)."""

from __future__ import annotations

import base64
import json as _json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from jose import jwt

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
from file_organizer.api.test_utils import build_test_settings


def _settings(tmp_path, **overrides):
    return build_test_settings(tmp_path, auth_overrides=overrides)


@pytest.mark.unit
class TestPasswordHelpers:
    """Tests for hash_password and verify_password."""

    def test_verify_correct_password(self):
        hashed = hash_password("SecurePass1!")
        assert verify_password("SecurePass1!", hashed) is True

    def test_reject_wrong_password(self):
        hashed = hash_password("SecurePass1!")
        assert verify_password("WrongPass1!", hashed) is False

    def test_hashes_are_not_plaintext(self):
        hashed = hash_password("SecurePass1!")
        assert "SecurePass1!" not in hashed


@pytest.mark.unit
class TestValidatePassword:
    """Tests for validate_password."""

    def test_accepts_strong_password(self, tmp_path):
        settings = _settings(tmp_path)
        ok, msg = validate_password("T3stP@ssword1!", settings)
        assert ok is True
        assert msg == ""

    def test_rejects_too_short(self, tmp_path):
        settings = _settings(tmp_path, auth_password_min_length=20)
        ok, msg = validate_password("T3stP@ssw0!", settings)
        assert ok is False
        assert "20" in msg

    def test_rejects_no_digit(self, tmp_path):
        settings = _settings(tmp_path, auth_password_require_number=True)
        ok, msg = validate_password("NoDigitHere@!AA", settings)
        assert ok is False
        assert "number" in msg.lower()

    def test_rejects_no_uppercase(self, tmp_path):
        settings = _settings(tmp_path, auth_password_require_uppercase=True)
        ok, msg = validate_password("nouppercase1@!", settings)
        assert ok is False
        assert "uppercase" in msg.lower()

    def test_rejects_no_special(self, tmp_path):
        settings = _settings(tmp_path, auth_password_require_special=True)
        ok, msg = validate_password("NoSpecial1234A", settings)
        assert ok is False
        assert "special" in msg.lower()

    def test_rejects_common_password(self, tmp_path):
        # Disable all complexity rules so only the common-password check fires
        settings = _settings(
            tmp_path,
            auth_password_min_length=1,
            auth_password_require_number=False,
            auth_password_require_letter=False,
            auth_password_require_uppercase=False,
            auth_password_require_special=False,
        )
        ok, msg = validate_password("password", settings)
        assert ok is False
        assert "common" in msg.lower()


@pytest.mark.unit
class TestCreateTokenBundle:
    """Tests for create_token_bundle."""

    def test_returns_token_bundle(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        assert isinstance(bundle, TokenBundle)

    def test_access_token_is_decodable(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        payload = decode_token(bundle.access_token, settings)
        assert payload["user_id"] == "user-id-1"

    def test_refresh_token_is_decodable(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        payload = decode_token(bundle.refresh_token, settings)
        assert payload["user_id"] == "user-id-1"

    def test_access_token_type(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        payload = decode_token(bundle.access_token, settings)
        assert is_access_token(payload) is True
        assert is_refresh_token(payload) is False

    def test_refresh_token_type(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        payload = decode_token(bundle.refresh_token, settings)
        assert is_refresh_token(payload) is True
        assert is_access_token(payload) is False

    def test_different_jtis(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        assert bundle.access_jti != bundle.refresh_jti

    def test_access_expires_before_refresh(self, tmp_path):
        settings = _settings(
            tmp_path,
            auth_access_token_minutes=30,
            auth_refresh_token_days=7,
        )
        bundle = create_token_bundle("user-id-1", "alice", settings)
        assert bundle.access_expires_at < bundle.refresh_expires_at


@pytest.mark.unit
class TestDecodeToken:
    """Tests for decode_token."""

    def test_raises_on_expired_token(self, tmp_path):
        settings = _settings(tmp_path)
        # Build an already-expired token
        secret = settings.auth_jwt_secret.get_secret_value()
        claims: dict[str, Any] = {
            "sub": "alice",
            "type": "access",
            "jti": "test-jti",
            "exp": int((datetime.now(UTC) - timedelta(seconds=1)).timestamp()),
        }
        expired_token = jwt.encode(claims, secret, algorithm=settings.auth_jwt_algorithm)
        with pytest.raises(TokenError):
            decode_token(expired_token, settings)

    def test_raises_on_wrong_secret(self, tmp_path):
        settings = _settings(tmp_path, auth_jwt_secret="correct-secret")
        bundle = create_token_bundle("user-id-1", "alice", settings)
        wrong_settings = _settings(tmp_path, auth_jwt_secret="wrong-secret")
        with pytest.raises(TokenError):
            decode_token(bundle.access_token, wrong_settings)

    def test_raises_on_tampered_payload(self, tmp_path):
        settings = _settings(tmp_path)
        bundle = create_token_bundle("user-id-1", "alice", settings)
        # Flip a character in the payload segment
        parts = bundle.access_token.split(".")
        tampered = parts[0] + "." + parts[1][:-2] + "ZZ" + "." + parts[2]
        with pytest.raises(TokenError):
            decode_token(tampered, settings)

    def test_algorithm_enforcement_rejects_none_alg(self, tmp_path):
        """S-5: Verify decode_token rejects 'alg: none' algorithm confusion tokens.

        python-jose's jwt.decode(..., algorithms=[...]) explicitly whitelists
        algorithms.  A token signed with alg=none (no signature) must be rejected
        because 'none' is not in the accepted algorithms list.
        """
        settings = _settings(tmp_path)
        claims: dict[str, Any] = {
            "sub": "alice",
            "user_id": "user-id-1",
            "type": "access",
            "jti": "test-jti",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }
        # Craft a token with alg=none and no signature
        header = {"alg": "none", "typ": "JWT"}
        def _b64(data: dict) -> str:
            return (
                base64.urlsafe_b64encode(_json.dumps(data).encode())
                .rstrip(b"=")
                .decode()
            )

        none_token = f"{_b64(header)}.{_b64(claims)}."

        with pytest.raises(TokenError):
            decode_token(none_token, settings)

    def test_algorithm_enforcement_rejects_hs512_when_hs256_configured(self, tmp_path):
        """S-5: Verify decode_token rejects tokens signed with an unexpected algorithm."""
        settings = _settings(tmp_path, auth_jwt_algorithm="HS256")
        secret = settings.auth_jwt_secret.get_secret_value()
        claims: dict[str, Any] = {
            "sub": "alice",
            "user_id": "user-id-1",
            "type": "access",
            "jti": "test-jti",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }
        # Sign with HS512 but settings only allow HS256
        hs512_token = jwt.encode(claims, secret, algorithm="HS512")
        with pytest.raises(TokenError):
            decode_token(hs512_token, settings)


@pytest.mark.unit
class TestTokenTypeChecks:
    """Tests for is_access_token and is_refresh_token."""

    def test_is_access_token_true(self):
        assert is_access_token({"type": "access"}) is True

    def test_is_access_token_false_for_refresh(self):
        assert is_access_token({"type": "refresh"}) is False

    def test_is_refresh_token_true(self):
        assert is_refresh_token({"type": "refresh"}) is True

    def test_is_refresh_token_false_for_access(self):
        assert is_refresh_token({"type": "access"}) is False

    def test_is_access_token_false_for_empty(self):
        assert is_access_token({}) is False

    def test_is_refresh_token_false_for_empty(self):
        assert is_refresh_token({}) is False
