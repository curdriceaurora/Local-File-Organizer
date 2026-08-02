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
- Non-mock replacements (``patch(..., None)``, plain sentinel values)
  cannot be tracked and are reported as ``untracked``, never ``dead``.
- ``monkeypatch.setattr`` is out of scope: it installs plain objects with
  no call recording, so liveness is undecidable statically here.

This plugin NEVER fails a test. Enforcement (with an
``@pytest.mark.allow_unaccessed_patches(reason=...)`` opt-out) is a
separate, later issue gated on the triage worklist being drained.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import NonCallableMock
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
}


#: Attributes a bare Mock carries that were not assigned by a test.
_MOCK_OWN_ATTRS = frozenset({"method_calls"})


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

    Returns:
        ("untracked", None) for non-mock replacements,
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
        return ("untracked", None)
    count = len(new_obj.mock_calls) + len(new_obj._mock_children)
    if count:
        return ("live", count)
    if _test_assigned_attrs(new_obj):
        return ("undecidable", 0)
    return ("dead", 0)


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
    """Wrapper over ``_patch.__enter__`` recording patches per test."""
    result = _state["orig_enter"](patcher)
    if _state["current"] is not None:
        _state["records"].append((_describe_target(patcher), result))
    return result


def pytest_configure(config: pytest.Config) -> None:
    """Install the ``_patch.__enter__`` instrumentation when enabled."""
    if not os.environ.get(ENV_VAR):
        return
    if _state["enabled"]:  # already installed (defensive: nested sessions)
        return
    _state["enabled"] = True
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
        _state["enabled"] = False
        _state["orig_enter"] = None
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
        if status == "live":
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
    with open(path, "a", encoding="utf-8") as fh:
        for finding in _state["findings"]:
            fh.write(json.dumps(finding, sort_keys=True) + "\n")
    _state["findings"] = []
