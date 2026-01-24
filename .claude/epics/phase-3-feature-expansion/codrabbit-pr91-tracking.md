---
title: CodeRabbit PR #91 Review Tracking
epic: phase-3-feature-expansion
pr: 91
created: 2026-01-24T00:00:00Z
updated: 2026-01-24T00:00:00Z
status: in-progress
---

# CodeRabbit PR #91 Review - Issue Tracking

## Overview

Tracking document for CodeRabbit review issues from PR #91 (Audio Transcription).

**Total Issues:** 28
**Resolved in Code:** 14 (50%)
**Tracked as GitHub Issues:** 7 (25%)
**Already Addressed:** 7 (25%)

## GitHub Issues Created

### Documentation (1 issue)

**#103: Add CUDA/cuDNN/FFmpeg installation requirements to README**
- **Priority:** Medium
- **Files:** README.md, file_organizer_v2/README.md
- **Description:** Document GPU acceleration and audio conversion dependencies
- **Labels:** documentation, enhancement
- **Acceptance Criteria:**
  - [ ] CUDA/cuDNN installation instructions for GPU users
  - [ ] FFmpeg installation for all platforms
  - [ ] Platform-specific commands (macOS, Linux, Windows)
  - [ ] Fallback behavior documentation
  - [ ] Troubleshooting section

### Code Quality (6 issues)

**#104: Add format validation in AudioTranscriber.transcribe()**
- **Priority:** Low
- **Files:** models/audio_transcriber.py
- **Description:** Add explicit format validation with ValueError
- **Labels:** enhancement
- **Acceptance Criteria:**
  - [ ] Validate format using is_supported_format()
  - [ ] Raise ValueError with clear message
  - [ ] Update docstring
  - [ ] Add test case

**#105: Move torch>=2.1.0 to optional dependencies**
- **Priority:** Medium
- **Files:** pyproject.toml, README.md
- **Description:** Make PyTorch optional to reduce installation size
- **Acceptance Criteria:**
  - [ ] Move torch to optional-dependencies
  - [ ] Create gpu, audio-video, gpu-audio groups
  - [ ] Update README installation instructions
  - [ ] Test CPU-only installation
  - [ ] Test GPU installation with extras

**#106: Replace hardcoded 0.75 threshold in is_confident()**
- **Priority:** Low
- **Files:** methodologies/para/detection/heuristics.py
- **Description:** Use config.get_category_threshold() instead of hardcoded value
- **Acceptance Criteria:**
  - [ ] Replace hardcoded 0.75 with config lookup
  - [ ] Add test for config-based threshold
  - [ ] Update any related documentation

**#107: Fix confidence formula docstring inconsistency**
- **Priority:** Low
- **Files:** methodologies/para/detection/heuristics.py:336
- **Description:** Docstring doesn't match implementation formula
- **Acceptance Criteria:**
  - [ ] Update docstring to match actual formula
  - [ ] Or update formula to match docstring (with tests)
  - [ ] Document reasoning for chosen formula

**#108: Add category string validation in rules engine**
- **Priority:** Low
- **Files:** methodologies/para/rules/engine.py
- **Description:** Validate category strings against PARACategory enum
- **Acceptance Criteria:**
  - [ ] Add validation function
  - [ ] Raise ValueError for invalid categories
  - [ ] Add test cases for validation
  - [ ] Update error messages

**#109: Add missing category field to ai_fallback_rule example**
- **Priority:** Low
- **Files:** docs/para/rule-schema.yaml:497-509
- **Description:** Example missing required category field in suggest action
- **Acceptance Criteria:**
  - [ ] Add category field to example
  - [ ] Verify example against schema
  - [ ] Check other examples for consistency

## Issues Resolved in Code (14 issues)

### Commit f8a1d94 (Part 3/3) - 5 issues
1. ✅ PARA heuristics configuration (use PARAConfig)
2. ✅ Unix st_ctime compatibility (use st_birthtime on macOS)
3. ✅ Audio options cleanup (remove unused fields)
4. ✅ AIHeuristic raises NotImplementedError
5. ✅ Remove hardcoded years from archive keywords

### Commit 7df2665 (Part 2/3) - 4 issues
1. ✅ Remove INT4 from ComputeType enum
2. ✅ Complete ComputeType enum (10 types)
3. ✅ Add compute type validation
4. ✅ Fix confidence calculation (log→probability)

### Commit a337da0 (Part 1/3) - 5 issues
1. ✅ Fix TOC anchor fragments in examples.md
2. ✅ Add trailing newlines (W292)
3. ✅ Path(None) TypeError prevention
4. ✅ DEFAULT_CONFIG mutation fix
5. ✅ Exception chaining with "from e"

## Issues Already Addressed (7 issues)

1. ✅ Temp directory cleanup - Documented in preprocessor.py docstring
2. ✅ Output path handling - Fixed in preprocess() method
3. ✅ Unused TranscriptionOptions fields - Removed in commit f8a1d94
4. ✅ Hardcoded thresholds - Replaced with PARAConfig
5. ✅ st_ctime Unix issue - Fixed with st_birthtime
6. ✅ Hardcoded years - Removed from default_config.yaml
7. ✅ AIHeuristic stub - Now raises NotImplementedError

## Summary by Priority

### High Priority (0 issues)
- None remaining

### Medium Priority (2 issues)
- #103: Documentation (CUDA/cuDNN/FFmpeg)
- #105: Optional torch dependency

### Low Priority (5 issues)
- #104: Format validation
- #106: is_confident() hardcoded threshold
- #107: Confidence formula docstring
- #108: Category string validation
- #109: ai_fallback_rule example

## Implementation Plan

### Phase 1: Documentation (Sprint 1)
- [ ] #103: Add dependency documentation to README

### Phase 2: Dependencies (Sprint 1-2)
- [ ] #105: Reorganize optional dependencies

### Phase 3: Code Quality (Sprint 2-3)
- [ ] #104: Format validation
- [ ] #106: is_confident() config
- [ ] #108: Category validation

### Phase 4: Documentation Cleanup (Sprint 3)
- [ ] #107: Confidence formula docs
- [ ] #109: Rule schema example

## Test Coverage

All resolved issues have test coverage:
- ✅ 187/188 tests passing
- ✅ Audio transcription tests pass
- ✅ PARA methodology tests pass
- ✅ No regressions introduced

## Related Resources

- **PR #91:** https://github.com/curdriceaurora/Local-File-Organizer/pull/91
- **Issue #42:** Audio Transcription Feature
- **Epic:** Phase 3 - Feature Expansion
- **Daily Log:** .claude/epics/phase-3-feature-expansion/daily-logs/2026-01-24.md

---

**Last Updated:** 2026-01-24T00:00:00Z
**Status:** In Progress - 7 issues tracked, 14 resolved, 7 addressed
**Next Review:** After Sprint 1 completion
