"""Unit tests for password policy enforcement (Issue #342)."""

from __future__ import annotations

import pytest

from file_organizer.api.auth import validate_password
from file_organizer.api.config import ApiSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides: object) -> ApiSettings:
    """Return a minimal ApiSettings with auth enabled and safe defaults."""
    base = {
        "environment": "test",
        "auth_jwt_secret": "test-secret-32-chars-long-enough!!",
        "auth_password_min_length": 12,
        "auth_password_require_letter": True,
        "auth_password_require_number": True,
        "auth_password_require_special": True,
        "auth_password_require_uppercase": True,
    }
    base.update(overrides)  # type: ignore[arg-type]
    return ApiSettings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestPasswordMinLength
# ---------------------------------------------------------------------------


class TestPasswordMinLength:
    """Passwords shorter than min_length should be rejected."""

    def test_password_shorter_than_12_rejected(self) -> None:
        settings = _settings()
        ok, msg = validate_password("Short1!A", settings)
        assert not ok
        assert "12" in msg

    def test_password_exactly_11_chars_rejected(self) -> None:
        settings = _settings()
        ok, msg = validate_password("Abcdefg1!xy", settings)
        assert not ok
        assert "12" in msg

    def test_password_exactly_12_chars_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abcdefg12!xy", settings)
        assert ok

    def test_password_longer_than_12_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abcdefghij1!K", settings)
        assert ok

    def test_custom_min_length_respected(self) -> None:
        settings = _settings(auth_password_min_length=16)
        ok, msg = validate_password("Abcdefg12!xyZ", settings)  # 13 chars
        assert not ok
        assert "16" in msg


# ---------------------------------------------------------------------------
# TestPasswordRequireLetter
# ---------------------------------------------------------------------------


class TestPasswordRequireLetter:
    """Passwords without any letter should be rejected when configured."""

    def test_no_letters_rejected(self) -> None:
        settings = _settings(auth_password_require_letter=True)
        ok, msg = validate_password("123456789!@#", settings)
        assert not ok
        assert "letter" in msg.lower()

    def test_with_letter_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abc123!@#xyz", settings)
        assert ok

    def test_letter_check_bypassed_when_disabled(self) -> None:
        # All digits + special + uppercase disabled too for isolation
        ok, _ = validate_password(
            "123456789012",
            _settings(
                auth_password_require_letter=False,
                auth_password_require_uppercase=False,
                auth_password_require_special=False,
            ),
        )
        assert ok


# ---------------------------------------------------------------------------
# TestPasswordRequireNumber
# ---------------------------------------------------------------------------


class TestPasswordRequireNumber:
    """Passwords without any digit should be rejected when configured."""

    def test_no_digits_rejected(self) -> None:
        settings = _settings(auth_password_require_number=True)
        ok, msg = validate_password("Abcdef!@#xyz", settings)
        assert not ok
        assert "number" in msg.lower()

    def test_with_digit_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abcdef1!@xyz", settings)
        assert ok

    def test_number_check_bypassed_when_disabled(self) -> None:
        settings = _settings(
            auth_password_require_number=False,
            auth_password_require_special=False,
            auth_password_require_uppercase=False,
        )
        ok, _ = validate_password("abcdefghijkl", settings)
        assert ok


# ---------------------------------------------------------------------------
# TestPasswordRequireUppercase
# ---------------------------------------------------------------------------


class TestPasswordRequireUppercase:
    """Passwords without any uppercase letter should be rejected when configured."""

    def test_no_uppercase_rejected(self) -> None:
        settings = _settings(auth_password_require_uppercase=True)
        ok, msg = validate_password("abcdef1!@xyz", settings)
        assert not ok
        assert "uppercase" in msg.lower()

    def test_with_uppercase_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abcdef1!@xyz", settings)
        assert ok

    def test_uppercase_check_bypassed_when_disabled(self) -> None:
        settings = _settings(auth_password_require_uppercase=False)
        ok, _ = validate_password("abcdef1!@xyz", settings)
        assert ok


# ---------------------------------------------------------------------------
# TestPasswordRequireSpecial
# ---------------------------------------------------------------------------


class TestPasswordRequireSpecial:
    """Passwords without a special character should be rejected when configured."""

    def test_no_special_char_rejected(self) -> None:
        settings = _settings(auth_password_require_special=True)
        ok, msg = validate_password("Abcdefg1Hijk", settings)
        assert not ok
        assert "special" in msg.lower()

    def test_with_special_char_accepted(self) -> None:
        settings = _settings()
        ok, _ = validate_password("Abcdefg1!ijk", settings)
        assert ok

    def test_special_check_bypassed_when_disabled(self) -> None:
        settings = _settings(auth_password_require_special=False)
        ok, _ = validate_password("Abcdefg1Hijk", settings)
        assert ok

    @pytest.mark.parametrize(
        "special_char",
        ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "-", "_", "+", "="],
    )
    def test_various_special_chars_accepted(self, special_char: str) -> None:
        settings = _settings()
        password = f"Abcdefgh1{special_char}ij"
        ok, _ = validate_password(password, settings)
        assert ok, f"Expected '{special_char}' to satisfy special-char requirement"


# ---------------------------------------------------------------------------
# TestCommonPasswords
# ---------------------------------------------------------------------------


class TestCommonPasswords:
    """Common passwords should be rejected even if they meet other criteria."""

    @pytest.mark.parametrize(
        "common_pw",
        [
            # These are in _COMMON_PASSWORDS lowercased; the check normalises to lower
            "Password",
            "Password1",
            "passw0rd",
            "Admin",
            "letmein",
            "qwerty123",
            "abc123456",
            "iloveyou1",
            "sunshine1",
        ],
    )
    def test_common_password_rejected(self, common_pw: str) -> None:
        # Allow length/letter/number/uppercase/special to pass so we specifically
        # test the common-password block.
        settings = _settings(
            auth_password_require_letter=False,
            auth_password_require_number=False,
            auth_password_require_uppercase=False,
            auth_password_require_special=False,
            auth_password_min_length=1,
        )
        ok, msg = validate_password(common_pw, settings)
        assert not ok
        assert "common" in msg.lower()

    def test_unique_password_not_rejected_as_common(self) -> None:
        settings = _settings(
            auth_password_require_letter=False,
            auth_password_require_number=False,
            auth_password_require_uppercase=False,
            auth_password_require_special=False,
            auth_password_min_length=1,
        )
        ok, _ = validate_password("Tr0ub4dour&3-correct-horse", settings)
        assert ok


# ---------------------------------------------------------------------------
# TestStrongPassword
# ---------------------------------------------------------------------------


class TestStrongPassword:
    """A well-formed password should pass all checks with default settings."""

    def test_strong_password_passes_all_checks(self) -> None:
        settings = _settings()
        ok, msg = validate_password("Tr0ub4dour&3!", settings)
        assert ok, f"Expected strong password to pass, got: {msg}"

    def test_another_strong_password(self) -> None:
        settings = _settings()
        ok, msg = validate_password("C0rrect-Horse#Battery", settings)
        assert ok, f"Expected strong password to pass, got: {msg}"

    def test_minimum_viable_strong_password(self) -> None:
        """Exactly 12 chars meeting all requirements should pass."""
        settings = _settings()
        # A=upper, b=lower, 1=digit, !=special → 12 chars total
        ok, msg = validate_password("Abcdefg1!xyz", settings)
        assert ok, f"Expected minimum strong password to pass, got: {msg}"
