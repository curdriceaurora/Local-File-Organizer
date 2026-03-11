---
name: architecture-modernization
description: Decompose, formalize, and modernize the core architecture — inspired by rcli patterns, validated against actual codebase state
status: backlog
created: 2026-03-10T23:50:03Z
updated: 2026-03-10T23:50:03Z
---

# PRD: Architecture Modernization

## Problem Statement

Local File Organizer v2.0 has grown to ~78,800 LOC across 314 modules. A comparative analysis against [rcli](https://github.com/RunanywhereAI/rcli) revealed 14 architectural improvement opportunities. Each has been validated against the actual codebase. This PRD captures the 13 actionable items (1 was already implemented) with verifiable acceptance criteria.

## Goals

1. Reduce `organizer.py` from 934 lines / 7 mixed concerns to focused modules
2. Formalize service contracts via Protocol/ABC interfaces
3. Add hardware-aware model selection at startup
4. Enable model hot-swapping without service restart
5. Introduce hybrid retrieval (BM25 + vector) for intelligent search
6. Create a benchmarking CLI with statistical rigor
7. Split model registry by domain for domain-specific validation
8. Add proactive memory management for batch processing
9. Enable I/O-compute overlap via double-buffered processing
10. Unify TUI into a dashboard home screen
11. Formalize engine abstraction across all services
12. Make pipeline stages composable and parallelizable

## Non-Goals

- Token budget context management (already implemented in copilot/conversation.py)
- Rewriting existing working services from scratch
- Changing the CLI framework (Typer stays)
- Changing the web framework (FastAPI stays)

## MECE Topic Decomposition

### Topic 1: Core Decomposition — organizer.py

**Current State**: `core/organizer.py` is 934 lines with `FileOrganizer` class mixing 7 concerns: orchestration, configuration, initialization, business logic (4 file types), file I/O, UI/display (Rich), error handling/degradation. 28 imports, 11 tight couplings, 5 inline service instantiations.

**Target State**: `FileOrganizer` becomes a thin facade (<200 lines) delegating to:
- `core/initializer.py` — startup, dependency wiring
- `core/dispatcher.py` — file routing and type dispatch
- `core/types.py` — shared type definitions (OrganizationResult, etc.)
- `core/display.py` — Rich UI output (progress, summary, tables)
- `core/file_ops.py` — collect, organize, simulate, cleanup operations

**Verifiable Artifacts**:
- [ ] `organizer.py` < 200 lines
- [ ] Each extracted module has `pytest -m ci` tests passing
- [ ] No inline service instantiation in `FileOrganizer.__init__` (all injected or factory-created)
- [ ] `ruff check` and `mypy --strict` pass on all new modules
- [ ] Existing CLI behavior unchanged: `file-organizer organize --help` output identical

### Topic 2: Interface/Implementation Separation

**Current State**: `src/file_organizer/interfaces/__init__.py` is 2 lines (empty). Project uses ABC pattern (BaseModel, Plugin, Integration). No formal contracts for processors, storage, or intelligence services.

**Target State**: `interfaces/` defines Protocol classes for all major service boundaries:
- `interfaces/model.py` — `TextModelProtocol`, `VisionModelProtocol`, `AudioModelProtocol`
- `interfaces/processor.py` — `FileProcessorProtocol`, `BatchProcessorProtocol`
- `interfaces/storage.py` — `StorageProtocol`, `CacheProtocol`
- `interfaces/intelligence.py` — `LearnerProtocol`, `ScorerProtocol`

**Verifiable Artifacts**:
- [ ] 4+ Protocol files in `interfaces/` with `@runtime_checkable` decorators
- [ ] Existing implementations satisfy their protocols (`isinstance(TextModel(), TextModelProtocol)` returns True)
- [ ] `mypy --strict` passes with Protocol-based type annotations
- [ ] Tests verify protocol conformance for each implementation
- [ ] No ABC changes required — Protocols are structural, additive

### Topic 3: Hardware Profiling at Startup

**Current State**: `optimization/resource_monitor.py` (290 LOC) detects memory/GPU basics via psutil and nvidia-smi. Missing: Apple MPS detection, CPU core counting, VRAM allocation tracking, auto-model selection based on hardware.

**Target State**: `core/hardware_profile.py` runs at startup and produces a `HardwareProfile` dataclass:
- GPU type (NVIDIA/Apple MPS/AMD/None) + VRAM
- Available RAM + CPU cores
- Recommended model size (3b/7b/13b) based on available resources
- Recommended worker count for parallel processing

**Verifiable Artifacts**:
- [ ] `file-organizer hardware-info` CLI command prints detected hardware profile
- [ ] Auto-selects `qwen2.5:3b` on systems with < 8GB RAM
- [ ] Auto-selects `qwen2.5:7b` on systems with >= 16GB RAM
- [ ] `parallel/config.py` uses detected CPU cores for worker count default
- [ ] Tests mock psutil/subprocess to verify detection logic for NVIDIA, Apple MPS, and no-GPU scenarios
- [ ] Startup log line: `INFO: Hardware profile: {gpu_type}, {vram}GB VRAM, {ram}GB RAM, {cores} cores`

### Topic 4: Model Hot-Swapping

**Current State**: BaseModel has `initialize()`, `generate()`, `cleanup()` lifecycle. No atomic swap, no request draining, no pre-warm, no rollback on failure. ModelCache uses OrderedDict with threading.Lock.

**Target State**: `ModelManager.swap_model(model_type, new_model_id)` performs:
1. Pre-warm new model (initialize + health check)
2. Drain in-flight requests (wait for completion)
3. Atomic swap (old model reference replaced)
4. Cleanup old model
5. Rollback on failure (keep old model if new one fails health check)

**Verifiable Artifacts**:
- [ ] `ModelManager.swap_model()` method exists with type annotations
- [ ] Test: swap succeeds — new model serves requests after swap
- [ ] Test: swap fails — old model continues serving (rollback)
- [ ] Test: in-flight request completes before old model cleanup
- [ ] Thread-safety: concurrent `generate()` calls during swap don't crash
- [ ] No user-facing API change — CLI users unaffected

### Topic 5: Hybrid Retrieval (BM25 + Vector Search) with Embedding Cache

**Current State**: `api/routers/search.py` uses keyword-based search with tiered scoring (exact=1.0, stem=0.7, extension=0.5, path=0.3). Max 10,000 file traversal. No vector/embedding/BM25 infrastructure. Intelligence layer (19 files) is preference-based, not search-based. No embedding cache exists.

**Target State**: `services/search/` module with:
- `bm25_index.py` — keyword-based retrieval with TF-IDF scoring
- `vector_index.py` — embedding-based semantic similarity
- `hybrid_retriever.py` — score fusion combining both
- `embedding_cache.py` — persistent cache for file content embeddings

**Verifiable Artifacts**:
- [ ] `file-organizer search "quarterly report" --semantic` returns semantically relevant results
- [ ] BM25 index builds in < 5s for 10,000 files
- [ ] Vector search returns files with cosine similarity > 0.7 for relevant queries
- [ ] Hybrid mode outperforms keyword-only on a 100-file test corpus (measured recall@10)
- [ ] Embedding cache persists to disk (SQLite or pickle) and survives restarts
- [ ] Cache hit rate > 90% on second search of same corpus
- [ ] Copilot suggestions use hybrid retrieval for context gathering

### Topic 6: Benchmarking Suite

**Current State**: No `cli/benchmark.py` exists. MemoryProfiler (286 LOC) collects per-function data but no aggregation. ParallelProcessor calculates fps but doesn't persist.

**Target State**: `file-organizer benchmark` CLI command with:
- Suite selection: `--suite text,vision,audio,pipeline,e2e`
- Warmup runs excluded from measurement
- Statistical reporting: median, p95, p99, std dev, throughput
- JSON output for CI regression detection
- Hardware profile included in results

**Verifiable Artifacts**:
- [ ] `file-organizer benchmark --help` shows available suites and options
- [ ] `file-organizer benchmark --suite text --json` produces valid JSON with fields: `median_ms`, `p95_ms`, `p99_ms`, `stddev_ms`, `throughput_fps`
- [ ] Warmup: first 3 iterations excluded from stats
- [ ] Results include `hardware_profile` section matching Topic 3 output
- [ ] `file-organizer benchmark --compare baseline.json` shows delta and regression flag
- [ ] Test: statistical output is correct for a known set of synthetic timings

### Topic 7: Domain-Specific Model Registries

**Current State**: Single `models/registry.py` with static `AVAILABLE_MODELS` list. `ModelManager` filters by `model_type` string. No domain-specific validation (e.g., vision model doesn't declare supported image formats).

**Target State**: Registry split with domain-specific metadata and validation:
- `models/text_registry.py` — context window, token limits, supported languages
- `models/vision_registry.py` — supported image formats, max resolution
- `models/audio_registry.py` — supported audio formats, sample rates, max duration
- `models/registry.py` — unified facade querying all domain registries

**Verifiable Artifacts**:
- [ ] Each domain registry file exists with domain-specific `ModelInfo` subclass
- [ ] `TextModelInfo` has `context_window: int` and `max_tokens: int` fields
- [ ] `VisionModelInfo` has `supported_formats: list[str]` and `max_resolution: tuple[int, int]`
- [ ] `AudioModelInfo` has `supported_formats: list[str]` and `max_duration_seconds: int`
- [ ] Unified `registry.py` facade delegates to domain registries
- [ ] `file-organizer models list --type vision` shows domain-specific metadata
- [ ] Tests validate that all registered models have required domain fields

### Topic 8: Proactive Memory Management

**Current State**: `optimization/` has 12 files (2,963 LOC) — resource_monitor, memory_profiler, model_cache, batch_sizer, memory_limiter, leak_detector, etc. All reactive (detect pressure, evict). No pre-allocation or arena allocation.

**Target State**: Add proactive allocation for predictable workloads:
- `optimization/buffer_pool.py` — pre-allocated read buffers for file processing
- Integrate `batch_sizer.py` into pipeline (currently unused)
- Dynamic pool sizing based on `resource_monitor` feedback

**Verifiable Artifacts**:
- [ ] `BufferPool` class with `acquire(size)` and `release(buffer)` methods
- [ ] Pool pre-allocates N buffers at startup (configurable, default 10 x 1MB)
- [ ] Test: 1000-file batch with pool uses < 50% GC time vs without pool
- [ ] `batch_sizer.py` integrated into `PipelineOrchestrator.process_batch()`
- [ ] Resource monitor triggers pool resize when memory pressure > 85%
- [ ] No memory leak: pool size returns to baseline after batch completes

### Topic 9: Double-Buffered Processing Pipeline

**Current State**: `PipelineOrchestrator.process_batch()` (424 LOC) processes files sequentially — each file waits for previous to complete. `ParallelProcessor` has bounded futures (2x workers) but no I/O-compute overlap.

**Target State**: Overlap I/O-bound work (file reading, disk writes) with compute-bound work (LLM inference):
- While current file's LLM analysis runs, pre-read next file
- While current batch writes to disk, start loading next batch
- Configurable prefetch depth (default 2)

**Verifiable Artifacts**:
- [ ] `PipelineOrchestrator` has `prefetch_depth` parameter (default 2)
- [ ] Test: 10-file batch with prefetch is >= 20% faster than without (measured wall clock)
- [ ] Test: prefetch doesn't exceed `memory_limiter` threshold
- [ ] Test: error in prefetched file doesn't crash pipeline
- [ ] `--no-prefetch` CLI flag disables overlap for debugging
- [ ] ParallelProcessor futures correctly bounded with prefetch enabled

### Topic 10: Consolidated TUI Dashboard

**Current State**: 10 TUI views in separate files. `analytics_view.py` (9.2K) is closest to a dashboard but focused on analytics only. No unified home screen.

**Target State**: `tui/dashboard.py` — single-pane home screen showing:
- Active jobs with progress
- Recent activity (last 10 organized files)
- Model status (loaded, available, memory usage)
- Disk usage summary
- Quick-action bar (organize, search, undo, settings)

**Verifiable Artifacts**:
- [ ] `tui/dashboard.py` file exists with `DashboardView` class
- [ ] Dashboard is the default view when launching `file-organizer tui`
- [ ] Shows real-time progress for active organization jobs
- [ ] Shows model status from `ModelManager.cache_info()`
- [ ] Quick-action bar navigates to existing views (file_browser, copilot, etc.)
- [ ] Test: DashboardView renders without errors on empty state (no files organized yet)

### Topic 11: Engine Abstraction Layer

**Current State**: BaseModel has `initialize()`, `generate()`, `cleanup()` lifecycle. Plugin has `on_load/enable/disable/unload`. Integration has `connect/disconnect`. No unified engine interface across all service types.

**Phase A Outcome (2026-03-11)**: `EngineProtocol` was designed but DELETED during implementation — its method names (`init`/`shutdown`/`process`) didn't match any existing implementation (`initialize`/`generate`/`cleanup`). The existing `TextModelProtocol`, `VisionModelProtocol`, and `AudioModelProtocol` already cover the model lifecycle contract. A unified engine protocol is deferred to Phase B/C if cross-cutting lifecycle management is needed.

**Verifiable Artifacts**:
- [x] Evaluated EngineProtocol — determined zero implementors exist
- [x] Deleted `interfaces/engine.py` (method mismatch with all existing classes)
- [ ] Deferred: unified engine protocol across service types (Phase B/C if needed)

### Topic 12: Composable Pipeline Stages

**Current State**: `pipeline/orchestrator.py` (424 LOC) handles routing, processing, and file operations in one class. `pipeline/router.py` handles file type routing. Sequential execution.

**Target State**: Pipeline as composable stages:
- `pipeline/stages/preprocessor.py` — file validation, metadata extraction
- `pipeline/stages/analyzer.py` — LLM analysis (text/vision/audio)
- `pipeline/stages/postprocessor.py` — file naming, folder assignment
- `pipeline/stages/writer.py` — file move/copy operations
- Each stage is independently testable and can be skipped/replaced

**Verifiable Artifacts**:
- [ ] Each stage file exists with a `PipelineStage` protocol implementation
- [ ] `PipelineOrchestrator` composes stages via list (not hardcoded method calls)
- [ ] Test: custom pipeline with only preprocessor + writer (skip analyzer) works
- [ ] Test: adding a custom stage (e.g., dedup check) doesn't require orchestrator changes
- [ ] Existing behavior unchanged: `file-organizer organize` produces same results
- [ ] Stage execution order configurable via config

## Already Implemented (No Issue Needed)

### Token Budget Context Management
**Status**: ALREADY IMPLEMENTED in `services/copilot/conversation.py`
- Sliding window: 3,800 token budget (Qwen 2.5 3B has 4,096 context)
- Keeps 6 turns in full fidelity
- Evicted messages summarized into compact context string
- Heuristic: ~4 chars/token for trimming
- No further work needed.

## Priority Matrix

| # | Topic | Impact | Effort | Priority | Dependencies |
|---|-------|--------|--------|----------|-------------|
| 1 | Core Decomposition | High | Medium | P1 | None |
| 2 | Interface Separation | High | Medium | P1 | None |
| 3 | Hardware Profiling | High | Low | P1 | None |
| 6 | Benchmarking Suite | Medium | Medium | P1 | Topic 3 (hardware profile in output) |
| 11 | Engine Abstraction | Medium | Medium | P2 | Topic 2 (interfaces) |
| 7 | Domain Registries | Medium | Low | P2 | None |
| 4 | Model Hot-Swapping | High | High | P2 | Topic 11 (engine protocol) |
| 12 | Pipeline Stages | Medium | Medium | P2 | Topic 1 (core decomposition) |
| 9 | Double-Buffered Pipeline | Medium | Medium | P2 | Topic 12 (pipeline stages) |
| 8 | Proactive Memory | Medium | Medium | P3 | Topic 3 (hardware profile) |
| 5 | Hybrid Retrieval (RAG) | High | High | P3 | Topic 2 (interfaces), Topic 11 (engine) |
| 10 | TUI Dashboard | Low | Medium | P3 | None |

## Recommended Execution Order

```
Phase A (Foundation — no dependencies):
  3 → 1 → 2 (in parallel: hardware, decomposition, interfaces)

Phase B (Core infrastructure — depends on Phase A):
  6 → 11 → 7 → 12 (benchmarks, engine protocol, registries, pipeline stages)

Phase C (Advanced features — depends on Phase B):
  4 → 9 → 8 (hot-swap, double-buffer, memory management)

Phase D (High-effort features — depends on Phases A-C):
  5 → 10 (hybrid retrieval, TUI dashboard)
```
