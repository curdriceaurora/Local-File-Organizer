"""Structured log redaction tests for stdlib extra attributes and loguru extra/bind.

Verifies that sensitive credentials passed in structured fields (extra= or bind())
are intercepted and redacted to [REDACTED] in-place.
"""

from __future__ import annotations

import logging
from typing import Any

from file_organizer.utils.log_redact import REDACTED, CredentialRedactingFilter


def _make_record_with_extra(msg: str, extra: dict[str, Any]) -> logging.LogRecord:
    """Build a stdlib LogRecord and attach extra fields directly onto it."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=None,
        exc_info=None,
    )
    for k, v in extra.items():
        record.__dict__[k] = v
    return record


def test_stdlib_extra_credential_redaction() -> None:
    """Verify that credentials in stdlib logging's extra fields are redacted."""
    f = CredentialRedactingFilter()
    record = _make_record_with_extra(
        "Standard log message",
        {"api_key": "sk-super-secret-xyz", "db_password": "supersecretpassword", "normal_field": "public"},
    )
    assert f.filter(record) is True
    assert record.api_key == REDACTED
    assert record.db_password == REDACTED
    assert record.normal_field == "public"


def test_loguru_extra_credential_redaction() -> None:
    """Verify that credentials in loguru's extra/bind fields are redacted."""
    f = CredentialRedactingFilter()
    from file_organizer.utils.log_redact import _install_on_loguru

    _install_on_loguru(f)

    patcher = getattr(f, "_loguru_patcher", None)
    assert patcher is not None

    record: dict[str, Any] = {
        "message": "Loguru log message",
        "extra": {
            "api_key": "sk-super-secret-xyz",
            "db_password": "supersecretpassword",
            "normal_field": "public",
        },
        "exception": None,
    }
    patcher(record)

    assert record["extra"]["api_key"] == REDACTED
    assert record["extra"]["db_password"] == REDACTED
    assert record["extra"]["normal_field"] == "public"
