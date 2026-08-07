"""Patch-liveness report plugin (issue #1681, epic #1678).

Report-mode-only detector for "dead" patches: ``unittest.mock`` patches
(``@patch``, ``with patch(...)``, ``mocker.patch``) whose replacement mock
recorded zero accesses during the test that installed them. A dead patch
is the #1671 decay signature — the code under test no longer touches the
patched target, so the test passes for reasons unrelated to the patch.

Enable by setting ``FO_PATCH_LIVENESS_REPORT=<path>``; the plugin is
completely inert otherwise (no instrumentation is installed). When
enabled, findings are appended to ``<path>`` as JSON lines with fields
``file``, ``line``, ``nodeid``, ``target``, ``status``, ``access_count``.
Only ``dead`` and ``untracked`` entries are written; live patches are
omitted. Under pytest-xdist each worker writes ``<path>.<worker_id>``.

Semantics (pinned by tests/unit/plugins/test_patch_liveness.py):

- An access is a recorded call (``mock_calls``) or a child-mock creation
  from attribute reads (``_mock_children``). ``PropertyMock`` reads are
  calls, so they count.
- Test-side configuration (``return_value = ...``, ``side_effect = ...``)
  is NOT an access — a configured-but-unreached mock is still dead.
- A mock the test ran ``assert_not_called()`` on is ``asserted``, not
  dead: staying unreached is the contract being pinned.
- Plain-function replacements (``patch(..., some_fake)``) ARE tracked:
  the function is wrapped in a recording proxy that delegates to it, so
  calls become observable. See ``_wrap_callable`` for why only
  ``FunctionType`` qualifies.
- Other non-mock replacements (``patch(..., None)``, constants, classes,
  exception types, module and instance stand-ins) cannot be tracked and
  are reported as ``untracked``, never ``dead``.
- ``monkeypatch.setattr`` is out of scope: it installs plain objects with
  no call recording, so liveness is undecidable statically here.

This plugin NEVER fails a test. Enforcement (with an
``@pytest.mark.allow_unaccessed_patches(reason=...)`` opt-out) is a
separate, later issue gated on the triage worklist being drained.
"""

from __future__ import annotations

import functools
import json
import os
import types
from typing import Any
from unittest.mock import DEFAULT, MagicMock, NonCallableMock
from unittest.mock import _patch as _MockPatch  # type: ignore[attr-defined]

import pytest

ENV_VAR = "FO_PATCH_LIVENESS_REPORT"

# Module state. `records` accumulates (target_string, replacement_object)
# tuples for patches entered while a test is active; `findings` collects
# report rows for the whole session.
_state: dict[str, Any] = {
    "enabled": False,
    "orig_enter": None,
    "current": None,  # (nodeid, file, line) of the running test
    "records": [],
    "findings": [],
    "worker": None,  # xdist worker id, from pytest config (never the env)
    "orig_assertions": None,  # unwrapped NonCallableMock assertion methods
}


#: Attributes a bare Mock carries that were not assigned by a test.
_MOCK_OWN_ATTRS = frozenset({"method_calls"})

#: Marker set on a mock the test asserted was never called. Underscore-
#: prefixed so ``_test_assigned_attrs`` ignores it.
_ASSERTED_FLAG = "_fo_asserted_not_called"

#: Mock methods whose whole purpose is to assert a patch stayed unused.
_NEGATIVE_ASSERTIONS = ("assert_not_called", "assert_not_awaited")


def _test_assigned_attrs(mock: NonCallableMock) -> list[str]:
    """Return attribute names a test assigned directly onto *mock*.

    ``mock.attr = value`` stores the value in the instance ``__dict__``.
    A later read by the code under test therefore resolves straight from
    there, without going through ``__getattr__``, so no child mock is
    created and nothing is recorded. Mock's own bookkeeping is either
    underscore-prefixed or in ``_MOCK_OWN_ATTRS``.
    """
    return [name for name in vars(mock) if not name.startswith("_") and name not in _MOCK_OWN_ATTRS]


def classify_mock(new_obj: object) -> tuple[str, int | None]:
    """Classify a patch replacement object by observed accesses.

    Accepts either a mock or an ``autospec``-produced function, which is
    classified through the mock it carries on ``.mock``.

    Returns:
        ("untracked", None) for replacements with nothing to observe,
        ("asserted", 0) when the test asserted the mock was never called,
        ("live", n) for mocks with n > 0 recorded accesses,
        ("undecidable", 0) when nothing was recorded but the test assigned
            attributes onto the mock, whose reads are invisible to us,
        ("dead", 0) for mocks with zero recorded accesses and no such
            attributes.

    The ``undecidable`` case exists because reporting those as dead is
    simply wrong: ``mock_sys.platform = "darwin"`` followed by the code
    reading ``sys.platform`` records nothing, yet the patch is load
    bearing. Callers that gate on decay must treat undecidable as "not a
    finding", never as dead.
    """
    if not isinstance(new_obj, NonCallableMock):
        # ``autospec``/``create_autospec`` on a function hands back a real
        # function with the recording mock hung off ``.mock``. Read it only
        # on non-mocks: on a Mock, ``.mock`` would auto-create a child and
        # manufacture the very access we are trying to measure.
        autospec_mock = getattr(new_obj, "mock", None)
        if not isinstance(autospec_mock, NonCallableMock):
            return ("untracked", None)
        new_obj = autospec_mock
    # ``mock.assert_not_called()`` makes deadness the *contract*: the test is
    # pinning that the code under test does not reach the patched target.
    # Such a patch asserts more than most live ones, so reporting it as decay
    # is backwards — it accounted for 98 of the 101 rows a regeneration
    # reopened after the epic had marked them repaired.
    # Read ``__dict__`` directly, never ``getattr``: a Mock manufactures a
    # child for any unknown attribute, so ``getattr`` would return a truthy
    # child AND register the access it was asked to measure.
    if new_obj.__dict__.get(_ASSERTED_FLAG, False):
        return ("asserted", 0)
    count = len(new_obj.mock_calls) + len(new_obj._mock_children)
    if count:
        return ("live", count)
    if _test_assigned_attrs(new_obj):
        return ("undecidable", 0)
    return ("dead", 0)


def _wrap_callable(real: object) -> tuple[Any, MagicMock] | None:
    """Return ``(installed, probe)`` making *real*'s calls observable.

    Returns ``None`` when *real* must be installed unchanged.

    A patch whose replacement is a plain fake function is invisible to
    ``classify_mock`` — there is no mock to interrogate — so every such
    site lands in the ``untracked`` bucket and gets allowlisted on sight.
    That is the shape most likely to hide decay: a fixture installing a
    fake ``initialize`` that nothing ever calls is indistinguishable from
    one that is load bearing.

    The fix is to install a *function* that records into a companion
    ``probe`` mock and then delegates. The plugin classifies the probe,
    not the installed object, so observability costs nothing at the call
    site.

    Only ``types.FunctionType`` (``def`` and ``lambda``) qualifies, and
    the wrapper is deliberately a function too, because **binding must
    match exactly**:

    - A function set on a class is a descriptor: ``inst.meth()`` passes
      ``self``. A ``MagicMock`` is not a descriptor, so swapping one in
      silently drops ``self`` — the wrapper would be called with the
      wrong arguments and the fake would raise ``TypeError``.
    - Conversely, ``functools.partial``, ``builtin_function_or_method``
      and bound methods do *not* bind when set on a class. Wrapping those
      in a function would *add* a ``self`` argument that was never there.

    Restricting to ``FunctionType`` and wrapping in a ``FunctionType``
    keeps the descriptor protocol identical in both directions. Classes,
    exception types, modules and instances are left alone: ``except``,
    ``isinstance`` and attribute protocols all require the real object.

    Replacements mock built for itself are also left alone. ``autospec``
    yields a genuine ``FunctionType`` carrying mock machinery in its
    ``__dict__``; it is already observable, and wrapping it hands the
    test a copy whose recorded calls live on a different object.
    """
    # `staticmethod`/`classmethod` are binding decorators over a function.
    # Wrap the function they carry and re-apply the decorator, so the
    # binding the test asked for is exactly the binding installed.
    if isinstance(real, (staticmethod, classmethod)):
        inner = _wrap_callable(real.__func__)
        if inner is None:
            return None
        recorder, probe = inner
        return (type(real)(recorder), probe)
    if type(real) is not types.FunctionType:
        return None
    if isinstance(getattr(real, "mock", None), NonCallableMock):
        return None
    probe = MagicMock()

    if _is_async(real):

        @functools.wraps(real)
        async def recorder(*args: Any, **kwargs: Any) -> Any:
            probe(*args, **kwargs)
            return await real(*args, **kwargs)

    else:

        @functools.wraps(real)
        def recorder(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
            probe(*args, **kwargs)
            return real(*args, **kwargs)

    return (recorder, probe)


def _is_async(func: Any) -> bool:
    """True when *func* is a coroutine function.

    Checked on the raw flags rather than ``inspect.iscoroutinefunction``
    so a fake that is itself already wrapped is judged by what it is, not
    by what it delegates to.
    """
    return bool(func.__code__.co_flags & 0x80)  # CO_COROUTINE


def _describe_target(patcher: _MockPatch) -> str:
    """Build a readable target string from a started patcher.

    Must be called while the patch is active: ``_patch.__exit__`` deletes
    the resolved ``target`` attribute.
    """
    target = getattr(patcher, "target", None)
    name = getattr(target, "__name__", None) or repr(target)
    attribute = getattr(patcher, "attribute", None)
    return f"{name}.{attribute}" if attribute else str(name)


def _tracking_enter(patcher: _MockPatch) -> object:
    """Wrapper over ``_patch.__enter__`` recording patches per test.

    Plain-function replacements are swapped for a recording proxy so
    their calls become observable; the probe is what gets classified.
    ``_patch.__exit__`` restores from its own saved ``temp_original`` and
    never inspects what is currently installed, so the swap is invisible
    to teardown.
    """
    result = _state["orig_enter"](patcher)
    if _state["current"] is None:
        return result
    target = _describe_target(patcher)
    # Only replacements the *test* supplied are candidates. When ``new`` is
    # DEFAULT, mock built the replacement itself (bare patch, spec,
    # autospec) and it is already observable — and the test is handed that
    # object, so substituting ours would strand its assertions on a copy.
    wrapped = _wrap_callable(result) if patcher.new is not DEFAULT else None
    if wrapped is None:
        _state["records"].append((target, result))
        return result
    installed, probe = wrapped
    setattr(patcher.target, patcher.attribute, installed)
    _state["records"].append((target, probe))
    return installed


def _install_negative_assertion_tracking() -> dict[str, Any]:
    """Record on the mock itself when a test asserts it was never called.

    Done by wrapping the ``NonCallableMock`` methods rather than by reading
    test source, so the flag lands on the exact object asserted — no name
    matching, and it works through fixtures, helpers and aliases.

    Returns the originals so ``pytest_unconfigure`` can restore them.
    """
    originals: dict[str, Any] = {}
    for name in _NEGATIVE_ASSERTIONS:
        original = getattr(NonCallableMock, name, None)
        if original is None:  # assert_not_awaited only exists on AsyncMock
            continue
        originals[name] = original

        def make(orig: Any) -> Any:
            @functools.wraps(orig)
            def tracked(self: Any, *args: Any, **kwargs: Any) -> Any:
                result = orig(self, *args, **kwargs)
                # Only on success: a failing assertion is not a contract.
                object.__setattr__(self, _ASSERTED_FLAG, True)
                return result

            return tracked

        setattr(NonCallableMock, name, make(original))
    return originals


def pytest_configure(config: pytest.Config) -> None:
    """Install the ``_patch.__enter__`` instrumentation when enabled."""
    if not os.environ.get(ENV_VAR):
        return
    if _state["enabled"]:  # already installed (defensive: nested sessions)
        return
    _state["enabled"] = True
    _state["orig_assertions"] = _install_negative_assertion_tracking()
    # Ask pytest, not the environment, whether this session is an xdist
    # worker. ``PYTEST_XDIST_WORKER`` is inherited by any subprocess a test
    # spawns, so a nested session would otherwise believe it is a worker and
    # write its report to a suffixed path nobody reads.
    _state["worker"] = getattr(config, "workerinput", {}).get("workerid")
    _state["orig_enter"] = _MockPatch.__enter__
    _MockPatch.__enter__ = _tracking_enter


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restore the original ``_patch.__enter__``."""
    if _state["enabled"] and _state["orig_enter"] is not None:
        _MockPatch.__enter__ = _state["orig_enter"]
        for name, original in (_state["orig_assertions"] or {}).items():
            setattr(NonCallableMock, name, original)
        _state["enabled"] = False
        _state["orig_enter"] = None
        _state["orig_assertions"] = None
        _state["worker"] = None


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Open the attribution window for this test."""
    if not _state["enabled"]:
        return
    file, lineno, _ = item.location
    _state["current"] = (item.nodeid, file, (lineno or 0) + 1)
    _state["records"] = []


def pytest_runtest_teardown(item: pytest.Item) -> None:
    """Evaluate every patch recorded during this test."""
    if not _state["enabled"] or _state["current"] is None:
        return
    nodeid, file, line = _state["current"]
    for target, new_obj in _state["records"]:
        status, count = classify_mock(new_obj)
        if status in ("live", "asserted"):
            continue
        _state["findings"].append(
            {
                "file": file,
                "line": line,
                "nodeid": nodeid,
                "target": target,
                "status": status,
                "access_count": count,
            }
        )
    _state["current"] = None
    _state["records"] = []


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Append this session's findings to the report file."""
    if not _state["enabled"] or not _state["findings"]:
        return
    path = os.environ[ENV_VAR]
    worker = _state["worker"]
    if worker:
        path = f"{path}.{worker}"
    # This plugin is report-only and must never be the reason a suite fails.
    # A report path under a directory that does not exist yet is an ordinary
    # caller mistake, not a test failure, so create it rather than raising
    # out of sessionfinish. Any other write error still propagates — silently
    # dropping findings would be worse than a loud failure.
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for finding in _state["findings"]:
            fh.write(json.dumps(finding, sort_keys=True) + "\n")
    _state["findings"] = []
