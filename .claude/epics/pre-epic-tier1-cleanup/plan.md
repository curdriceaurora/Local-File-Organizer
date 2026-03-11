# Pre-Epic Tier 1 Cleanup Plan

**Branch**: `fix/pre-epic-tier1-cleanup`
**Purpose**: Resolve blocking and tech-debt issues before starting Epic #706 (Architecture Modernization) to minimize throwaway work.
**Created**: 2026-03-11

---

## Issues

| Priority | Issue | Title | Effort | Throwaway Risk if Deferred |
|----------|-------|-------|--------|---------------------------|
| 1 | #725 | VRAM exhaustion — lazy model init | Medium | High — Epic Task #710 rewrites organizer.py; a full solution now gets discarded. Minimal lazy-init flag is safe. |
| 2 | #691 | CI failing on main | Low | Blocking — red CI blocks all PRs |
| 3 | #697 | Dual `__version__` declaration | Trivial | Low — but epic touches `__init__.py`, cleaner to fix now |
| 4 | #683 | glib Rust crate security advisory | Low | None — security fix, independent of epic |

---

## Parallelizability

```
             ┌─────────────────────┐
             │ #691 Verify CI      │──► If broken, fix (blocking)
             │ (investigate only)  │    If green, close
             └─────────────────────┘
                       │ CI confirmed green
                       ▼
    ┌──────────────────────────────────────────┐
    │         PARALLEL BATCH                   │
    │                                          │
    │  #697 __version__    #683 glib Rust      │
    │  (Python only)       (Rust/Cargo only)   │
    │  No file overlap     No file overlap     │
    └──────────────────────────────────────────┘
                       │ both complete
                       ▼
             ┌─────────────────────┐
             │ #725 Lazy model     │
             │ init (organizer.py) │
             └─────────────────────┘
```

- **#691** must be verified first — red CI blocks everything
- **#697 and #683** are fully independent (Python vs Rust, zero file overlap) — can be done in parallel
- **#725** goes last — it touches `organizer.py` which is the most complex change and benefits from a green, clean baseline

---

## Execution Order & Approach

### 1. #691 — Verify CI Status

**Action**: Check if failures are still present on main.

- Main CI is currently green (as of 2026-03-11)
- Failures listed in #691: TUI `NoActiveAppError`, `PatternLearner` mock mismatches, `SettingsRepository.test_set_none_value`, `test_marker_documented[no_ollama]`, `test_api_health`
- **If still failing**: Fix the specific tests
- **If already fixed**: Close #691 as resolved

### 2. #697 + #683 — Parallel Batch

#### #697 — Dual `__version__` Cleanup

**Action**: Remove duplicate `__version__` declaration.

- `src/file_organizer/__init__.py` and `src/file_organizer/version.py` both declare `__version__`
- Fix: Import from `version.py` in `__init__.py` instead of redeclaring
- 5-minute change, no risk
- **Files touched**: `src/file_organizer/__init__.py`

#### #683 — glib Rust Crate Security Fix

**Action**: Upgrade glib Rust crate to >= 0.20.0 (GHSA-wrw7-89jp-8q8g).

- Security advisory on Rust dependency
- Update in `Cargo.toml` / `Cargo.lock` for the Tauri desktop app
- No Python code impact
- **Files touched**: `desktop/src-tauri/Cargo.toml`, `desktop/src-tauri/Cargo.lock`

**Why parallel**: Zero file overlap between #697 (Python `__init__.py`) and #683 (Rust `Cargo.toml`). No shared state or dependencies.

### 3. #725 — VRAM Exhaustion (Minimal Lazy Init)

**Action**: Add lazy model initialization to prevent dual-model VRAM exhaustion.

**Scope (minimal — designed to be absorbed by Epic Task #710)**:
- Add `lazy_init: bool = True` to `FileOrganizer.__init__()`
- Defer `TextProcessor.initialize()` and `VisionProcessor.initialize()` until first use
- Each processor initializes on first `process_file()` call
- No architectural changes — just defer the `.initialize()` calls
- **Files touched**: `src/file_organizer/core/organizer.py`, related tests

**What NOT to do** (Epic #710 handles these):
- Do NOT decompose `organizer.py` into modules
- Do NOT add VRAM detection (Epic Task #712)
- Do NOT add model scheduling or swapping (Epic Task #708)
- Do NOT refactor the processor lifecycle

**Why last**: Most complex change, benefits from clean baseline. Epic Task #710 extracts organizer.py from 934 → <200 lines. Any structural work here gets rewritten. The lazy-init flag is a behavioral change that the decomposed version will preserve.

---

## Relationship to Epic #706

```
Tier 1 (this branch)          Epic #706 Phase A
─────────────────────         ──────────────────────
#697 __version__ cleanup  →   Clean __init__.py for epic
#683 security fix         →   Independent, no conflict
#691 CI fix               →   Green CI required for epic PRs
#725 lazy init (minimal)  →   Absorbed by Task #710 (decomposition)
                              + Task #712 (hardware profiling)
```

**Key principle**: Every change here is either independent of the epic or designed to be cleanly absorbed by it. Zero throwaway work.

---

## Deferred Issues (NOT in this branch)

| Issue | Why Deferred |
|-------|-------------|
| #723 (llama.cpp provider) | Needs plugin registration from Epic Task #711 |
| #727 (parallelism controls) | Epic Tasks #709 + #712 redesign this entirely |
| #720 (TUI dashboard) | Standalone, explicitly deferred by epic |
| #719 (semantic naming) | Research task, no urgency |
| #737, #738, #739, #731 | Testing debt — do anytime, no conflict |
| #693, #694 | Test assertion improvements — do anytime |

---

## Exit Criteria

- [x] #691 — Closed (all tests pass on main, CI green)
- [x] #697 — Fixed (`__init__.py` imports from `version.py`)
- [ ] #683 — Deferred (blocked on upstream `gtk-rs 0.20+` migration)
- [x] #725 — Fixed (sequential model init: text → cleanup → vision)
- [x] Main CI green
- [x] `pre-commit run --all-files` passes (12/12 hooks)
- [x] No regressions (132 integration + 37 organizer unit tests pass)
- [ ] PR created and merged before starting Epic Phase A
