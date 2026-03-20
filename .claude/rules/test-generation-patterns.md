# Test Generation Anti-Patterns

Reference ruleset for writing tests that catch real bugs.
Sourced from CodeRabbit and Copilot review comments across integration test PRs.

**Core question to ask before writing any assertion:**
> "If the mock was never called / returned the wrong value / mutated nothing, would my test still pass?"
> If yes — the test is not catching anything real.

---

## Pre-Generation Checklist

Before writing any test:

- [ ] Does each assertion verify a *specific value*, not just a type or non-None? (T1 — use Fix-by-type table)
- [ ] After calling a mutating method, does the test verify the mutation persisted? (T2)
- [ ] Are mocks asserted with exact call args, not just `call_count >= 1`? (T3)
- [ ] Is `pytest.importorskip` scoped to only the classes that use the optional dep? (T5)
- [ ] Does this file import an optional dep at module level without `pytest.importorskip`? (T8)
- [ ] Does any assertion use `>= 0` on a length, count, or duration? Replace with a meaningful bound. (T9)

---

## Pattern T1: SOLE_ISINSTANCE — verified by CI guardrail

**What it is**: Test function's only assertion is `assert isinstance(x, T)`. Verifies the
return type but not the value. Since most methods have a defined success/failure value,
the test passes even if the implementation returns the wrong one.

**Bad**:
```python
def test_update_rule(self, rule_manager, sample_rule):
    rule_manager.add_rule("default", sample_rule)
    updated = Rule(name="pdf_to_archive", description="Updated description")
    result = rule_manager.update_rule("default", updated)
    assert isinstance(result, bool)  # passes even if update_rule returns False

def test_get_summary(self, analyzer):
    result = analyzer.get_summary()
    assert isinstance(result, str)  # passes even if get_summary returns ""

def test_load_config(self, loader):
    result = loader.load()
    assert isinstance(result, dict)  # passes even if load returns {}

def test_list_rules(self, rule_manager):
    result = rule_manager.list_rules()
    assert isinstance(result, list)  # passes even if list_rules returns []
```

**Good**:
```python
def test_update_rule(self, rule_manager, sample_rule):
    rule_manager.add_rule("default", sample_rule)
    updated = Rule(name="pdf_to_archive", description="Updated description")
    result = rule_manager.update_rule("default", updated)
    assert result is True
    retrieved = rule_manager.get_rule("default", "pdf_to_archive")
    assert retrieved is not None
    assert retrieved.description == "Updated description"
```

**Fix by type** (apply the appropriate fix for the return type):

| Return type | Weak assertion | Strong assertion |
|-------------|---------------|-----------------|
| `bool` | `assert isinstance(result, bool)` | `assert result is True` or `assert result is False` |
| `str` | `assert isinstance(result, str)` | `assert result == "expected_string"` or `assert "key" in result` |
| `dict` | `assert isinstance(result, dict)` | `assert result == {"key": "val"}` or `assert result["key"] == val` |
| `list` | `assert isinstance(result, list)` | `assert len(result) == N` + content check |
| `int` | `assert isinstance(result, int)` | `assert result == expected_int` |
| `float` | `assert isinstance(result, float)` | `assert result == pytest.approx(expected_float)` |

**Residual count**: ~135 sole-isinstance violations remain in the test suite; cleanup tracked in a
dedicated phase. The CI guardrail is currently diff-scoped (changed files only) — full-suite
enforcement will follow the cleanup phase.

**CI enforcement**: `test_changed_tests_have_no_sole_isinstance_assertions` in `tests/ci/test_test_quality_guardrails.py`

---

## Pattern T2: MISSING_STATE_VERIFICATION

**What it is**: Test calls a mutating method (add, update, remove, toggle, save) but only
asserts the return value, not that the state actually changed.

**Bad**:
```python
def test_remove_rule(self, rule_manager, sample_rule):
    rule_manager.add_rule("default", sample_rule)
    result = rule_manager.remove_rule("default", "pdf_to_archive")
    assert result is True  # but what if get_rule still returns the rule?
```

**Good**:
```python
def test_remove_rule(self, rule_manager, sample_rule):
    rule_manager.add_rule("default", sample_rule)
    result = rule_manager.remove_rule("default", "pdf_to_archive")
    assert result is True
    assert rule_manager.get_rule("default", "pdf_to_archive") is None  # state verified
```

**Pre-generation check**: For every mutating method call, ask: "How do I prove the mutation happened?"

---

## Pattern T3: MOCK_CALL_COUNT_WITHOUT_PAYLOAD

**What it is**: Mock verified with `call_count >= 1` or `assert_called()` without checking
what arguments it was called with. The test passes even if the mock was called with garbage.

**Bad**:
```python
def test_sends_notification(self, mock_notifier):
    service.process(item)
    assert mock_notifier.notify.call_count >= 1  # called, but with what?
```

**Good**:
```python
def test_sends_notification(self, mock_notifier):
    service.process(item)
    mock_notifier.notify.assert_called_once_with(
        recipient="user@example.com",
        subject="Processing complete",
    )
```

---

## Pattern T4: TAUTOLOGICAL_DISJUNCTION

**What it is**: `assert X is None or isinstance(X, T)` — always passes for `None` or any
value of type `T`. Equivalent to asserting nothing meaningful about the non-None case.

**Bad**:
```python
result = rule_manager.toggle_rule("default", "ghost")
assert result is None or isinstance(result, bool)  # always True for None or bool
```

**Good**:
```python
result = rule_manager.toggle_rule("default", "ghost")
assert result is None  # nonexistent rule returns None specifically
```

---

## Pattern T5: IMPORTSKIP_SCOPE

**What it is**: `pytest.importorskip("pkg")` at module level in a file that mixes classes
with and without the optional dependency. All classes in the file are skipped when the
package is absent, including ones that don't need it.

**Bad**:
```python
# test_security_bm25_decorators.py
pytest.importorskip("rank_bm25")  # skips security + decorator tests too!

class TestPluginSecurityPolicy: ...   # doesn't use rank_bm25
class TestBM25Index: ...              # does use rank_bm25
```

**Good**:
```python
# test_security_bm25_decorators.py
class TestPluginSecurityPolicy: ...   # no importorskip needed

class TestBM25Index:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")
```

---

## Pattern T6: WEAK_CONFIDENCE_LEVEL_ASSERTION

**What it is**: `get_confidence_level` returns one of four specific strings. Asserting
`isinstance(level, str)` passes even if the function returns `"garbage"`.

**Bad**:
```python
def test_high_confidence(self, conf_engine):
    level = conf_engine.get_confidence_level(0.9)
    assert isinstance(level, str)
```

**Good**:
```python
def test_high_confidence(self, conf_engine):
    level = conf_engine.get_confidence_level(0.9)
    assert level == "high"  # 0.9 >= HIGH_CONFIDENCE_THRESHOLD (0.75)
```

**Known level boundaries** (from `ConfidenceEngine`):
- `>= 0.75` → `"high"`
- `>= 0.50` → `"medium"`
- `>= 0.25` → `"low"`
- `< 0.25` → `"very_low"`

---

## Pattern T7: UNVERIFIED_EXCEPTION_GUARD

**What it is**: `try/except SomeError: pass` wrapping a function call. If the production
code never raises that exception (e.g. returns an empty dict instead), the guard silently
swallows any real errors the test should have caught.

**Bad**:
```python
try:
    result = deduplicator.find_duplicates([f1, f2], min_text_length=10)
    assert isinstance(result, dict)
except ValueError:
    pass  # "sklearn may raise on small corpora" — but it doesn't
```

**Good**:
```python
result = deduplicator.find_duplicates([f1, f2], min_text_length=10)
assert isinstance(result, dict)
```

**Pre-generation check**: Before adding a try/except in a test, verify the production
code actually raises that exception. If it returns a sentinel value instead, remove the guard.

---

## Pattern T8: MISSING_IMPORT_GUARD

**What it is**: Test file imports an optional dependency at module level (top-level `import`
or `from X import Y`) without a `pytest.importorskip` guard. When the package is absent the
entire file fails with `ImportError` at collection time — silencing all tests in the file,
including ones that don't need the optional dep.

Distinct from T5 (IMPORTSKIP_SCOPE) which covers a *misplaced* guard; T8 covers a *missing*
guard entirely.

**Bad**:
```python
from rank_bm25 import BM25Okapi  # crashes entire file if rank_bm25 not installed

class TestBM25Search:
    def test_basic_search(self): ...

class TestFileValidator:      # doesn't use rank_bm25, but also silenced
    def test_validates_pdf(self): ...
```

**Good**:
```python
class TestBM25Search:
    @pytest.fixture(autouse=True)
    def _require_rank_bm25(self) -> None:
        pytest.importorskip("rank_bm25")

    def test_basic_search(self): ...

class TestFileValidator:      # unaffected; runs even without rank_bm25
    def test_validates_pdf(self): ...
```

**Optional dependencies in this project** (require guards): `rank_bm25`, `sklearn`
(scikit-learn), `fitz` (PyMuPDF), `docx` (python-docx), `openpyxl`, `pptx`
(python-pptx), `ebooklib`, `bs4` (beautifulsoup4).

**Pre-generation check**: Before writing any test that imports from the list above, add a
class-level `@pytest.fixture(autouse=True)` that calls `pytest.importorskip("<package>")`.
Never use a module-level guard in files with mixed classes.

---

## Pattern T9: VACUOUS_TAUTOLOGY_ASSERTION

**What it is**: An assertion that is always true by mathematical definition — passes even
when the code is completely broken. Common forms:

- `assert len(results) >= 0` — `len()` is always ≥ 0 by definition
- `assert count >= 0` — counts are non-negative by definition
- `assert duration >= 0` — elapsed time is non-negative
- `assert total_size >= 0` — sizes are non-negative

The assertion provides zero signal: it passes whether `results` is empty, full, or even
`None` (which would have raised before the assertion).

**Bad**:
```python
results = searcher.find(query)
assert len(results) >= 0   # always True — len() is never negative

count = tracker.get_count()
assert count >= 0          # always True — counts are non-negative

duration = timer.elapsed()
assert duration >= 0       # always True — elapsed time is non-negative
```

**Good**:
```python
results = searcher.find(query)
assert len(results) >= 1   # lower bound > 0 is meaningful
assert len(results) == 3   # exact count is strongest

count = tracker.get_count()
assert count == expected_count   # assert the actual expected value

duration = timer.elapsed()
assert duration < 5.0      # upper bound is meaningful (not lower bound)
```

**Pre-generation check**: Before writing `assert X >= 0`, ask: *"Is X a length, count,
size, or duration? If yes — this assertion always passes. Assert a meaningful bound
(>= 1, == expected, < max) instead."*

**CI enforcement**: `test_changed_tests_have_no_vacuous_len_gte_zero_assertions` in
`tests/ci/test_test_quality_guardrails.py` (detects `len(x) >= 0` and `0 <= len(x)` forms).

---

## Rule of Thumb

For every assertion, ask:
1. **T1**: "Is isinstance the *only* assertion? If yes — use the Fix-by-type table above."
2. **T2**: "Did I call a mutating method? Did I verify the state changed?"
3. **T3**: "Did I verify mock call args, not just call count?"
4. **T4**: "Is this an `X or isinstance(X, T)` disjunction? Flatten to a specific check."
5. **T5**: "Is importorskip at module level in a mixed file? Move to class-level autouse."
6. **T7**: "Does this try/except guard an exception the production code actually raises?"
7. **T8**: "Does this test file import an optional dep at module level without a guard?"
8. **T9**: "Is `assert X >= 0` where X is a length/count/duration? Replace with a meaningful bound."

**Last audited PR**: #921
