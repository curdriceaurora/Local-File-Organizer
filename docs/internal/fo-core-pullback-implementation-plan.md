# fo-core Pull-Back — MECE Implementation Plan

**Date:** 2026-06-14
**Companion to:** `docs/internal/fo-core-fork-evaluation.md`
**Target repo:** `local-file-organizer` (package `src/file_organizer/`)
**Source fork:** `curdriceaurora/fo-core` (package `src/`, commit `89b6019`)

This plan turns the fork evaluation into an executable, **MECE** work breakdown:
every candidate module is assigned to exactly **one** work package (mutually
exclusive) and all evaluation sections — Hardening, Reliability, Features, Tests,
CI/Tooling — are covered (collectively exhaustive). Tests travel with the module
they validate.

---

## Global conventions (defined once; apply to every work package)

- **Layout re-targeting:** the fork's flat `src/X` maps to `src/file_organizer/X`.
  Rewrite imports `from X` → `from file_organizer.X`; re-scope every pre-commit
  hook / rail path glob `^src/` → `^src/file_organizer/`.
- **Definition of Done (per WP):**
  1. Module(s) ported + re-targeted imports.
  2. Their tests ported and passing.
  3. `bash .claude/scripts/pre-commit-validation.sh` green.
  4. `/code-reviewer` clean.
  5. Coverage floor respected; CHANGELOG entry added.
  6. **One PR per WP.**
  7. The original's `review_regressions/` security tests are **preserved** (never
     dropped while reconciling test trees).
- **Permanently out of scope:** the fork-dropped `api/`, `web/`, `desktop/`,
  `tui/`, `client/`, `plugins/`, `deploy/` surfaces. The original keeps them; the
  fork offers no improvements there.
- **Branching:** each WP is its own branch/PR off `main`, sequenced by the
  dependency graph below.

---

## Phase 0 — Enablement (no runtime change)

| WP | Scope | Deliverable |
|----|-------|-------------|
| **WP-0.1 Scaffolding** | Re-targeting checklist; confirm package stays `src/file_organizer/`; stand up the CI-rail framework in **advisory mode** (warn, don't block) so later rails can flip to enforce; create `tests/security/`, `tests/smoke/`, `tests/extras/` skeletons. | Mechanical prep; zero behavior change. |

---

## Phase 1 — Foundations (parallel after WP-0.1; no consumers yet)

| WP | Modules (fork-only) | Tests ported |
|----|--------------------|--------------|
| **WP-1.1 Path-safety primitive** | `utils/safedir.py`, `core/path_guard.py`, `cli/path_validation.py` | `test_safedir`, `test_safedir_anchored`, `test_path_guard`, `test_path_validation`, `test_path_validation_wiring` |
| **WP-1.2 Crash-safety primitive** | `utils/atomic_write.py`, `undo/durable_move.py`, `undo/_journal.py`, `undo/trash_gc.py`, `cli/undo_recover.py` | `test_atomic_write`, `test_durable_move`, `test_trash_gc`, `test_trash_gc_race`, `test_undo_recover` |
| **WP-1.3 Diagnostics primitive** | `utils/log_redact.py`, `core/error_taxonomy.py`, `utils/cli_errors.py`, `services/inference_timer.py` | `test_log_redact`, `test_error_taxonomy`, `test_cli_errors` |

---

## Phase 2 — Hardened call sites (consume Phase 1)

| WP | Modules hardened (shared files) | Depends on | Tests |
|----|-------------------------------|-----------|-------|
| **WP-2.1 Read-path** | `services/text_processor.py`, `utils/epub_enhanced.py`, readers SafeDir dispatch, `services/deduplication/{extractor,image_*}.py`, `services/search` read-text-safe, `methodologies/para` heuristics read-content, `core/organizer.py` (sha256 via SafeDir) | 1.1 | `test_*_safedir` (extractor, image, read_text_safe, epub, organizer_sha256, heuristics, readers_safedir) |
| **WP-2.2 Write/undo-path** | `pipeline/stages/writer.py`, `undo/rollback.py`, `undo/undo_manager.py`, `core/file_ops.py` (`safe_walk`) | 1.1, 1.2 | rollback/undo durability + inode-swap tests, file_ops walk tests |
| **WP-2.3 Watcher** | `watcher/handler.py` + monitor symlink hardening | 1.1 | `watcher/test_safedir_hardening_322` |

---

## Phase 3 — Resource limits & config validation

| WP | Modules | Depends on | Tests |
|----|---------|-----------|-------|
| **WP-3.1 Reader caps** | `utils/readers/{scientific,documents,archives,ebook}.py` (size / decompression-bomb caps) | 1.1 | `test_reader_robustness_326`, integration archives reader, extras matrix |
| **WP-3.2 Config validation** | `config/schema.py` (`__post_init__` bounds), `config/manager.py` (atomic + migration-safe writes) | 1.2 | schema/manager validation tests |

---

## Phase 4 — Reliability

| WP | Modules | Notes |
|----|---------|-------|
| **WP-4.1 Inference resilience** | `core/dispatcher.py` (anti-cascade, vision-timeout fallback), `parallel/*` (timeout-cascade abort fix #370) | high blast radius — isolate |
| **WP-4.2 Vision pipeline** | `services/vision_processor.py`, `models/base.py` (`generate_structured`), `models/vision_schema.py`, `services/vision_fallback.py`, `pipeline/router.py` (WEBP/HEIC/SVG) | structured output + circuit breaker |
| **WP-4.3 Pipeline executor** | `pipeline/resource_aware_executor.py` + `pipeline/orchestrator.py` refactor | needs `optimization/` (present) |
| **WP-4.4 Offline NLP** | `utils/text_processing.py` (vendored stopwords + snowballstemmer, drop `nltk.download`) | low-risk, high reliability win |

---

## Phase 5 — Features (mostly independent)

| WP | Modules |
|----|---------|
| **WP-5.1 Preferences persistence** | `services/intelligence/preference_storage.py` (+ tracker wiring) |
| **WP-5.2 Config evolution** | `config/migrations.py`, `config/defaults.py` |
| **WP-5.3 Optional-dep UX** | `utils/readers/_scientific_stub.py`, `services/audio/lexicons.py` **+ bundled JSON data file** |
| **WP-5.4 Copilot link actions** | `services/copilot/rules/actions.py` (hardlink/symlink) |
| **WP-5.5 CLI operator commands** | `cli/logs.py`, `cli/dedupe_renderer.py`, `cli/state.py`, `cli/lazy.py` |

---

## Phase 6 — CI rails & tooling (enforcement gated on its target code landing)

| WP | Scope | Enforce after |
|----|-------|--------------|
| **WP-6.1 Security/path rails** | `scripts/check_{atomic_write,safedir_required,safedir_valueerror,defusedxml_fallback,cli_path_validation,textiowrapper_detach}.py` + pre-commit hooks | 1.1 / 1.2 / 2.x |
| **WP-6.2 Test-hygiene & coverage rails** | `scripts/check_{test_hardcoded_paths,test_separator_paths,pytest_raises_hygiene,called_attribute_assertion,xdist_loadgroup,module_coverage_floor}.py`, `select_tests_for_changes.py`, `scripts/coverage/*` + hooks | independent (advisory now) |
| **WP-6.3 Supply-chain gating** | `scripts/pip_audit_gate.py` + `.github/accepted-risks*.yml`, gate `security.yml`, add `ci-extras.yml` | independent |
| **WP-6.4 Lint/type config + docs** | Ruff `PT0xx` + `external` rules, mypy-on-all-`src`, `SECURITY.md` architecture + rail table, `.claude` rules/scripts | after rails exist |

---

## Dependency graph (critical path)

```text
WP-0.1
  ├─► WP-1.1 ─┬─► WP-2.1 ─► WP-3.1
  │           ├─► WP-2.2 (also needs 1.2)
  │           └─► WP-2.3
  ├─► WP-1.2 ─┴─► WP-2.2, WP-3.2
  └─► WP-1.3
WP-4.x, WP-5.x  ── mostly independent (4.3 needs optimization/; 4.2 needs models/)
WP-6.x          ── rails authored anytime (advisory); flip to ENFORCE only once
                   the code they guard has merged
```

---

## MECE coverage check

- **Mutual exclusivity:** every fork-only module (25) and every hardened shared
  file from the evaluation is assigned to exactly one WP — no file appears twice.
  (`cli/undo_recover.py` lives only in WP-1.2; `core/organizer.py` only in WP-2.1;
  `core/file_ops.py` only in WP-2.2.)
- **Collective exhaustiveness:** Phases 1–6 plus the cross-cutting conventions
  cover the evaluation's Hardening, Reliability, Features, Tests, and CI/Tooling
  sections in full. Tests are not a separate phase — each WP owns the tests for
  its modules; only shared scaffolding lives in WP-0.1.

---

## Suggested milestones

1. **M1 — Security floor:** WP-0.1 → 1.1 → 1.2 → 2.1 → 2.2 → 2.3 (then enforce
   WP-6.1). Closes the symlink/TOCTOU + durability gaps — highest value/urgency.
2. **M2 — Robustness:** WP-1.3, 3.1, 3.2, 4.1, 4.4 (plus WP-6.2, 6.3).
3. **M3 — Pipeline/vision:** WP-4.2, 4.3.
4. **M4 — Features & polish:** WP-5.x, WP-6.4.

---

## Risk register

| Risk | Mitigation |
|------|------------|
| **Blast radius:** WP-2.2 (undo/move semantics), WP-4.1 (parallel timeouts) | Isolate, heavy tests, consider feature flag / staged rollout |
| **Layout drift** (import + glob re-targeting is the bulk of effort) | Standardize in WP-0.1; mechanical, reviewable |
| **Optional deps/data:** WP-5.3 needs the lexicon JSON; rename `fo-core[scientific]` extra | Ship data file; adjust extra name to `local-file-organizer[scientific]` |
| **mypy 1.20.x crash** on models | Already capped to `<1.20`; keeps `lint` green throughout |
| **Test reconciliation** | Never drop the original's `review_regressions` security tests |

---

*Companion roadmap to the fork evaluation. Each work package is independently
shippable and maps to a single PR.*
