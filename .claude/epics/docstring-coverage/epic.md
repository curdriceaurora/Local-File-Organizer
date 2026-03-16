---
name: docstring-coverage
title: Docstring Coverage - Reach 90% via Interrogate
description: Add missing docstrings across codebase to reach 90% interrogate coverage threshold
status: open
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/579
created: 2026-03-06T20:00:00Z
updated: 2026-03-06T20:00:00Z
effort_hours: 20-30
parallel: true
---

# Docstring Coverage Epic

Reach 90% docstring coverage threshold via interrogate across all public APIs.

## Scope

- **Target**: >= 90% coverage (configured in pyproject.toml)
- **Files**: All `.py` files under `src/file_organizer/`
- **Focus**: Public APIs (classes, public methods), then internal utilities
- **Style**: Google-style docstrings (existing standard)
- **Constraints**: No signature/behavior changes, docstrings only

## Current Status

- **Coverage**: [To be measured]
- **Started**: 2026-03-06
- **Parallel Streams**: 6 (independent components)

## MECE Task Breakdown

### Stream 1: Core Components
- **Files**: `core/*.py` (7-10 modules)
- **Scope**: File metadata, pipeline, config
- **Effort**: ~4-5 hours

### Stream 2: Services Layer
- **Files**: `services/**/*.py` (12+ services)
- **Scope**: File readers, processors, organizers
- **Effort**: ~6-8 hours

### Stream 3: Web Layer
- **Files**: `web/*.py` (routes, handlers, utilities)
- **Scope**: API endpoints, web handlers, utilities
- **Effort**: ~4-5 hours

### Stream 4: CLI & User-Facing APIs
- **Files**: `cli/*.py`, top-level `__init__.py` exports
- **Scope**: Command handlers, public interfaces
- **Effort**: ~3-4 hours

### Stream 5: Methodologies & Analysis
- **Files**: `methodologies/**/*.py` (PARA, Johnny Decimal, etc.)
- **Scope**: Strategy classes, detection, analysis
- **Effort**: ~4-5 hours

### Stream 6: Utils & Helpers
- **Files**: `utils/**/*.py`, `models/*.py`
- **Scope**: Utility functions, data models
- **Effort**: ~3-4 hours

## Definition of Done

- [ ] All 6 streams complete their assignments
- [ ] `interrogate -v src/file_organizer` reports >= 90%
- [ ] No function/class behavior changed (docstrings only)
- [ ] Google-style formatting consistent throughout
- [ ] Baseline measured, final coverage verified
