---
name: architecture-modernization
status: in-progress
created: 2026-03-10T23:53:38Z
progress: 33%
prd: .claude/prds/architecture-modernization.md
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/706
---

# Epic: Architecture Modernization

## Overview

Modernize the Local File Organizer core architecture based on validated analysis of 14 improvement areas (13 actionable, 1 already implemented). The work decomposes into 9 MECE tasks across 4 phases, progressing from foundational refactoring (God Object decomposition, interface contracts) through infrastructure (benchmarking, model management) to advanced features (RAG search, pipeline prefetch).

Every task has definitely verifiable acceptance criteria — measurable line counts, passing isinstance checks, CLI command outputs, statistical benchmarks, and behavioral tests.

## Architecture Decisions

- **Protocol over ABC for new contracts**: Existing ABCs remain untouched. New contracts use `typing.Protocol` with `@runtime_checkable` — structural subtyping, no inheritance changes required
- **Facade pattern for organizer.py**: Keep `FileOrganizer` as public API; extract 6 internal modules behind it. Zero breaking changes to CLI/API consumers
- **Leverage existing optimization suite**: 12 files / 2,963 LOC already exist in `optimization/`. Integrate `batch_sizer.py` (currently unused) rather than building from scratch
- **Hardware profile informs defaults**: Auto-select model size and worker count at startup, but always allow user override via config

## Technical Approach

### Foundation Layer (Phase A — no dependencies)

**Task 1: Core Decomposition** — Break `organizer.py` (934 lines, 7 concerns) into 5 focused modules. FileOrganizer becomes thin facade < 200 lines. Eliminates God Object anti-pattern.

**Task 2: Interface & Engine Contracts** — Populate empty `interfaces/` directory with Protocol classes for models, processors, storage, intelligence, and pipeline stages. Additive — no existing code changes. (EngineProtocol was planned but deleted — zero implementors.)

**Task 3: Hardware Profiling** — New `core/hardware_profile.py` + CLI command. Detects GPU/RAM/cores, recommends model size and worker count. Extends existing `ResourceMonitor` (which only covers NVIDIA + basic memory).

### Infrastructure Layer (Phase B — depends on Phase A)

**Task 4: Benchmarking Suite** — New `cli/benchmark.py` with suite selection, warmup, statistical reporting (median/p95/p99/stddev), JSON output, hardware profile inclusion. Currently zero benchmark infrastructure exists.

**Task 5: Model Lifecycle** — Two sub-deliverables: (a) domain-specific registries (text/vision/audio) with domain metadata fields, (b) `ModelManager.swap_model()` with drain/pre-warm/rollback semantics. Builds on engine protocol from Task 2.

**Task 6: Composable Pipeline** — Extract 4 pipeline stages (preprocess/analyze/postprocess/write) from monolithic orchestrator. Stages are independently testable, skippable, replaceable. Orchestrator composes via stage list.

### Advanced Features (Phase C — depends on Phases A-B)

**Task 7: Double-Buffered Processing** — Add I/O-compute overlap to pipeline: prefetch next file while current file's LLM inference runs. Configurable prefetch depth, bounded by memory limiter.

**Task 8: Proactive Memory Management** — `BufferPool` with acquire/release, batch_sizer integration into pipeline, dynamic pool resizing based on resource monitor feedback.

### High-Effort Features (Phase D — depends on Phases A-C)

**Task 9: Hybrid Retrieval with Embedding Cache** — BM25 + vector search with score fusion. Persistent embedding cache (SQLite). Replaces current keyword-only search (tiered scoring, max 10K files). Copilot integration for context gathering.

## Implementation Strategy

### Phased Execution

```
Phase A (Foundation):  Tasks 1, 2, 3  — parallelizable, no cross-deps
Phase B (Infrastructure): Tasks 4, 5, 6 — sequential within phase
Phase C (Advanced):    Tasks 7, 8      — depends on Tasks 6, 3
Phase D (High-effort): Task 9          — depends on Tasks 2, 5
```

### Risk Mitigation

- **Behavioral regression**: Every task requires "existing CLI behavior unchanged" verification
- **God Object extraction**: Incremental — extract one concern at a time, test after each
- **Protocol adoption**: Additive only — existing ABCs stay, Protocols layer on top
- **Benchmark flakiness**: Statistical reporting (p95/p99) + warmup exclusion prevents CI flakiness

### Testing Approach

- Each task defines 4-6 verifiable acceptance criteria
- Protocol conformance tested via `isinstance()` runtime checks
- Benchmark correctness tested via synthetic known-value inputs
- Pipeline stages tested independently + composed

## Task Breakdown

- [x] Task 1: Core Decomposition — organizer.py God Object extraction (PRD Topics 1)
- [x] Task 2: Interface & Engine Contracts — Protocol definitions (PRD Topics 2, 11; EngineProtocol deleted — zero implementors)
- [x] Task 3: Hardware Profiling — startup detection + model auto-selection (PRD Topic 3)
- [x] Task 4: Benchmarking Suite — CLI command + statistical reporting (PRD Topic 6)
- [x] Task 5: Model Lifecycle — domain registries + hot-swap (PRD Topics 4, 7)
- [x] Task 6: Composable Pipeline — stage extraction + orchestrator refactor (PRD Topic 12)
- [ ] Task 7: Double-Buffered Processing — I/O-compute overlap (PRD Topic 9)
- [ ] Task 8: Proactive Memory Management — buffer pool + batch_sizer integration (PRD Topic 8)
- [ ] Task 9: Hybrid Retrieval + Embedding Cache — BM25 + vector + cache (PRD Topics 5, 14)

## Dependencies

- **Internal**: Task 2 (interfaces) before Tasks 5, 9. Task 1 (decomposition) before Task 6. Task 3 (hardware) before Tasks 4, 8.
- **External**: None — all work uses existing frameworks (Typer, FastAPI, Rich, Ollama)
- **Packages**: Task 9 may require `rank-bm25`, `numpy`, `sqlite3` (stdlib). Task 3 may require `psutil` (already a dependency).

## Success Criteria (Technical)

- `organizer.py` < 200 lines (from 934)
- 4+ Protocol files in `interfaces/` with runtime conformance tests
- `file-organizer hardware-info` CLI command works on macOS + Linux
- `file-organizer benchmark --suite text --json` produces valid statistical output
- Model swap with rollback tested (success + failure paths)
- Pipeline stages independently composable (skip/replace any stage)
- Hybrid search recall@10 > keyword-only on test corpus
- All existing `pytest -m ci` tests continue passing after each task

## Estimated Effort

- **Phase A (Tasks 1-3)**: 3-5 days — parallelizable
- **Phase B (Tasks 4-6)**: 4-6 days — some sequential
- **Phase C (Tasks 7-8)**: 2-3 days
- **Phase D (Task 9)**: 3-5 days — highest complexity
- **Total**: 12-19 days
- **Critical path**: Task 2 → Task 5 → Task 9 (interface → model lifecycle → RAG)

## Tasks Created

- [x] #710 - Core Decomposition — organizer.py God Object Extraction (parallel: true, size: L) ✅ DONE
- [x] #711 - Interface & Engine Contracts — Protocol Definitions (parallel: true, size: M) ✅ DONE
- [x] #712 - Hardware Profiling — Startup Detection & Model Auto-Selection (parallel: true, size: S) ✅ DONE
- [x] #707 - Benchmarking Suite — CLI Command & Statistical Reporting (parallel: false, depends: #712, size: M) ✅ DONE
- [x] #708 - Model Lifecycle — Domain Registries & Hot-Swap (parallel: false, depends: #711, size: L) ✅ DONE
- [x] #709 - Composable Pipeline — Stage Extraction & Orchestrator Refactor (parallel: false, depends: #710, size: M) ✅ DONE
- [ ] #713 - Double-Buffered Processing — I/O-Compute Overlap (parallel: true, depends: #709, size: M)
- [ ] #714 - Proactive Memory Management — Buffer Pool & Batch Sizer Integration (parallel: true, depends: #712, size: M)
- [ ] #715 - Hybrid Retrieval with Embedding Cache — BM25 + Vector Search (parallel: false, depends: #711+#708, size: XL)

Total tasks: 9
Parallel tasks: 5 (#710, #711, #712, #713, #714)
Sequential tasks: 4 (#707, #708, #709, #715)
Estimated total effort: 94-116 hours

## Excluded (Already Implemented)

**Token Budget Context Management**: `services/copilot/conversation.py` already has sliding-window context with 3,800 token budget, 6-turn retention, and summary eviction. No work needed.

**TUI Dashboard (Deferred)**: `analytics_view.py` partially covers this. Deferred to a separate low-priority epic to keep this one focused on core architecture. Can be tracked independently.
