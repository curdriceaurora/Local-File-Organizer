# fo-core Fork Evaluation — Pull-Back Assessment

**Date:** 2026-06-13
**Original:** `local-file-organizer` (v2.0.0-alpha.3, package `src/file_organizer/`)
**Fork:** [`curdriceaurora/fo-core`](https://github.com/curdriceaurora/fo-core) (v2.0.0-beta.10, package `src/`)

This report evaluates what features, tests, and hardening from the `fo-core`
fork can be pulled back into the original repository. It is the synthesis of a
file-level diff plus four focused code reviews (fork-only modules, in-place
hardening of shared files, test suite, and CI/tooling).

---

## 1. Executive Summary

`fo-core` is a **deliberate down-scoping** of this repo into a tight, CLI-only,
local-AI file organizer. The fork:

- **Dropped the entire networked/UI surface** (~130 files): `api/`, `web/`,
  `desktop/`, `tui/`, `client/`, `plugins/`, `deploy/`, `review_regressions/`.
- **Flattened** `src/file_organizer/` → `src/`.
- **Added 25 new core modules** (~7.4k LOC) and **hardened a large share of the
  278 shared modules**, advancing from alpha to `2.0.0-beta.10`.

The fork's distinguishing value is a **coherent path-safety + crash-safety
hardening program** that does **not exist in the original at all** — the
original tree has no `safedir.py`, no `path_guard.py`, and zero
`O_NOFOLLOW`/`SafeDir`/`SymlinkRejected` usage anywhere. This, plus atomic-write
durability, undo durability, an error taxonomy, and the CI "rails" that lock all
of it in, are the highest-value pull-backs and are cleanly scoped to the core
engine (no api/web/tui coupling).

**Recommendation:** Pull back in phases, foundation-first. The hardening and its
guarding tests/rails travel together. The dropped server/UI surface is *not* a
regression to restore — it is out of scope for the fork and irrelevant to the
pull-back.

---

## 2. Scope Delta (what is and isn't a candidate)

| Area | Status | Pull-back relevance |
|------|--------|--------------------|
| `api/`, `web/`, `desktop/`, `tui/`, `client/`, `plugins/`, `deploy/` | Dropped by fork | **N/A** — original keeps these; fork has no improvements here |
| `review_regressions/` | Dropped by fork | Keep original's; fork *lacks* some security detectors that live here |
| Core engine (`core/`, `pipeline/`, `services/`, `models/`, `undo/`, `utils/`, `parallel/`, `watcher/`, `config/`, `methodologies/`) | Hardened + extended | **Primary pull-back target** |
| Dev tooling (`.pre-commit-config.yaml`, `scripts/`, `.github/workflows/`, `SECURITY.md`) | Significantly hardened | **High-value pull-back** |

**Universal caveat:** every pull-back must be re-targeted from the fork's
flattened `src/` layout to the original's `src/file_organizer/` layout (import
paths, hook path globs, rail scripts, rule-doc references).

---

## 3. Hardening (highest value)

The original has **none** of the symlink/TOCTOU hardening series. Most file-level
fixes are call sites that thread a new primitive through read/dedup/undo/write
paths, so the primitive must come first.

### 3.1 Foundation modules (fork-only — pull back FIRST)

| Module | What it provides | Value |
|--------|------------------|-------|
| `utils/safedir.py` (579 LOC) | POSIX `dir_fd` + `O_NOFOLLOW` primitive; operates on path *components* (rejects `/`, `..`, `.`, NUL); typed `SymlinkRejected`; fd lifetime via context manager. TOCTOU-safe. | **5 (prerequisite)** |
| `core/path_guard.py` (202 LOC) | `validate_within_roots` + `safe_walk` (symlink/hidden filtering) + `PathTraversalError`. | **5** |
| `utils/atomic_write.py` (331 LOC) | Crash-safe temp+fsync+`os.replace` writers (`atomic_write_text/bytes/with`, `append_durable`). Note: original already has an identical `utils/atomic_io.py`, so this is incremental. | **5** |
| `utils/log_redact.py` (474 LOC) | Process-wide credential-redacting logging filter (stdlib + loguru), fail-closed. | **5** |
| `undo/durable_move.py` (1551 LOC) + `undo/_journal.py` + `undo/trash_gc.py` (541 LOC) | Atomic same-device / EXDEV-durable cross-device move with crash-recoverable JSONL journal + sweep; race-safe trash GC under `LOCK_EX`. Pull back as a unit. | **5** |
| `core/error_taxonomy.py` (173 LOC) | `classify_error` → 5 buckets + operator recommendations. Pure, decoupled. | **5** |
| `utils/cli_errors.py` (55 LOC) | Hint-rich validation errors with difflib "did you mean". Zero coupling. | **5** |
| `cli/path_validation.py` (147 LOC) | `resolve_cli_path` / `validate_pair` CLI-boundary path checks (typer-coupled). | **4** |

### 3.2 Shared-file call sites (pull back AFTER the foundation)

These existing files were hardened in-place; they depend on `safedir.py` /
`path_guard.py` / `durable_move`.

| File | Hardening | Value |
|------|-----------|-------|
| `services/text_processor.py` | Untrusted-file→LLM read routed through `read_file_via_safedir_anchored` (every ancestor `O_NOFOLLOW`); refuses symlink reads. Closes exfiltration window (#264/#286). | **5** |
| `pipeline/stages/writer.py` | `shutil.copy2` → `SafeDir.open_child(O_NOFOLLOW)`; fd-based `fchmod`/`utime` instead of path-reopening `copystat` (#322/#354). | **5** |
| `undo/rollback.py` | All moves via durable/atomic `_move()`; inode anti-swap verification (`st_dev/st_ino`); refuses replay on mismatch. | **5** |
| `undo/undo_manager.py` | Status flips wrapped in DB transactions (fixes write/commit race, B3); all-or-nothing redo. | **5** |
| `utils/epub_enhanced.py` | `O_NOFOLLOW` fd-backed fileobj to `epub.read_epub` instead of following symlinks. | **5** |
| `core/organizer.py` | SafeDir dedup hashing (`SymlinkRejected`); constructor input validation; per-file timeout + transcription caps with graceful degradation. | **4** |
| `core/file_ops.py` | `os.walk`/`rglob` → `safe_walk` (skip symlinks/hidden) for collection and empty-dir cleanup (#270). | **4** |
| `utils/readers/scientific.py` | Size caps on NetCDF/MAT readers that previously had **zero** size protection (buffer-bomb guard). | **4** |
| `utils/readers/documents.py` | `FileTooLargeError` propagation fix; lazy PDF streaming via `/dev/fd/{fd}` before page cap (#298). | **4** |
| `utils/readers/archives.py` | Per-archive decompression-bomb size cap before parse; SafeDir fileobj entry points. | **4** |
| `config/manager.py` | Atomic config writes; migration safety with fallback-to-defaults leaving disk untouched (F6). | **4** |
| `config/schema.py` | `__post_init__` validation (SVG byte cap, timeout/threshold ranges, schema-version constants). | **4** |

---

## 4. Reliability / Robustness (shared-file fixes, no new security primitive)

These are independently valuable and several are lower-risk than the symlink series.

| File | Fix | Value |
|------|-----|-------|
| `core/dispatcher.py` | Anti-cascade: best-effort transcription never aborts batch; vision-timeout → EXIF/filename fallback; sequential isolated retry on pool saturation (#432). | **4** |
| `services/vision_processor.py` | Always filesystem-sanitizes untrusted model output; circuit breaker + shape validation + strict retry; image-edge clamp; OOM strings treated as fatal. | **4** |
| `models/base.py` | `generate_structured()` backend-agnostic JSON-prompt + `parse_structured_json`/`StructuredParseError`. Pull with vision_processor. | **4** |
| `services/vision_fallback.py` + `models/vision_schema.py` | Degraded image categorization (EXIF/filename) when vision times out; single-call structured vision schema. | **4** |
| `services/inference_timer.py` | Per-inference timing context manager + structured logging (observability). | **4** |
| `pipeline/resource_aware_executor.py` (406 LOC) | Extracted prefetch + buffer-pool + memory-pressure rebalancing (I/O-compute overlap). Needs `optimization/` present (it is). | **4** |
| `utils/text_processing.py` | Vendored stopwords + `snowballstemmer` replace optional NLTK `nltk.download()` → deterministic, offline-safe (no network/`LookupError` paths). Trade-off: ASCII-only tokenization. | **3** |
| `pipeline/router.py` | Adds `.tif/.webp/.heic/.heif/.svg` to routing. Pairs with WEBP/HEIC support (#370). | **2** |

Notable CHANGELOG-documented reliability fixes embedded in the above: parallel
timeout cascade abort fix (#370), vision circuit breaker for Ollama OOM,
single multimodal default model (`gemma3:4b`) to avoid dual-model OOM on 8 GB
machines (#370/#375), and the Python 3.14 lazy-import startup fix (#379).

---

## 5. Features (new, mostly self-contained)

| Module | Feature | Value |
|--------|---------|-------|
| `services/intelligence/preference_storage.py` (727 LOC) | InMemory + SQLite preference storage behind a Protocol. Depends on sibling intelligence modules. | **4** |
| `services/copilot/rules/actions.py` (335 LOC) | Hardlink/symlink rule actions with conflict strategies ("second-view" organization, #459). | **3** |
| `config/migrations.py` (218 LOC) | Versioned config-schema migration registry + version compare (registry currently empty; value as schema evolves). | **3** |
| `services/audio/lexicons.py` (191 LOC) | Externalized sentiment/keyword lexicons from JSON. **Requires shipping the bundled JSON data file.** | **3** |
| `utils/readers/_scientific_stub.py` (46 LOC) | Install-hint stubs when scipy/h5py absent (graceful optional-dep degradation). | **3** |
| `cli/logs.py`, `cli/undo_recover.py`, `cli/dedupe_renderer.py`, `cli/state.py`, `cli/lazy.py` | CLI operator commands & patterns (`fo logs`, `fo recover`, rich/json/plain renderers, per-invocation state, lazy command loading). Techniques reusable; contents bound to fork's command surface. | **2–3** |
| `config/defaults.py` (7 LOC) | `DEFAULT_MODEL` / `DEFAULT_LARGE_MODEL` constants (values are fork-specific). | **1** |

---

## 6. Tests (pull back *with* the code they guard)

The fork has ~578 test files / ~17.4k test functions (the original's larger raw
count is the dropped UI/api/auth/e2e/playwright layers). On the **shared core the
fork is denser**, with **123 test files that have no equivalent in the original**.

**Fork-only test areas:** `tests/security/` (symlink/TOCTOU threat model),
`tests/smoke/` (import-boundary), `tests/extras/` (optional-dep matrix),
`tests/integration/utils/readers/`.

**Highest-value pull-back tests** (map 1:1 to the hardening above):

- Path/symlink/TOCTOU: `security/test_symlink_safety.py`, `core/test_path_guard.py`,
  `utils/test_safedir.py`, `utils/test_safedir_anchored.py`,
  `utils/test_readers_safedir.py`, `cli/test_path_validation.py` (+ `_wiring`),
  `core/test_organizer_sha256_safedir.py`,
  `services/deduplication/test_extractor_safedir.py` / `test_image_safedir.py`,
  `services/search/test_read_text_safe_safedir.py`,
  `utils/test_epub_enhanced_safedir.py`, `watcher/test_safedir_hardening_322.py`.
- Atomicity/durability: `utils/test_atomic_write.py`, `undo/test_durable_move.py`,
  `undo/test_trash_gc.py`, `undo/test_trash_gc_race.py`, `cli/test_undo_recover.py`.
- Redaction & errors: `utils/test_log_redact.py`, `core/test_error_taxonomy.py`,
  `utils/test_cli_errors.py`.
- Resource limits / malformed input: `utils/test_reader_robustness_326.py`
  (STEP memory-blowup cap), `integration/utils/readers/test_archives_reader.py`
  (corrupt-archive, `max_files` truncation).

**Gap to preserve:** the original's `review_regressions` security tests
(`test_security_detectors.py`, `test_review_regressions_security.py`) are *absent*
in the fork — keep them; do not let a pull-back drop them.

**No generative fuzzing** (`hypothesis`) exists in either; the fork's coverage is
adversarial-input style.

---

## 7. CI / Tooling Hardening

| Area | What the fork adds | Value |
|------|--------------------|-------|
| **`scripts/check_*.py` rails** | AST/regex guards: `check_atomic_write`, `check_safedir_required`, `check_safedir_valueerror`, `check_defusedxml_fallback`, `check_cli_path_validation`, `check_textiowrapper_detach`, plus test-hygiene (`check_test_hardcoded_paths`, `check_test_separator_paths`, `check_pytest_raises_hygiene`, `check_xdist_loadgroup`) and coverage (`check_module_coverage_floor`, `pip_audit_gate`, `select_tests_for_changes`). | **5** |
| **`.pre-commit-config.yaml`** | Wires the rails above; mypy widened from `models/`→ all `src/`; `interrogate --fail-under 95` docstring gate; `pytest-affected`. | **5** |
| **`scripts/` guards backend** | Executable backends for the rails + `scripts/coverage/` ratchet + `scripts/ci/run-xdist-audit.sh`. | **5** |
| **`.github/workflows/security.yml`** | pip-audit **gated** (removed `continue-on-error`) via `pip_audit_gate.py` + `accepted-risks*.yml`; extras audit on Linux+macOS matrix; retry-wrapped installs; CodeQL bump. | **4** |
| **New workflows** | `ci-extras.yml` (per-extra install/import smoke), `pr-integration.yml`, `parallel-macos-matrix.yml` (timeout-race gate), `dependabot-automerge.yml`. | **4** |
| **`SECURITY.md`** | Replaces boilerplate with a real Security Architecture section + lint-rail table + Known Limitations + GitHub Security Advisories reporting. | **4** |
| **`pyproject.toml`** | Ruff adds `PT012/PT017/PT022` + `external=["G1".."G5"]` (preserves rail noqas); pragmatic mypy per-module overrides. Net type strictness ≈ equal (the real gain is the mypy-on-all-`src` pre-commit hook). | **3** |
| **`.claude/` rules/scripts** | PR/issue workflow automation scripts + workflow-state-machine / documentation-verification rule docs. References fork paths; needs re-targeting. | **3** |

---

## 8. Recommended Phased Pull-Back Plan

**Phase 0 — CI rails first (mechanical, low-risk, high-leverage).**
Port `scripts/check_*.py` + their pre-commit hooks + `pip_audit_gate.py` /
`accepted-risks*.yml`, re-targeting path globs to `src/file_organizer/`. These
prevent silent regression of everything that follows. *Note:* the
`safedir-required` and `atomic-write-required` rails should be added **with or
after** the code they enforce, or as advisory-only until then.

**Phase 1 — Hardening foundation.** `utils/safedir.py`, `core/path_guard.py`,
`utils/atomic_write.py` (incremental over existing `atomic_io.py`),
`utils/log_redact.py`, `core/error_taxonomy.py`, `utils/cli_errors.py`,
`undo/durable_move.py` + `_journal.py` + `trash_gc.py`. Bring their tests.

**Phase 2 — Hardened call sites.** text_processor, writer, rollback,
undo_manager, epub_enhanced, organizer, file_ops + their `*_safedir` tests.

**Phase 3 — Resource caps & reliability.** readers (scientific/documents/
archives/ebook), config schema + manager, dispatcher, vision_processor +
models/base `generate_structured`, vision_fallback/vision_schema, parallel
timeout-cascade fix. Bring robustness tests.

**Phase 4 — Features & opportunistic.** preference_storage, copilot link
actions, config migrations, audio lexicons (+ data file), `text_processing`
offline stemming, WEBP/HEIC routing, CLI operator commands. Then SECURITY.md
architecture, gated `security.yml`, and `.claude` automation.

Each phase: re-target imports to `file_organizer.*`, run
`bash .claude/scripts/pre-commit-validation.sh`, then `/code-reviewer`.

---

## 9. Key Caveats

1. **Layout rename** (`src/` → `src/file_organizer/`) touches every import and
   every hook/rail path glob — the bulk of mechanical pull-back effort.
2. **Package identity** differs (`fo-core` vs `file_organizer`); `defaults.py`
   values, the `fo-core[scientific]` extra name, and CLI prog name (`fo`) are
   fork-specific.
3. **Bundled data:** `audio/lexicons.py` needs its JSON data file shipped.
4. **Don't lose the original's `review_regressions` security tests** when
   reconciling test trees.
5. **The dropped UI/api surface is out of scope** — the original retains it; the
   fork offers no improvements there.

---

*Generated from a file-level diff of the two trees plus four targeted code
reviews. The fork was inspected at commit `89b6019` (v2.0.0-beta.10).*
