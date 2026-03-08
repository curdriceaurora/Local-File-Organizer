# Test Generation Anti-Patterns

Reference ruleset for writing tests that pass PR review without correction.
Sourced from CodeRabbit and Copilot review comments across test-generation PRs (#603, #605, #607, #624, #635, #652, #655).

**Frequency baseline**: 280 classified findings across 7 PRs (40 findings/PR average).

---

## Pattern 1: WEAK_ASSERTION (Success-only check)

**What it is**: Asserting only `result["success"] is True` without verifying the underlying behavior.

**Bad**:
```python
# BAD — a facade returning {"success": True} with wrong data still passes
assert result["success"] is True
```

**Good**:
```python
# GOOD — verify the underlying call was made correctly
assert result["success"] is True
mock_cls.assert_called_once_with(dry_run=False)
mock_obj.method.assert_called_once_with(input_path=..., output_path=...)
```

---

## Pattern 2: NON_NONE_IDENTITY_CHECK (formerly MISSING_CALL_VERIFY)

Renamed from `MISSING_CALL_VERIFY` to match the narrower pattern documented here:
asserting a value is non-`None` instead of proving it is the expected instance.

**What it is**: Checking `is not None` instead of asserting the exact expected instance.

**Bad**:
```python
# BAD — wrong object still passes
assert svc is not None
```

**Good**:
```python
# GOOD — verify it's the exact expected instance
assert svc is mock_service
```

---

## Pattern 3: WRONG_PAYLOAD (Call count without payload)

**What it is**: Asserting call count without verifying what was passed.

**Bad**:
```python
# BAD — wrong payload still passes
assert mock.send.call_count >= 1
assert len(calls) >= 1
```

**Good**:
```python
# GOOD — assert exact payload
mock.send.assert_called_once_with({"type": "ping"})
assert calls[0][0][0] == {"type": "error", "message": "Unknown message type"}
```

---

## Pattern 3b: MISSING_CALL_VERIFY (Mock set up, call never verified)

**What it is**: A mock is configured and the function under test runs, but no `assert_called_*` check is ever made — so the mock could be uncalled or called with wrong args and the test still passes. This was the #1-ranked finding in the issue #656 audit (42 instances, 15% of all findings).

**Bad**:
```python
# BAD — mock set up but never verified; function could skip it entirely
mock_db.save = MagicMock()
result = service.create_user({"name": "alice"})
assert result["id"] == 1
```

**Good**:
```python
# GOOD — verify the dependency was actually invoked with correct args
mock_db.save = MagicMock(return_value={"id": 1})
result = service.create_user({"name": "alice"})
assert result["id"] == 1
mock_db.save.assert_called_once_with({"name": "alice"})
```

---

## Pattern 4: PERMISSIVE_FILTER (Filter instead of assert_not_called)

**What it is**: Filtering for a subset of values rather than asserting nothing was sent.

**Bad**:
```python
# BAD — unexpected message types still pass
responses = [c for c in calls if c[0][0].get("type") in ("pong", "error")]
assert len(responses) == 0
```

**Good**:
```python
# GOOD — assert nothing was sent at all
mock.send_personal_message.assert_not_called()
```

---

## Pattern 5: PRIVATE_ATTR (Private attribute access)

**What it is**: Asserting private SQLAlchemy / library internals that break across versions.

**Bad**:
```python
# BAD — breaks across library versions
assert engine.pool._max_overflow == 5
```

**Good**:
```python
# GOOD — use public API or structural check
assert isinstance(engine.pool, QueuePool)
```

---

## Pattern 6: BROAD_EXCEPTION (Broad exception catching)

**What it is**: Catching `Exception` broadly in tests, hiding real failures.

**Bad**:
```python
# BAD — hides real failures
try:
    await do_thing()
except Exception:
    pass
```

**Good**:
```python
# GOOD — assert specific exception or positive outcome
with pytest.raises(WebSocketDisconnect):
    await do_thing()
```

---

## Pattern 7: RESOURCE_LEAK (SQLAlchemy engines with LRU cache)

**What it is**: File-backed engines cached via LRU stay open after the test, breaking `tmp_path` cleanup.

**Bad**:
```python
# BAD — file-backed engine stays open
engine = get_engine(db_url, pool_size=2)
assert isinstance(engine.pool, QueuePool)
```

**Good**:
```python
# GOOD — always dispose file-backed engines
engine = get_engine(db_url, pool_size=2)
try:
    assert isinstance(engine.pool, QueuePool)
finally:
    engine.dispose()
```

---

## Pattern 8: DEAD_CODE (Unused helpers / imports)

**What it is**: Leaving unused test helper methods and imports in test files.

**Bad**:
```python
from app.service import build_payload  # unused import

def _make_unused_user():               # unused helper
    return {"name": "alice"}

def test_ping():
    assert ping() == "ok"
```

**Good**:
```python
def test_ping():
    assert ping() == "ok"
```

- Remove unused test helper methods and their imports immediately
- Ruff will catch unused imports but not unused methods — scan manually

---

## Pattern 9: BRITTLE_ASSERTION

**What it is**: Assertions that rely on the string `repr` of `call_args`, private
attributes, or other implementation details that break across library versions or
minor mock-API changes.

**Evidence**: PR #603 · `tests/web/test_router.py`
> "These assertions are brittle because they rely on `str(mock_tpl.TemplateResponse.call_args)`.
> It's more robust to assert on the actual positional/keyword arguments."

**Bad**:
```python
# BAD — repr-based, breaks if mock format changes
assert "template.html" in str(mock_render.call_args)
assert "200" in str(response.call_args)
```

**Good**:
```python
# GOOD — assert on actual args
mock_render.assert_called_once_with("template.html", {"key": "value"})
assert response.status_code == 200
```

**Root cause**: Reaching for `str()` to avoid learning `call_args` structure.
**Fix**: Use `mock.assert_called_once_with(...)`, `mock.call_args.args`, or
`mock.call_args.kwargs` directly.

---

## Pattern 10: WRONG_PATCH_TARGET

**What it is**: Patching the wrong module path so the patch never intercepts the
actual import used by production code.

**Evidence**: PR #603 · `tests/cli/test_cli_copilot.py`
> "`test_status_with_ollama` patches `file_organizer.cli.copilot._ollama`, but
> `copilot_status()` does a local `import ollama as _ollama`, so this patch is
> never used."

**Bad**:
```python
# BAD — patches the wrong location; production code imports locally
with patch("file_organizer.cli.copilot._ollama") as mock_ollama:
    result = copilot_status()
# mock_ollama was never called — patch didn't intercept
```

**Good**:
```python
# GOOD — patch where the name is looked up at call time
with patch("ollama.list") as mock_list:
    result = copilot_status()
mock_list.assert_called_once()
```

**Root cause**: Not reading the production import statement before writing the patch path.
**Fix**: Read the module under test; patch the dotted path where the name is *used*,
not where it is *defined*. For `import x as y` inside a function, patch the original
module attribute (`x.method`), not the local alias.

---

## Pattern 11: GLOBAL_STATE_LEAK

**What it is**: Test fixtures or mocks that modify global or class-level state
without teardown, causing test pollution that makes tests pass or fail depending
on execution order.

**Evidence**: PR #605 · `tests/services/intelligence/test_preference_database_coverage.py`
> "Use a `yield` fixture and close the manager in teardown. The fixture returns a
> live DB manager without guaranteed cleanup."

**Bad**:
```python
# BAD — no teardown, manager stays open and pollutes other tests
@pytest.fixture
def db_manager():
    return PreferenceDatabaseManager(":memory:")

# BAD — class-level mock that leaks across test instances
type(MagicMock).some_property = PropertyMock(return_value=True)
```

**Good**:
```python
# GOOD — yield fixture with guaranteed cleanup
@pytest.fixture
def db_manager():
    manager = PreferenceDatabaseManager(":memory:")
    yield manager
    manager.close()

# GOOD — use instance-level mock, not class-level
mock = MagicMock()
mock.some_property = True
```

**Root cause**: Using `return` instead of `yield` in fixtures that own resources;
mutating class-level attributes on `MagicMock` types.
**Fix**: Always use `yield` fixtures for any resource that needs explicit cleanup
(DB connections, temp files, threads, sockets). Never assign to `type(mock).attr`.

---

## Pattern 12: HARDCODED_ABSOLUTE_PATH

**What it is**: Hardcoding Unix-specific paths (`/tmp/...`, `/a.mp3`, `/proc/...`) instead of using `tmp_path`. Most flagged pattern in PRs #605 and #635 (25+ instances).

**Bad**:
```python
# BAD — Unix-only, leaves files behind
result = process_file(Path("/tmp/test_audio.mp3"))
```

**Good**:
```python
# GOOD — portable, auto-cleaned
def test_process(tmp_path):
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    result = process_file(audio)
```

---

## Pattern 13: TAUTOLOGY_ASSERTION

**What it is**: Assertions that are always true regardless of implementation — `isinstance(x, list)` on a list comprehension, `assert n >= 0` on a count. Provides zero regression protection.

**Bad**:
```python
# BAD — always true, tests nothing
result = [x for x in items]
assert isinstance(result, list)

count = len(items)
assert count >= 0
```

**Good**:
```python
# GOOD — verify actual content
assert result == ["expected_item"]
assert count == 3
```

---

## Pattern 14: MISSING_EXIT_CODE_ASSERT

**What it is**: CLI tests that check `result.output` without first asserting the expected `result.exit_code`, hiding crashes or wrong failure modes behind output matching.

**Bad**:
```python
# BAD — passes even if CLI crashed or returned the wrong status
result = runner.invoke(app, ["cmd"])
assert "Success" in result.output
```

**Good**:
```python
# GOOD — assert the expected exit code before checking output
result = runner.invoke(app, ["cmd"])
assert result.exit_code == 0, result.output   # success path: expect 0
assert "Success" in result.output

# For failure-path tests, assert the non-zero code explicitly:
result = runner.invoke(app, ["cmd", "--bad-arg"])
assert result.exit_code == 2, result.output   # typer/click usage error
assert "Error" in result.output
```

---

## Pattern 15: WRONG_TEMPLATE_ASSERTION

**What it is**: Web route tests assert `mock_templates.TemplateResponse.assert_called_once()` without checking which template name or what context dict was passed.

**Bad**:
```python
# BAD — passes even if wrong template rendered with wrong data
mock_templates.TemplateResponse.assert_called_once()
```

**Good**:
```python
# GOOD — verify template name and the context entries that matter
mock_templates.TemplateResponse.assert_called_once()
template_name, context = mock_templates.TemplateResponse.call_args.args[:2]
assert template_name == "dashboard.html"
assert context["request"] is mock_request
assert context["user"] == expected_user
```

---

## Pattern 16: WRONG_EXCEPTION_TYPE_IN_MOCK

**What it is**: Stubbing the wrong exception class so the test exercises the wrong error path.

**Bad**:
```python
# BAD — builtin ConnectionError ≠ httpx.ConnectError; wrong branch exercised
mock_client.get.side_effect = ConnectionError("network down")
```

**Good**:
```python
# GOOD — match the exact exception the production code catches
import httpx
mock_client.get.side_effect = httpx.ConnectError("network down")
```

---

## Pattern 17: MOCK_REAL_IMPLEMENTATION_BYPASS

**What it is**: Patching the method under test itself rather than its dependencies, so the test only validates the mock's return value, not the real logic.

**Bad**:
```python
# BAD — patches the function being tested; nothing is actually tested
with patch("module.service.do_thing", return_value={"ok": True}):
    result = service.do_thing(input)
assert result == {"ok": True}  # trivially true
```

**Good**:
```python
# GOOD — patch dependencies, exercise real logic
with patch("module.service.db_client.query", return_value=rows):
    result = service.do_thing(input)
assert result == expected_output
```

---

## Rule of Thumb

For every mocked dependency, ask: **"If this method was never called, or called with wrong args, would my test catch it?"**

If no: add `mock_obj.method.assert_called_once_with(expected_args)`.

### Pre-Commit Self-Check (apply before every new test file)

1. **No `str(mock.call_args)` assertions** — use `.assert_called_once_with()` (Pattern 9: BRITTLE_ASSERTION)
2. **Every `patch()` target is the import site, not the definition site** (Pattern 10: WRONG_PATCH_TARGET)
3. **Every fixture owning a resource uses `yield` + teardown** (Patterns 7, 11: RESOURCE_LEAK, GLOBAL_STATE_LEAK)
4. **Every mock call is verified with exact args** — not just call count (Pattern 3: WRONG_PAYLOAD)
5. **No `assert isinstance(x, list)` or `assert n >= 0`** — assert actual values (Pattern 13: TAUTOLOGY_ASSERTION)
6. **No hardcoded `/tmp/` paths** — use `tmp_path` fixture (Pattern 12: HARDCODED_ABSOLUTE_PATH)
7. **CLI tests assert the expected `exit_code` before checking output** — `== 0` for success paths, explicit non-zero for failure paths (Pattern 14: MISSING_EXIT_CODE_ASSERT)
8. **Web route tests check template name AND context dict** (Pattern 15: WRONG_TEMPLATE_ASSERTION)
9. **Exception mocks use the exact type the production code catches** (Pattern 16: WRONG_EXCEPTION_TYPE_IN_MOCK)
10. **Assertions check specific values, not just truthiness** (Pattern 1: WEAK_ASSERTION)
