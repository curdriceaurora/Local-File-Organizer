---
name: 579-stream1-core
issue: 579
stream: 1
title: "Core Components Docstrings"
status: open
created: 2026-03-06T21:00:00Z
updated: 2026-03-06T21:00:00Z
---

# Task 579.1: Core Components Docstrings

## Scope

Add docstrings to core components in `src/file_organizer/core/`:

- `__init__.py` - module docstring + exports
- `file_metadata.py` - FileMetadata dataclass and helpers
- `file_classifier.py` - Classification engine
- `pipeline.py` - Pipeline orchestration
- `config.py` - Configuration management
- `cache.py` - Caching utilities
- Other core modules as present

## Acceptance Criteria

- [ ] All public classes have docstrings
- [ ] All public methods/functions have docstrings  
- [ ] Module-level docstring present in each file
- [ ] No function signatures changed
- [ ] Google-style formatting consistent
- [ ] `interrogate -v src/file_organizer/core` reports 90%+ coverage

## Implementation Notes

1. Start with `file_metadata.py` (foundational)
2. Then `pipeline.py` and `config.py` (core architecture)
3. Fill remaining modules
4. Verify with: `interrogate -v src/file_organizer/core`

## Definition of Done

- [ ] Baseline measured: `interrogate src/file_organizer/core`
- [ ] All public APIs have docstrings
- [ ] Coverage reported >= 90% for core/
- [ ] No behavior changes (docstrings only)
- [ ] Commit: "docs: add docstrings to core components (#579.1)"

## Files to Touch

```
src/file_organizer/core/
├── __init__.py
├── file_metadata.py
├── file_classifier.py
├── pipeline.py
├── config.py
├── cache.py
└── [other .py files]
```

## Verification Command

```bash
interrogate -v src/file_organizer/core --quiet
```

Expected: >= 90% coverage
