# Quality Ratchet Baseline

**Created**: 2026-02-28T00:00:00Z
**Issue**: #480

This document tracks the quality ratchet — lint and type strictness gates that
only move forward, never backward.

## Mypy Strict Mode

### CI-Gated Modules (must stay at 0 errors)

| Module | Errors | Date Gated |
|--------|--------|------------|
| `src/file_organizer/models/` | 0 | 2026-02-28 |

### Not Yet Gated (current error counts for reference)

| Module | Errors | Notes |
|--------|--------|-------|
| `src/file_organizer/core/` | ~133 | Largest orchestrator module |
| `src/file_organizer/config/` | ~73 | Configuration management |
| `src/file_organizer/cli/` | ~100+ | CLI layer |
| `src/file_organizer/services/` | ~200+ | Business logic |

**Goal**: Gate one more module per sprint until full coverage.

## Ruff C901 Complexity

**Threshold**: `max-complexity = 15`

### Grandfathered Functions (per-file-ignores)

These 14 functions exceed complexity 15 and are allowed via per-file-ignores
in `pyproject.toml`. New code must stay under 15.

| File | Function | Complexity |
|------|----------|------------|
| `api/config.py` | `load_settings` | 83 |
| `web/files_routes.py` | `files_upload` | 25 |
| `cli/utilities.py` | `search` | 24 |
| `parallel/processor.py` | `process_batch_iter` | 24 |
| `services/intelligence/profile_importer.py` | `validate_import_file` | 24 |
| `cli/dedupe.py` | `dedupe_command` | 23 |
| `src/file_organizer/core/organizer.py` | `organize` | 20 |
| `web/files_routes.py` | `_collect_entries` | 20 |
| `updater/installer.py` | `select_asset` | 19 |
| `cli/undo_redo.py` | `undo_command` | 18 |
| `methodologies/para/ai/suggestion_engine.py` | `_compute_feature_scores` | 18 |
| `services/copilot/intent_parser.py` | `_extract_parameters` | 17 |
| `services/intelligence/profile_merger.py` | `get_merge_conflicts` | 17 |
| `services/intelligence/profile_migrator.py` | `migrate_version` | 17 |

**Goal**: Reduce this list by refactoring 2-3 functions per sprint.

## How the Ratchet Works

1. **New code** must pass all enabled checks (C901 <= 15, mypy for gated modules)
2. **Existing violations** are allowed via per-file-ignores (C901) or by not
   gating the module yet (mypy)
3. **Never add new per-file-ignores** — refactor instead
4. **Remove per-file-ignores** when a function is refactored below threshold
5. **Gate new modules** for mypy as they reach 0 errors
