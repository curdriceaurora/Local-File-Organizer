# Test Skip Audit - Alpha.3 Release

**Audit Date:** 2026-03-26
**Total Skips Found:** 36 (14 unconditional + 22 conditional)

## Counting Methodology

Counts in this document represent unique skip *decorators* (i.e., `@pytest.mark.skip`,
`@pytest.mark.skipif`, or module-level `pytestmark` assignments), not individual test
methods. A single class-level or module-level decorator may cover multiple test methods
within that scope.

## Executive Summary

This document catalogs all skipped tests in the Local-File-Organizer test suite for the alpha.3 release. Tests are categorized by skip type and reason to facilitate planning and documentation.

## Skip Categories

### DOCUMENT Category: Intentional Deferrals (Total: 14)

#### 1. Phase 3 Audio/Video Features (12 tests)

These tests are intentionally skipped as they test features deferred to Phase 3:

**Audio Metadata Tests (3)** - `tests/utils/test_audio_metadata.py`:
- `test_extract_mp3_metadata` - Line 23: Audio metadata extraction not implemented
- `test_extract_wav_metadata` - Line 39: Audio metadata extraction not implemented
- `test_extract_music_tags` - Line 54: Music tag metadata not implemented

**Video Metadata Tests (3)** - `tests/utils/test_video_metadata.py`:
- `test_extract_mp4_metadata` - Line 23: Video metadata extraction not implemented
- `test_extract_resolution` - Line 37: Video resolution detection not implemented
- `test_detect_codec` - Line 51: Video codec detection not implemented

**Audio Transcription Tests (3)** - `tests/services/test_audio_transcription.py`:
- `test_transcribe_mp3_file` - Line 33: Audio transcription service not implemented
- `test_transcribe_wav_file` - Line 48: Audio transcription service not implemented
- `test_language_detection` - Line 61: Audio language detection not implemented

**Video Processing Tests (3)** - `tests/services/test_video_processing.py`:
- `test_process_mp4_video` - Line 33: Advanced video processing not implemented
- `test_scene_detection` - Line 46: Video scene detection not implemented
- `test_frame_extraction` - Line 59: Video frame extraction not implemented

**Status:** Intentional - Deferred to Phase 3 roadmap
**Action:** Document in CHANGELOG Known Limitations

#### 2. SSE Streaming Features (2 tests)

Server-Sent Events functionality not yet implemented:

**SSE Tests**:
- `tests/test_web_organize_routes.py:330` - `test_organize_stream_cancellation`: SSE streaming not implemented
- `tests/test_web_files_routes.py:246` - `test_files_sse_placeholder`: SSE routes not implemented

**Status:** Planned feature - Not yet implemented
**Action:** Document in CHANGELOG Known Limitations

### PLATFORM Category: OS/Environment-Specific (Total: 22)

#### 1. Platform-Specific Behavior (15 skip conditions)

Tests that correctly skip on platforms where the tested functionality is unavailable:

**Windows-Specific Skips (10)**:
- `tests/daemon/test_service_signal_safety.py:90, 132, 171` - Signal pipe not available on Windows (3 tests)
- `tests/plugins/test_base_coverage.py:79` - chmod does not restrict reads on Windows
- `tests/integration/test_error_propagation.py:30, 123` - chmod does not restrict reads on Windows (2 tests)
- `tests/parallel/test_checkpoint.py:446` - directory fsync is a no-op on Windows
- `tests/undo/test_rollback_extended.py:154, 362` - /dev/null is writable on Windows (2 tests)
- `tests/integration/test_organize_text_workflow.py:99` - Hardlinks require admin privileges on Windows

**Windows/macOS Skip (1)**:
- `tests/test_web_files_routes.py:87` - `test_files_sort_by_created`: Creation time sorting skipped on Windows/macOS (st_birthtime/st_ctime unreliable)

**macOS-Specific Tests (2)**:
- `tests/config/test_config_paths.py:52` - macOS-specific path test (skipped on non-macOS)
- `tests/integration/test_context_menu_macos.py:11` - macOS-only test (skipped on non-macOS)

**Linux-Specific Tests (1)**:
- `tests/config/test_config_paths.py:63` - Linux-specific path test (skipped on non-Linux)

**Windows-Specific Tests (1)**:
- `tests/config/test_config_paths.py:72` - Windows-specific path test (skipped on non-Windows)

**Status:** Expected behavior - Tests correctly skip on unsupported platforms
**Action:** No documentation needed (normal conditional testing)

#### 2. Optional Dependencies (4 tests)

Tests that skip when optional packages are not installed:

**ebooklib-dependent (2 tests)**:
- `tests/utils/test_epub_enhanced.py:43` - Module-level pytestmark (skips all tests in module if ebooklib not installed)
- `tests/utils/test_file_readers.py:222` - EPUB reading test

**Pillow-dependent (1 test)**:
- `tests/utils/test_epub_enhanced.py:350` - EPUB image extraction test

**pytest-benchmark-dependent (1 test)**:
- `tests/e2e/test_full_pipeline.py:312` - Benchmark test

**Status:** Expected behavior - Optional features gracefully degrade
**Action:** No documentation needed (standard optional dependency pattern)

#### 3. Environment/Import-Dependent (3 tests)

**SuggestionEngine Tests (3 tests in 2 test classes)** - `tests/integration/test_image_quality_para_suggestion.py`:

Tests that skip if SuggestionEngine cannot be imported:

- Line 448: `TestSuggestionEngineInit` (1 test):
  - `test_creates` - Verifies SuggestionEngine instantiation

- Line 455: `TestSuggestionEngineAPI` (2 tests):
  - `test_has_suggest_method` - Verifies API methods exist
  - `test_suggest_category_returns_something` - Verifies category suggestion functionality

**Status:** Expected behavior - Module exists but may not be importable in all test environments
**Action:** No documentation needed (environment-dependent, similar to optional dependencies)

**Note:** SuggestionEngine exists in the codebase (`src/file_organizer/methodologies/para/ai/suggestion_engine.py`) but the skipif protects against import failures in environments where the package isn't properly installed.

## Summary Table

| Category | Count | Reason | Status |
|----------|-------|--------|--------|
| Phase 3 Features | 12 | Audio/video metadata deferred to Phase 3 | DOCUMENT - Intentional |
| SSE Streaming | 2 | Server-Sent Events not yet implemented | DOCUMENT - Planned |
| Platform-Specific | 15 | OS-specific conditions | PLATFORM - Expected |
| Optional Dependencies | 4 | Optional packages not required | PLATFORM - Expected |
| Import-Dependent | 3 | SuggestionEngine import protection | PLATFORM - Expected |
| **Total** | **36** | | |

## Verification Commands

```bash
# Count unconditional skips
grep -rn "@pytest.mark.skip\b" tests/ --include="*.py" | grep -v "skipif" | wc -l
# Result: 14

# Count conditional skips (unique, deduplicated)
grep -rn "@pytest.mark.skipif\|pytestmark = pytest.mark.skipif" tests/ --include="*.py" | grep -v "conftest.py" | wc -l
# Result: 22 unique conditional skip decorators

# List Phase 3 skips
grep -rn "@pytest.mark.skip" tests/ --include="*.py" | grep "Phase 3"
# Result: 12 tests

# List SSE skips
grep -rn "@pytest.mark.skip" tests/ --include="*.py" | grep "SSE"
# Result: 2 tests
```

## Recommendations

1. **DOCUMENT in CHANGELOG**: Add Known Limitations section for:
   - 12 Phase 3 audio/video tests (intentional deferral)
   - 2 SSE streaming tests (planned feature)

2. **NO ACTION NEEDED** for:
   - 15 platform-specific skipifs (correct behavior)
   - 4 optional dependency skipifs (correct behavior)
   - 3 SuggestionEngine skipifs (correct behavior - protects against import failures)

## Next Steps

1. ✅ Audit complete - All skips identified and categorized
2. ✅ SuggestionEngine investigation complete - Module exists, skipif is correct
3. ⏳ Update CHANGELOG.md with Known Limitations section
4. ⏳ Verify all non-skipped tests still pass: `pytest tests/ -x --timeout=120`

## Conclusion

**Total tests requiring CHANGELOG documentation: 14** (12 Phase 3 + 2 SSE)
**Total platform/environment skips (no action needed): 22** (15 platform + 4 optional deps + 3 import-dependent)
