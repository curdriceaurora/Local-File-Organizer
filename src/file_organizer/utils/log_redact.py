"""Credential-redacting ``logging.Filter`` (A3, hardening roadmap).

Project-wide safety net for the common shapes in which API keys, tokens,
passwords and bearer credentials accidentally end up in log records. The
existing model-client code already avoids logging the key directly (see
``models/_openai_client.py:74`` and ``models/_claude_client.py:69``, both of
which log ``type(e).__name__`` rather than the exception message), but
future code paths can still reach a ``logger.info("api_key=%s", ...)`` by
accident — the filter exists so the mistake fails closed.

Contract:

- ``CredentialRedactingFilter.filter`` always returns ``True``. The filter's
  job is redaction, not level-based suppression — handler levels and
  downstream filters still decide emission.
- Both the inline message (``record.msg``) and the positional format args
  (``record.args``) are scrubbed. ``record.getMessage()`` continues to work.
- ``REDACTED`` is a module-level public constant so tests and integration
  assertions can reference the exact replacement token without duplicating
  its string form.

The filter is attached to the root logger in ``cli.main`` so every
``logging.getLogger(__name__)`` inherits the protection.
"""

from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Iterable, Mapping

REDACTED = "[REDACTED]"

# Unforgeable module-level sentinel for the idempotency guard. Using a
# truthy attribute (``record._fo_redacted = True``) is vulnerable to
# bypass via ``logger.info(..., extra={"_fo_redacted": True})`` — an
# attacker-controlled log-extra could mark the record as already
# redacted and skip the scrub. Identity check on a unique ``object()``
# instance can't be forged without a reference to our sentinel.
_RECORD_REDACTED_SENTINEL = object()

# Keys that, when seen as the left-hand side of ``key=value`` / ``key: value``
# / ``key="value"`` in a log message, should have their right-hand side
# replaced with ``REDACTED``. Hyphen and underscore spellings both covered
# (api_key vs api-key). Matched case-insensitively via the ``(?i)`` in the
# assembled pattern below.
_CRED_KEYS = (
    "api[_-]?key",
    "api[_-]?token",
    "access[_-]?token",
    "auth[_-]?token",
    "bearer[_-]?token",
    # Bare ``auth`` is a common shorthand (``logger.info("auth=%s", secret)``).
    # Won't false-positive on ``author=`` etc. because the pattern requires
    # the key to be immediately followed by ``=``/``:`` (optional quote).
    "auth",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
)
# ``authorization`` is NOT in ``_CRED_KEYS`` because ``_KV_PATTERN`` would
# then preempt ``_BEARER_PATTERN`` on ``Authorization: Bearer <token>`` —
# the kv match would capture only ``Bearer`` as the value (stops at
# whitespace), leaving the actual token unredacted. Handle the bearer-
# header shape exclusively via ``_BEARER_PATTERN``. But for the mapping-
# style case (``logger.info("%(Authorization)s", {"Authorization": ...})``,
# codex P1 PRRT_kwDOR_Rkws59JVLj) ``_BEARER_PATTERN`` can't catch it
# post-format (the prefix is gone), so we pre-scrub by matching the dict
# KEY name. Dict-key scrub uses a wider list than the text pattern.
_CRED_KEY_FULL_NAMES: tuple[str, ...] = (*_CRED_KEYS, "authorization")
# Full-match form for dict-arg key names in mapping-style format logs
# (``logger.info("%(api_key)s", {"api_key": ...})``). ``_KV_PATTERN``
# catches the ``key=value`` text shape, but mapping-style interpolation
# strips the key name before emission — ``getMessage()`` returns only
# the raw value, which doesn't match any text pattern. So we scrub
# credential-named mapping keys BEFORE formatting (codex P1
# PRRT_kwDOR_Rkws59I2zc). Uses the wider ``_CRED_KEY_FULL_NAMES`` list
# which includes ``authorization`` (see comment above).
_CRED_KEY_FULL = re.compile(r"(?i)^(?:" + "|".join(_CRED_KEY_FULL_NAMES) + r")$")
# ``key`` + optional quotes + ``=`` or ``:`` + value. The value arm has
# five alternatives ordered so each form stops on the correct delimiter:
#
# 1. Double-quoted, closed (``password="abc'def"``) — allows single
#    quotes, ``\\"`` escapes, and even raw interior ``"`` characters
#    inserted by ``logger.info('token="%s"', 'abc"def')``. A quote only
#    counts as the closer when the next char is a normal value boundary
#    (whitespace / field punctuation / end-of-string), so quoted
#    placeholders don't leak suffixes when the substituted credential
#    contains the same quote character as the template wrapper (codex
#    P1 PRRT_kwDOR_Rkws59JVLj) while still preserving trailing context in
#    shapes like ``password="secret". user=alice``,
#    ``token='secret': next``, ``password="secret"/ user=alice``, and
#    ``token='secret'?next=1``.
# 2. Single-quoted, closed — mirror case.
# 3. Double-quoted, UNCLOSED (``password="super secret``, truncated log
#    or malformed template) — eats everything up to end of line so the
#    remainder of the credential doesn't leak (codex P1
#    PRRT_kwDOR_Rkws59IsZr). Over-redaction here is safer than leak.
# 4. Single-quoted, unclosed — mirror case.
# 5. Unquoted — stops at whitespace / delimiter.
#
# The alternation order matters: the closed variants must come before
# the unclosed ones so well-formed quoted values don't accidentally get
# consumed by the greedy unclosed fallback.
_KV_PATTERN = re.compile(
    r"(?i)(?P<key>(?:" + "|".join(_CRED_KEYS) + r")[\"']?\s*[:=]\s*)"
    r"(?:"
    r'"(?P<qvalue_dq>(?:[^"\\]|\\.|"(?![\s,;:./?&}\])]|$))*)"(?=[\s,;:./?&}\])]|$)'
    r"|"
    r"'(?P<qvalue_sq>(?:[^'\\]|\\.|'(?![\s,;:./?&}\])]|$))*)'(?=[\s,;:./?&}\])]|$)"
    r"|"
    r'"(?P<mvalue_dq>[^\r\n]*)'
    r"|"
    r"'(?P<mvalue_sq>[^\r\n]*)"
    r"|"
    r"(?P<value>[^\"'\s,;&}\])]+)"
    r")"
)

# ``Authorization: Bearer <token>`` HTTP header shape. Distinct from the
# ``key=value`` pattern because the separator between the header name and
# ``Bearer`` is usually whitespace rather than a closing quote — but the
# separator between ``Authorization`` and the value can be either ``:``
# (header style) or ``=`` (query / form style; codex P2
# PRRT_kwDOR_Rkws59IQew). Allows optional quotes around both the key and
# the separator so dict-repr (``{'Authorization': 'Bearer abc'}``) and
# JSON (``"Authorization": "Bearer abc"``) forms also match — logger
# calls that pass header dicts are a real leak path (codex P1
# PRRT_kwDOR_Rkws59IB5U).
_BEARER_PATTERN = re.compile(
    r"(?i)(?P<prefix>authorization[\"']?\s*[:=]\s*[\"']?bearer\s+)(?P<value>[^\"'\s,;}]+)"
)


def _kv_replace(match: re.Match[str]) -> str:
    """``_KV_PATTERN`` callback: preserve the quote shape when redacting.

    Five branches, ordered the same as the pattern: closed dq/sq first
    (wrap REDACTED in matching quotes), then unclosed dq/sq (preserve the
    opening quote, emit REDACTED but no close — output stays recognisable
    as a truncated quoted value), then unquoted. The ``is not None`` check
    (rather than truthy) matters for empty-string values —
    ``password=""`` has ``qvalue_dq = ""`` which is falsy but not None.
    """
    if match.group("qvalue_dq") is not None:
        return f'{match.group("key")}"{REDACTED}"'
    if match.group("qvalue_sq") is not None:
        return f"{match.group('key')}'{REDACTED}'"
    if match.group("mvalue_dq") is not None:
        return f'{match.group("key")}"{REDACTED}'
    if match.group("mvalue_sq") is not None:
        return f"{match.group('key')}'{REDACTED}"
    return f"{match.group('key')}{REDACTED}"


def _redact_text(text: str) -> str:
    """Apply all credential patterns to ``text``.

    Returns a new string; the original is not mutated. Order of application
    doesn't matter because the patterns don't overlap.
    """
    text = _KV_PATTERN.sub(_kv_replace, text)
    text = _BEARER_PATTERN.sub(lambda m: f"{m.group('prefix')}{REDACTED}", text)
    return text


def _sanitize_args(args: object) -> object:
    """Replace every arg with ``REDACTED`` (fail-closed fallback).

    Used on exception paths where we couldn't format the template safely —
    logging's own error handler would otherwise print the raw ``record.args``
    tuple to stderr on format failure, which could leak a secret. Return a
    same-shape (tuple / dict / scalar) value with sentinels.
    """
    if isinstance(args, tuple):
        return tuple(REDACTED for _ in args)
    if isinstance(args, dict):
        return dict.fromkeys(args, REDACTED)
    return REDACTED


class CredentialRedactingFilter(logging.Filter):
    """Redact credential-shaped substrings in log records. Never drops.

    Attach to the root logger (or any parent logger) so every child logger
    inherits the filter. Per the ``logging`` module semantics, a filter on
    a logger applies to records that *originate* at that logger; filters
    on a handler apply to records routed through it. For maximum coverage
    the attachment point is the root logger in ``cli.main``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact ``record`` in-place. Always returns ``True`` (never drops).

        Idempotent: a sentinel attribute ``_fo_redacted`` is set on the
        record after the first pass so subsequent invocations (e.g. from
        both the ``setLogRecordFactory`` wrapper AND a duplicate
        logger-level filter attachment) short-circuit. Without this guard,
        the non-idempotent redact pattern would double-bracket already-
        scrubbed values (``api_key=[REDACTED]`` → ``api_key=[REDACTED]]``)
        for root-originated records, corrupting output.

        When ``record.args`` is non-empty, the record is a template +
        arguments pair (e.g. ``logger.info("api_key=%s", secret)``).
        Running the redact pattern on ``record.msg`` alone can strip ``%s``
        placeholders while leaving ``record.args`` intact, and the
        downstream ``record.getMessage()`` then raises ``TypeError`` —
        Python's logging error handler would print the raw ``args`` tuple
        (including the unredacted secret) to stderr. Avoid that by
        formatting first and redacting the result, then clearing ``args``
        so the formatted-and-redacted string is what ``getMessage()``
        returns.
        """
        # Identity check on ``_RECORD_REDACTED_SENTINEL``: a truthy
        # attribute ``record._fo_redacted = True`` reachable via
        # ``logger.info(..., extra={"_fo_redacted": True})`` could
        # otherwise short-circuit redaction before secrets are scrubbed.
        # The sentinel is a fresh ``object()`` whose identity can't be
        # reproduced from outside this module.
        if getattr(record, "_fo_redacted", None) is _RECORD_REDACTED_SENTINEL:
            return True
        # --- Message redaction (args-present and no-args paths) ---
        # ``getMessage()`` runs ``record.msg % record.args`` which invokes
        # each arg's ``__str__`` / ``__repr__``. A bug in any of those
        # (custom ``Exception`` subclass, buggy ``__str__`` raising
        # ``RuntimeError`` / ``AttributeError``, etc.) must NOT escape
        # the filter — we're attached via ``setLogRecordFactory`` so this
        # runs on EVERY ``logger.*()`` call, and escalating here would
        # break the caller's normal execution including records that
        # would otherwise be dropped later by level filtering.
        #
        # Fail-CLOSED posture: on exception paths, clear ``record.args``
        # to sentinel REDACTED entries so logging's own error handler
        # (which prints the raw args tuple to stderr on format failure)
        # can't leak the secret. Preserving the original args ("fail
        # open") is wrong for a credential safety net — the whole point
        # is that unknown-shape inputs get masked, not passed through.
        if record.args:
            try:
                # Pre-scrub mapping-style args: ``logger.info("%(api_key)s",
                # {"api_key": secret})`` interpolates just the raw value,
                # so post-format text redaction has no key=value shape to
                # match. Replace credential-named mapping values with the
                # REDACTED sentinel before ``getMessage()`` sees them.
                # ``collections.abc.Mapping`` covers ``UserDict``,
                # ``MappingProxyType``, and third-party mapping types
                # ``logging`` also accepts (codex P2
                # PRRT_kwDOR_Rkws59JMYx). Pre-scrub is INSIDE the try so a
                # broken ``Mapping.items()`` / ``__iter__`` implementation
                # can't escape the filter (codex P2
                # PRRT_kwDOR_Rkws59JVLp).
                if isinstance(record.args, Mapping):
                    record.args = {
                        k: (REDACTED if isinstance(k, str) and _CRED_KEY_FULL.match(k) else v)
                        for k, v in record.args.items()
                    }
                formatted = record.getMessage()
            except Exception:
                try:
                    record.msg = _redact_text(str(record.msg))
                except Exception:
                    record.msg = REDACTED
                # ``record.args`` is typed as ``tuple | Mapping | None``;
                # ``_sanitize_args`` preserves the shape (tuple→tuple,
                # dict→dict, scalar→str). Cast covers the fallback scalar.
                record.args = _sanitize_args(record.args)  # type: ignore[assignment]
            else:
                record.msg = _redact_text(formatted)
                record.args = None
        else:
            # No-args branch. Always stringify ``record.msg`` before
            # redacting — callers can pass non-string objects
            # (``logger.info({"api_key": "..."})`` or any custom object
            # whose ``__str__`` returns ``"token=..."``).
            try:
                rendered = str(record.msg)
            except Exception:
                record.msg = REDACTED
            else:
                record.msg = _redact_text(rendered)

        # --- Traceback redaction (applies to BOTH branches) ---
        # ``logger.exception()`` / ``logger.*(..., exc_info=True)``
        # attaches a ``(type, value, traceback)`` tuple at
        # ``record.exc_info``. The default formatter later calls
        # ``formatException`` and caches the result in ``record.exc_text``
        # — at which point the raw exception message (e.g.
        # ``RuntimeError("api_key=sk-xxx")``) is rendered verbatim into
        # the log output. Pre-format and redact the traceback now so the
        # formatter's "use cached exc_text if already set" branch picks
        # up our scrubbed version instead. Critical: this must run even
        # in the args branch (codex P1:
        # ``logger.error("msg: %s", value, exc_info=True)``).
        if record.exc_info:
            try:
                exc_text = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                # Fail-CLOSED on traceback formatting failure (buggy
                # ``__str__`` / ``__repr__`` on the exception itself).
                # Returning early leaves ``exc_text = None`` and
                # ``exc_info`` intact, which the default ``Formatter``
                # then re-renders via the same buggy call path — the
                # raw exception message (including any embedded secret)
                # ends up in the log output. Replace both with a safe
                # placeholder: ``exc_text = REDACTED`` pre-populates
                # the formatter cache, and clearing ``exc_info`` stops
                # the formatter from attempting its own render
                # (coderabbit Major PRRT_kwDOR_Rkws59II7G).
                record.exc_text = REDACTED
                record.exc_info = None
            else:
                record.exc_text = _redact_text(exc_text)
        elif record.exc_text:
            # Some code paths populate ``exc_text`` directly (e.g.,
            # pre-formatted exceptions, loguru-to-stdlib bridges)
            # without going through ``exc_info``. Redact those too so
            # a pre-rendered traceback containing a secret doesn't
            # reach the handler unscrubbed (coderabbit Major
            # PRRT_kwDOR_Rkws59II7G).
            record.exc_text = _redact_text(record.exc_text)
        # Mark the record so subsequent filter invocations (duplicate
        # logger-level filter attachment, factory + filter combo) skip the
        # re-redact pass. Essential because ``_KV_PATTERN`` isn't
        # idempotent on already-bracketed ``[REDACTED]`` values. Uses the
        # module-level sentinel (see comment at the top of ``filter``) so
        # external callers can't forge the idempotency marker.
        record._fo_redacted = _RECORD_REDACTED_SENTINEL  # pyre-ignore[16]: intentional dynamic attr — idempotency sentinel
        return True


def _install_on_loguru(instance: CredentialRedactingFilter) -> bool:
    """Register a patcher on the Loguru logger that redacts every record.

    Parts of the codebase (``src/models/_openai_client.py``,
    ``src/models/_claude_client.py``) use Loguru rather than the stdlib
    ``logging`` module. Loguru records don't go through
    ``setLogRecordFactory``, so a stdlib-only install leaves Loguru paths
    unprotected. Loguru's patcher API (``logger.configure(patcher=fn)``
    since 0.6) runs ``fn`` on every record dict before emission, which is
    the symmetric hook point.

    Returns ``True`` if loguru was installed, ``False`` if loguru is
    unavailable (the dep is declared as a base requirement in
    ``pyproject.toml`` but importing can still fail in minimal test envs).
    """
    try:
        from loguru import logger as loguru_logger
    except ImportError:  # pragma: no cover — loguru is a base dep
        return False

    from typing import Any

    def _patcher(record: Any) -> None:
        # Idempotency: a prior pass (duplicate install) marked this record,
        # skip to avoid double-redaction corrupting ``[REDACTED]`` brackets.
        # Identity check on the module sentinel rather than a truthy value
        # so a caller-supplied ``bind(_fo_redacted=True)`` can't bypass
        # redaction (coderabbit Major PRRT_kwDOR_Rkws59II7G, symmetric
        # with the stdlib filter).
        extra = record.get("extra") or {}
        if extra.get("_fo_redacted") is _RECORD_REDACTED_SENTINEL:
            return
        # Loguru record: ``{'message': str, 'exception': RecordException | None, ...}``.
        # Redact the main message and the exception repr (which loguru
        # stringifies during emission just like logging's exc_info path).
        msg = record.get("message")
        if isinstance(msg, str):
            record["message"] = _redact_text(msg)
        exc = record.get("exception")
        # ``RecordException`` is a namedtuple-ish object with ``type``,
        # ``value``, ``traceback``. We redact ``value``'s str representation
        # by replacing the exception with a re-formatted version, but the
        # simplest safe thing is to scrub the message via loguru's built-in
        # pre-formatted repr. Best-effort: stringify and rely on the
        # scrubbed message + exception message caught at emission.
        if exc is not None:
            try:
                exc_text = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
            except Exception:
                # Buggy ``__str__`` / ``__repr__`` on the exception itself.
                # Can't safely format, so drop the exception payload
                # entirely rather than let loguru render the original via
                # the same buggy call path. Non-silent statement satisfies
                # the silent-broad-except CI guardrail.
                record["exception"] = None
                return
            redacted = _redact_text(exc_text)
            # codex P1 (PRRT_kwDOR_Rkws59HjtX): the default loguru
            # formatter renders the exception block from
            # ``record["exception"]`` via ``traceback.format_exception`` —
            # a stashed ``record["extra"][...]`` is never consumed.
            # Replace the entire exception payload with a sanitized
            # ``RecordException`` whose value is a plain
            # ``Exception(redacted)`` and whose traceback is stripped (we
            # already formatted+scrubbed it into the exception's message).
            try:
                from loguru._recattrs import RecordException
            except ImportError:
                # Internal API moved — fall back to dropping the exception
                # block entirely. Still prevents the leak while degrading
                # gracefully. Non-silent statement.
                record["exception"] = None
                return
            sanitized = Exception(redacted)
            record["exception"] = RecordException(type(sanitized), sanitized, None)
        # Mark this record so duplicate patcher installs skip the rewrite.
        # Uses the module sentinel (see ``filter`` for the rationale).
        record["extra"]["_fo_redacted"] = _RECORD_REDACTED_SENTINEL

    # ``patcher`` runs on every record; installing twice would stack, so
    # configure with a single canonical patcher. ``logger.configure``
    # replaces the patcher rather than appending, making this idempotent.
    loguru_logger.configure(patcher=_patcher)
    # Keep a reference for potential teardown by tests.
    instance._loguru_patcher = _patcher  # type: ignore[attr-defined]
    return True


def install_on_root(extra_loggers: Iterable[str] = ()) -> CredentialRedactingFilter:
    """Install the redacting filter process-wide via ``setLogRecordFactory``.

    Python ``logging`` applies ``Logger`` filters only at the logger where a
    record *originates*; propagation to ancestor handlers does not re-run
    ancestor filters. Attaching a filter to the root logger therefore does
    NOT cover records emitted by child loggers (the common case — every
    ``logging.getLogger(__name__)`` in ``src/``).

    The fix is to wrap the global ``LogRecordFactory`` so redaction happens
    at record construction time, before any logger/handler sees it. Every
    record — regardless of originating logger or handler chain — is
    redacted. For symmetry we also add the filter to the root logger and
    any ``extra_loggers`` so ``logger.filter(record)`` continues to apply
    the same sanitisation to records constructed outside our factory
    (rare, but possible).

    Idempotent: calling twice installs exactly one factory wrapper (the
    second call is a no-op if our wrapper is already the active factory).
    Tests that need to restore the original factory can read
    ``filter_instance._original_factory`` and pass it back to
    ``logging.setLogRecordFactory``.

    Args:
        extra_loggers: Additional named loggers to attach the filter to
            as a belt-and-suspenders symmetric install.

    Returns:
        The installed filter instance. Callers may hold it for teardown.
    """
    instance = CredentialRedactingFilter()
    current_factory = logging.getLogRecordFactory()
    # Detect our own wrapper by a sentinel attribute so repeated installs
    # don't stack wrappers.
    if not getattr(current_factory, "_fo_log_redact_installed", False):

        def _redacting_factory(*args: object, **kwargs: object) -> logging.LogRecord:
            record = current_factory(*args, **kwargs)
            instance.filter(record)
            return record

        _redacting_factory._fo_log_redact_installed = True  # type: ignore[attr-defined]
        instance._original_factory = current_factory  # type: ignore[attr-defined]
        logging.setLogRecordFactory(_redacting_factory)

    logging.getLogger().addFilter(instance)
    for name in extra_loggers:
        logging.getLogger(name).addFilter(instance)
    # codex P1: Loguru has its own record pipeline that doesn't go through
    # ``setLogRecordFactory``. Install a symmetric patcher so loguru-based
    # log sites (``_openai_client.py``, ``_claude_client.py``) are covered.
    _install_on_loguru(instance)
    return instance
