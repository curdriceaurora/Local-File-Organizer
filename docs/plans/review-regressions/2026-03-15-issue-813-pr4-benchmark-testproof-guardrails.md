# Issue #813 PR-4: Benchmark Contract/Test-Proof Guardrails

## Why This PR Exists

Workstream **G** in #813 owns benchmark schema + test-proof quality guardrails.
This PR converts review-time expectations into enforced CI checks.

## Guardrails Added

1. Benchmark payload contract (live runtime output):
- Enforce required top-level fields including `hardware_profile`.
- Enforce required metric fields including `stddev_ms`.

2. Deterministic smoke contract marker hygiene:
- Enforce `pytest.mark.smoke`, `pytest.mark.ci`, and `pytest.mark.unit` on the benchmark schema smoke test.

3. Fallback/delegation test-proof contract:
- Enforce that audio fallback tests prove delegated call arguments via `assert_called_once_with(...)`.
- Enforce that those tests also assert returned payload (`result.processed_count`), not just warning text.

4. Benchmark stub cleanup interface parity:
- Enforce that stub cleanup parity test calls `model.safe_cleanup()`.
- Enforce pre/post initialization state assertions (`is_initialized is True` then `False`).

## Contract Evidence (Tests)

- `tests/ci/test_benchmark_contracts.py`
  - `test_live_benchmark_payload_contains_required_runtime_fields`
- `tests/ci/test_benchmark_testproof_guardrails.py`
  - `test_smoke_schema_test_has_required_pytest_markers`
  - `test_audio_fallback_test_proves_delegation_call_and_result_contract`
  - `test_benchmark_stub_cleanup_parity_test_enforces_pre_and_post_state`

## Local Verification

```bash
pytest tests/ci/test_benchmark_contracts.py tests/ci/test_benchmark_testproof_guardrails.py tests/cli/test_benchmark_suite_runners.py -q --no-cov --override-ini="addopts="
bash .claude/scripts/pre-commit-validation.sh
```
