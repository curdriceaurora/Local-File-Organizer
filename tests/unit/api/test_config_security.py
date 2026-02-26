"""Security tests for ApiSettings — specifically JWT secret handling with SecretStr."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from file_organizer.api.config import ApiSettings


@pytest.mark.unit
class TestJwtSecretSecretStr:
    """Verify auth_jwt_secret uses SecretStr to prevent log/repr leakage."""

    def test_jwt_secret_not_in_repr(self) -> None:
        """The raw secret value must not appear in repr() or str() of ApiSettings."""
        settings = ApiSettings(auth_jwt_secret="mysecret")  # type: ignore[arg-type]
        assert "mysecret" not in repr(settings)
        assert "mysecret" not in str(settings)

    def test_jwt_secret_accessible_via_get_secret_value(self) -> None:
        """The raw secret value must be accessible via get_secret_value()."""
        settings = ApiSettings(auth_jwt_secret="mysecret")  # type: ignore[arg-type]
        assert settings.auth_jwt_secret.get_secret_value() == "mysecret"

    def test_jwt_secret_field_is_secret_str(self) -> None:
        """auth_jwt_secret must be a SecretStr instance."""
        settings = ApiSettings(auth_jwt_secret="anysecret")  # type: ignore[arg-type]
        assert isinstance(settings.auth_jwt_secret, SecretStr)

    def test_jwt_secret_default_masked_in_repr(self) -> None:
        """The default 'change-me' value must also be masked in repr()."""
        settings = ApiSettings()
        assert "change-me" not in repr(settings)
        assert "change-me" not in str(settings)

    def test_jwt_secret_default_accessible_via_get_secret_value(self) -> None:
        """The default value must still be retrievable via get_secret_value()."""
        settings = ApiSettings()
        assert settings.auth_jwt_secret.get_secret_value() == "change-me"
