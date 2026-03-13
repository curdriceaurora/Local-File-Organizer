# Legacy Review Regression Test-Quality Rules

These rules codify the first-wave test-quality findings from the PR-review
audit. The detector is intentionally narrow: it targets high-confidence weak
mock-call assertions that frequently pass even when behavior is wrong.

## Rule Class Coverage

This detector pack currently owns one pattern:

1. Weak lower-bound assertions on `mock.call_count` that do not prove an exact
   interaction contract or concrete side effect.

## Invariant Protected

### `weak-mock-call-count-lower-bound`

Tests that only assert lower bounds for `call_count` can pass while still
allowing wrong payloads, wrong ordering, or extra calls. This is especially
problematic in facade and orchestration tests where argument correctness is the
main contract.

Flagged forms:

```python
assert mock.call_count >= 1
assert mock.call_count > 0
assert 1 <= mock.call_count
assert 0 < mock.call_count
```

## Approved Strong Patterns

These are not flagged by this detector:

```python
assert mock.call_count == 2
mock.send.assert_called_once_with(recipient=42, body="hello")
```

The first pattern is an exact quantitative contract. The second pattern verifies
payload semantics directly, which is the preferred assertion style for mocked
interactions.

## Scan Modes

The detector supports two modes:

1. `full_repo` scans all Python files under `tests/`.
1. `changed_test_files` scans only test files identified as changed.

Non-test source files are always excluded, even when they contain lookalike
assertions.
