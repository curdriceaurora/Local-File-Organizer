---
name: technical-debt-tracking
title: Technical Debt Tracking for Phase 3
epic: phase-3-feature-expansion
created: 2026-01-24T04:30:00Z
updated: 2026-01-24T04:30:00Z
status: active
---

# Technical Debt Tracking - Phase 3

This document tracks technical debt items identified during Phase 3 implementation that should be addressed in future iterations.

## From PR #90 (PARA Methodology - Task #38)

### Code Quality Issues

**Issue #98: Replace hardcoded archive years with regex pattern**
- **Priority**: Medium
- **Epic**: phase-3-feature-expansion
- **Task**: 38 (PARA Methodology)
- **Status**: Open
- **Created**: 2026-01-24
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/98
- **Description**: Archive keywords contain hardcoded years (2020, 2021, 2022)
- **Files**: `file_organizer_v2/src/file_organizer/methodologies/para/default_config.yaml`
- **Effort**: 1-2 hours

**Issue #99: Improve keyword matching with word boundaries**
- **Priority**: Medium
- **Epic**: phase-3-feature-expansion
- **Task**: 38 (PARA Methodology)
- **Status**: Open
- **Created**: 2026-01-24
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/99
- **Description**: Naive substring matching causes false positives
- **Files**: `file_organizer_v2/src/file_organizer/methodologies/para/detection/heuristics.py`
- **Effort**: 2-3 hours

**Issue #101: Fix st_ctime usage for cross-platform compatibility**
- **Priority**: Medium
- **Epic**: phase-3-feature-expansion
- **Task**: 38 (PARA Methodology)
- **Status**: Open
- **Created**: 2026-01-24
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/101
- **Description**: `st_ctime` behaves differently on Unix vs Windows
- **Files**: `file_organizer_v2/src/file_organizer/methodologies/para/detection/heuristics.py`
- **Effort**: 2-4 hours

### Documentation Issues

**Issue #100: Fix markdown link fragments in rule-examples.md**
- **Priority**: Low
- **Epic**: phase-3-feature-expansion
- **Task**: 38 (PARA Methodology)
- **Status**: Open
- **Created**: 2026-01-24
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/100
- **Description**: TOC anchor fragments don't match heading slugs
- **Files**: `file_organizer_v2/docs/para/rule-examples.md`
- **Effort**: 30 minutes - 1 hour

### Future Features

**Issue #102: Implement AI Heuristic for PARA categorization**
- **Priority**: Low (Future Enhancement)
- **Epic**: phase-3-feature-expansion
- **Task**: 38 (PARA Methodology)
- **Status**: Open
- **Created**: 2026-01-24
- **GitHub**: https://github.com/curdriceaurora/Local-File-Organizer/issues/102
- **Description**: AIHeuristic class needs actual implementation using Ollama
- **Files**: `file_organizer_v2/src/file_organizer/methodologies/para/detection/heuristics.py`
- **Effort**: 8-12 hours
- **Dependencies**: Ollama integration, embedding model

---

## Summary

**Total Issues**: 5
- **Code Quality**: 3 (Medium priority)
- **Documentation**: 1 (Low priority)
- **Future Features**: 1 (Low priority)

**Total Effort Estimate**: 14-22 hours

## Recommended Approach

1. **Phase 3 Completion**: Address Medium priority items (#98, #99, #101) before marking Task #38 as fully complete
2. **Documentation Sprint**: Include #100 in next documentation update
3. **Phase 4 Planning**: Consider #102 for Phase 4 (Intelligence) epic

## Tracking Updates

- **2026-01-24**: Initial tracking document created after PR #90 review
- Issues created and linked to epic
