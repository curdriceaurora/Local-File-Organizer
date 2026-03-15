# Post-814 PR Review Comment Analysis (for #813 + #822 scope fit)

## Scope and Method

- PRs analyzed: `#815`, `#817`, `#818`, `#821` (all PRs with number `> 814` as of 2026-03-15).
- Sources: GitHub review threads, inline review comments, and outside-diff review notes.
- Normalization: duplicate restatements in "prompt for AI agents" sections were deduplicated into single findings.

## High-Level Counts

- PRs analyzed: `4`
- PRs with review findings: `3` (`#815`, `#817`, `#821`)
- Unique findings after deduplication: `19`
- Findings that current #813 scope would catch: `3 / 19` (`15.8%`)
- Findings that planned #813 + #822 scope would catch: `4 / 19` (`21.1%`)
- Findings not covered after #813 + #822: `15 / 19` (`78.9%`)

Interpretation:
- `#822` adds one additional catch from this sample (`#5`), while the other three caught findings already overlap with #813 E coverage.
- Most remaining misses are benchmark-governance and workflow-security policy classes, not observability/import-time fallback classes.

## Per-Finding Mapping

| # | PR | Finding (deduped) | #813 catch? | #813 + #822 catch? | Owner | Notes |
|---|----|--------------------|-------------|---------------------|-------|-------|
| 1 | 815 | Audio suite fallback to IO can mislabel results; require explicit warning/behavior | No | No | — | Benchmark suite semantics; outside current #813/#822 family |
| 2 | 815 | Suite runner alias contract should be pairwise distinct | No | No | — | Benchmark governance contract |
| 3 | 815 | `_BenchmarkModelStub` missing `safe_cleanup()` | No | No | — | Runtime stub API compatibility, outside #813 allowlist |
| 4 | 815 | Text/vision suites should not `fallback_to_all=True` | No | No | — | Benchmark suite correctness |
| 5 | 815 | `OSError` in benchmark corpus copy is silently swallowed | Partial | **Yes** | #822 | #822 explicitly covers equivalent silent swallow patterns |
| 6 | 815 | Bare `except Exception` in hardware detection fallback | **Yes** | **Yes** | #813-E / #822 | Direct observability hit |
| 7 | 815 | Test should assert vision backend pull mock was not called | No | No | — | Test-proof-strength gap |
| 8 | 815 | Smoke schema test missing `hardware_profile`/`stddev_ms` assertions | No | No | — | Benchmark contract completeness |
| 9 | 815 | Outdated test docstring after stronger contract | No | No | — | Documentation hygiene |
| 10 | 815 | Throughput/files_count uses `len(files)` instead of processed subset | No | No | — | Benchmark metric correctness |
| 11 | 815 | Missing `@pytest.mark.smoke` on deterministic smoke contract test | No | No | — | Test/governance policy gap |
| 12 | 815 | `Any` types too broad (`model_type`, synthesized metadata return) | No | No | — | Typing quality |
| 13 | 815 | Audio fallback test should assert delegated args + return value | No | No | — | Test-proof-strength gap |
| 14 | 815 | Redundant local imports (`ModelType`) | No | No | — | Style/refactor |
| 15 | 817 | `_set_status` swallowed exceptions silently | **Yes** | **Yes** | #813-E / #822 | Direct observability hit |
| 16 | 817 | Missing `os.cpu_count() -> None` import-time fallback test | **Yes** | **Yes** | #813-E / #822 | Direct import-time fallback hit |
| 17 | 821 | Workflow should declare explicit token permissions (least privilege) | No | No | — | CI security policy, out of #813/#822 scope |
| 18 | 821 | Third-party action pin to immutable SHA | No | No | — | Supply-chain policy, out of #813/#822 scope |
| 19 | 821 | Add `@claude` mention guard to avoid unnecessary job startup | No | No | — | Workflow efficiency policy |

## Pattern Clusters

### 1) Benchmark Semantics and Metric Truthfulness (`8 findings`)
- Findings: `#1`, `#2`, `#4`, `#8`, `#10`, `#11`, `#13`, `#3` (stub API in benchmark path).
- Theme: suite identity, cardinality correctness, deterministic schema guarantees, and assertion strength.
- Current #813 coverage: none.

### 2) Exception Handling + Observability (`3 findings + 1 near miss`)
- Findings: `#6`, `#15`, and near-miss `#5`.
- Theme: non-fatal exception paths should remain diagnosable.
- Current #813 coverage: broad silent catches and import-time fallback.
- With #822: this cluster is fully covered in this sample (including the specific silent swallow near-miss).

### 3) Workflow Security/Policy (`3 findings`)
- Findings: `#17`, `#18`, `#19`.
- Theme: least-privilege permissions, immutable action pinning, workflow trigger guardrails.
- Current #813 coverage: none (separate policy domain).

### 4) General Test/Type Hygiene (`5 findings`)
- Findings: `#7`, `#9`, `#12`, `#13`, `#14`.
- Theme: stronger behavioral assertions, docs precision, typing specificity.
- Current #813 coverage: minimal.

## What #813 Already Proved Useful For

- It directly explains and covers both new `#817` nits.
- It would have caught the broad-silent hardware detection catch in `#815`.
- Its E-stream direction (diagnostic + import-time ratchet) is validated by real review data.

## Tightening Opportunities (with #822 in plan)

1. **Do not expand #813 E further; execute #822 as the cross-cutting owner for silent-swallow and import-time fallback ratchets.**
   - This avoids duplicate ownership and preserves MECE between issue streams.
   - In this dataset, #822 already captures the only #813 near-miss (`#5`).

2. **Add a narrow #813-C subcontract for fallback label integrity on user-facing runtime/benchmark flows.**
   - Rule: fallback execution must emit explicit signal and must not silently preserve a misleading suite/status label.
   - Would catch findings `#1` and `#4`.

3. **Add #813-D deterministic contract checks for benchmark cardinality/schema truthfulness only if benchmark surfaces are declared in-scope for #813.**
   - Enforce processed-count truthfulness and required schema keys for benchmark outputs.
   - Would catch findings `#8`, `#10`, and partially `#11`.

4. **Do not overload #813 or #822 with workflow supply-chain policy.**
   - Keep `#17/#18/#19` in a separate CI-security issue stream to preserve MECE boundaries.

## Recommended Scope Update Delta for #813

- **Keep A/B unchanged.**
- **E:** keep aligned to observability goals, but defer broad ratchet implementation details to #822 to avoid duplication.
- **C:** add fallback label/degradation signaling contract beyond backend fatal classification.
- **D:** add benchmark output truthfulness only if benchmark subsystem is declared in #813 in-scope; otherwise track in benchmark governance issue.

## Suggested Follow-Up Issues

- New issue (if not already tracked): benchmark output contract ratchet (processed cardinality + required schema keys + smoke marker policy).
- New issue (if not already tracked): GitHub workflow security baseline (permissions + SHA pinning + mention guards).
- Existing linked issue: `#822` (silent-except diagnostics + import-time fallback ratchet).
