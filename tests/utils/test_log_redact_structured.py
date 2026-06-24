"""Structured log redaction tests for stdlib extra attributes and loguru extra/bind.

Verifies that sensitive credentials passed in structured fields (extra= or bind())
are intercepted and redacted to [REDACTED] in-place.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from file_organizer.utils.log_redact import REDACTED, CredentialRedactingFilter

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


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
        {
            "api_key": "sk-super-secret-xyz",
            "db_password": "supersecretpassword",
            "normal_field": "public",
        },
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


def test_stdlib_exc_info_legacy_form_with_none_value() -> None:
    """``exc_info`` as a malformed ``(type, None, tb)`` triple still formats.

    A non-empty 3-tuple is truthy even when the value slot is ``None``, so
    the filter's ``if record.exc_info:`` guard passes and falls into the
    legacy 3-arg ``traceback.format_exception`` branch (the single-arg form
    requires a real exception value). Must not raise.
    """
    f = CredentialRedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="caught something odd",
        args=None,
        exc_info=(ValueError, None, None),
    )
    assert f.filter(record) is True
    assert record.exc_text is not None


def test_loguru_patcher_normalizes_non_dict_extra() -> None:
    """A loguru record whose ``extra`` is missing/non-dict is normalized in place.

    Real loguru records always carry a dict ``extra``, but the patcher
    defends against a malformed record (no ``extra`` key at all) by
    substituting an empty dict before scrubbing keys.
    """
    f = CredentialRedactingFilter()
    from file_organizer.utils.log_redact import _install_on_loguru

    _install_on_loguru(f)
    patcher = getattr(f, "_loguru_patcher", None)
    assert patcher is not None

    record: dict[str, Any] = {"message": "no extra key here", "exception": None}
    patcher(record)

    assert isinstance(record["extra"], dict)
    assert record["extra"].get("_fo_redacted") is not None


def test_loguru_patcher_exception_legacy_form_with_none_value() -> None:
    """A loguru ``RecordException`` with ``value=None`` uses the legacy
    3-arg ``traceback.format_exception`` fallback rather than raising.
    """
    from loguru._recattrs import RecordException

    from file_organizer.utils.log_redact import _install_on_loguru

    f = CredentialRedactingFilter()
    _install_on_loguru(f)
    patcher = getattr(f, "_loguru_patcher", None)
    assert patcher is not None

    fake_exc = RecordException(ValueError, None, None)
    record: dict[str, Any] = {
        "message": "an error occurred",
        "exception": fake_exc,
        "extra": {},
    }
    patcher(record)

    new_exc = record["exception"]
    assert new_exc is not fake_exc
    assert new_exc is not None
