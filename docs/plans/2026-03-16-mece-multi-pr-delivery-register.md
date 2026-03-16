# 2026-03-16 MECE Multi-PR Delivery Register

This register converts the open architecture/provider issue cluster into
non-overlapping PR streams with explicit priority, quick-win status, and
dependency boundaries.

Scope covered in this register:

- `#820` Claude provider
- `#819` MLX provider
- `#816` CI benchmark split
- `#727` parallelism/resource controls
- `#723` llama.cpp provider foundation
- `#720` TUI analytics completion
- `#719` semantic naming quality investigation
- `#715` hybrid retrieval + embedding cache
- `#706` architecture modernization epic

## MECE PR Partition

| PR Stream | Issues | Type | Priority | Quick Win | Wave | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| PR-A: Provider/CI/Epic closeout reconciliation | #723, #816, #706 | Governance closeout | P0 | Yes | 1 | No new provider runtime behavior; reconciles completion claims and dependencies |
| PR-B: MLX provider | #819 | Feature | P1 | No | 2 | Provider integration for Apple-local inference path |
| PR-C: Claude provider | #820 | Feature | P1 | No | 2 | Anthropic cloud provider path |
| PR-D: User-facing parallelism/resource controls | #727 | Feature | P1 | No | 1 | CLI/TUI runtime controls |
| PR-E: Semantic naming quality investigation | #719 | Feature/Experiment | P2 | Yes | 1 | Corpus + benchmark + fallback experiments |
| PR-F: TUI analytics completion | #720 | Feature | P3 | No | 1 | Low-priority UX completion |
| PR-G: Hybrid retrieval + embedding cache | #715 | Feature | P1 | No | 3 | Largest scope; architecture bottleneck for epic closeout |

## Dependency Graph

1. `#819` and `#820` depend on `#723` semantics being final/closed.
2. `#715` is the primary bottleneck for full `#706` completion.
3. Conflict hotspot for `#819` + `#820`: provider registry, provider env wiring, provider literals.

## PR-A Reconciliation Evidence

### #723 (llama.cpp provider foundation)

- Provider registry includes built-in `llama_cpp` registration:
  - `src/file_organizer/models/provider_registry.py`
- Provider environment supports `FO_PROVIDER=llama_cpp`:
  - `src/file_organizer/config/provider_env.py`
- Dedicated model and tests exist:
  - `src/file_organizer/models/llama_cpp_text_model.py`
  - `tests/models/test_llama_cpp_text_model.py`
  - `tests/models/test_provider_registry.py`

### #816 (CI benchmark split)

- Non-benchmark lane exists (`test` job) with benchmark marker exclusion:
  - `.github/workflows/ci.yml`
- Benchmark-only lane exists (`test-benchmark`) with no xdist and benchmark mode:
  - `.github/workflows/ci.yml`
- Path-aware benchmark gating is wired through `dorny/paths-filter`:
  - `.github/workflows/ci.yml`

### #706 (epic bookkeeping stance)

- `#706` remains open while Phase C/D closeout items remain active.
- `#715` remains the long-running architecture bottleneck issue.
- PR-A only reconciles tracking integrity; it does not claim full epic completion.

<!-- MECE_MULTI_PR_DELIVERY_METADATA_START -->
```json
{
  "format_version": 1,
  "generated_on": "2026-03-16",
  "issues_in_scope": [
    706,
    715,
    719,
    720,
    723,
    727,
    816,
    819,
    820
  ],
  "pr_stream_count": 7,
  "pr_streams": [
    {
      "id": "PR-A",
      "issues": [723, 816, 706],
      "type": "governance_closeout",
      "priority": "P0",
      "quick_win": true,
      "wave": 1
    },
    {
      "id": "PR-B",
      "issues": [819],
      "type": "feature",
      "priority": "P1",
      "quick_win": false,
      "wave": 2
    },
    {
      "id": "PR-C",
      "issues": [820],
      "type": "feature",
      "priority": "P1",
      "quick_win": false,
      "wave": 2
    },
    {
      "id": "PR-D",
      "issues": [727],
      "type": "feature",
      "priority": "P1",
      "quick_win": false,
      "wave": 1
    },
    {
      "id": "PR-E",
      "issues": [719],
      "type": "feature_experiment",
      "priority": "P2",
      "quick_win": true,
      "wave": 1
    },
    {
      "id": "PR-F",
      "issues": [720],
      "type": "feature",
      "priority": "P3",
      "quick_win": false,
      "wave": 1
    },
    {
      "id": "PR-G",
      "issues": [715],
      "type": "feature",
      "priority": "P1",
      "quick_win": false,
      "wave": 3
    }
  ],
  "wave_order": {
    "1": ["PR-A", "PR-D", "PR-E", "PR-F"],
    "2": ["PR-B", "PR-C"],
    "3": ["PR-G"]
  },
  "closeout_assertions": {
    "issues_reconciled_now": [723, 816],
    "epic_tracking_issue": 706,
    "epic_bottleneck_issue": 715
  },
  "evidence_paths": {
    "provider_registry": "src/file_organizer/models/provider_registry.py",
    "provider_env": "src/file_organizer/config/provider_env.py",
    "llama_model": "src/file_organizer/models/llama_cpp_text_model.py",
    "ci_workflow": ".github/workflows/ci.yml"
  }
}
```
<!-- MECE_MULTI_PR_DELIVERY_METADATA_END -->
