# Test Suite Documentation

## Skip Status Overview

This document tracks all skipped tests in the pytest test suite. Every skipped test is documented with a tracking issue explaining why it's skipped and when it can be unskipped.

### Final Skip Count

As of the audit completed on 2026-03-30:

- **@pytest.mark.skip**: 20 tests (unconditional skips)
- **@pytest.mark.skipif**: 26 tests (conditional platform skips)
- **pytest.importorskip**: ~8+ additional skips (optional dependency checks)
- **Total documented skips**: ~54 tests with issue references

### Skip Categories

#### 1. Deferred Features (Phase 3 Development)

Tests skipped because features are not yet implemented:

| Issue | Count | Description | Files Affected |
|-------|-------|-------------|----------------|
| [#611](https://github.com/curdriceaurora/Local-File-Organizer/issues/611) | 3 | Audio metadata extraction needs real fixtures | `tests/utils/test_audio_metadata.py` |
| [#1071](https://github.com/curdriceaurora/Local-File-Organizer/issues/1071) | 3 | Audio transcription feature (Phase 3) | `tests/services/test_audio_transcription.py` |
| [#1073](https://github.com/curdriceaurora/Local-File-Organizer/issues/1073) | 6 | Video processing features (Phase 3) | `tests/services/test_video_processing.py`<br>`tests/utils/test_video_metadata.py` |
| [#1076](https://github.com/curdriceaurora/Local-File-Organizer/issues/1076) | 1 | SSE routes for file browser | `tests/test_web_files_routes.py` |
| [#1077](https://github.com/curdriceaurora/Local-File-Organizer/issues/1077) | 3 | SuggestionEngine API implementation | `tests/integration/test_image_quality_para_suggestion.py` |
| [#1080](https://github.com/curdriceaurora/Local-File-Organizer/issues/1080) | 1 | SSE streaming for organize route | `tests/test_web_organize_routes.py` |
| [#338](https://github.com/curdriceaurora/Local-File-Organizer/issues/338) | 3 | Stream A executor not yet delivered | `tests/plugins/test_sandbox_isolation.py` |

**Subtotal: 20 tests** (deferred feature skips)

#### 2. Platform-Specific Limitations

Tests skipped on specific operating systems due to platform limitations:

| Issue | Platform | Count | Description | Files Affected |
|-------|----------|-------|-------------|----------------|
| [#1072](https://github.com/curdriceaurora/Local-File-Organizer/issues/1072) | Cross-platform | 3 | Platform-specific path validation (macOS, Linux, Windows) | `tests/config/test_config_paths.py` |
| [#1074](https://github.com/curdriceaurora/Local-File-Organizer/issues/1074) | Windows | 3 | Signal pipe not available on Windows | `tests/daemon/test_service_signal_safety.py` |
| [#1075](https://github.com/curdriceaurora/Local-File-Organizer/issues/1075) | Windows | 2 | `/dev/null` is writable on Windows | `tests/undo/test_rollback_extended.py` |
| [#1078](https://github.com/curdriceaurora/Local-File-Organizer/issues/1078) | Windows | 2 | `chmod` does not restrict reads on Windows | `tests/integration/test_error_propagation.py` |
| [#1078](https://github.com/curdriceaurora/Local-File-Organizer/issues/1078) | Windows | 1 | `chmod` does not restrict reads on Windows | `tests/plugins/test_base_coverage.py` |
| [#1081](https://github.com/curdriceaurora/Local-File-Organizer/issues/1081) | Windows | 1 | Directory fsync is a no-op on Windows | `tests/parallel/test_checkpoint.py` |
| [#1082](https://github.com/curdriceaurora/Local-File-Organizer/issues/1082) | Windows | 1 | Hardlinks require admin privileges on Windows | `tests/integration/test_organize_text_workflow.py` |
| [#1083](https://github.com/curdriceaurora/Local-File-Organizer/issues/1083) | macOS | 12 | macOS-only Quick Action feature | `tests/integration/test_context_menu_macos.py` |
| [#1085](https://github.com/curdriceaurora/Local-File-Organizer/issues/1085) | Windows, macOS | 1 | Creation time sorting is flaky on Windows/macOS | `tests/test_web_files_routes.py` |

**Subtotal: 26 tests** (platform-specific skips)

#### 3. Optional Dependencies

Tests skipped when optional dependencies are not installed. These use `pytest.importorskip()` pattern.

**Policy exception**: Tests using `pytest.importorskip()` for `rank_bm25` and `sklearn` do not require tracking issues, as these are standard optional dependency checks that skip automatically when the package is not installed.

| Issue | Dependency | Description | Files Affected |
|-------|------------|-------------|----------------|
| [#1079](https://github.com/curdriceaurora/Local-File-Organizer/issues/1079) | `ebooklib` | EPUB file processing | `tests/utils/test_file_readers.py`<br>`tests/unit/utils/test_file_readers.py` |
| [#1079](https://github.com/curdriceaurora/Local-File-Organizer/issues/1079) | `Pillow` | Image processing (EPUB thumbnails) | `tests/utils/test_epub_enhanced.py` |
| [#1084](https://github.com/curdriceaurora/Local-File-Organizer/issues/1084) | `pytest-benchmark` | Performance benchmarking | `tests/e2e/test_full_pipeline.py` |
| Exception applies | `rank_bm25` | BM25 search indexing | Multiple search/copilot test files |
| Exception applies | `sklearn` | Machine learning features | Analytics and vector search tests |

**Subtotal: 8+ tests** (optional dependency skips)

### Skip Pattern Reference

#### Pattern 1: Unconditional Skip with Issue Reference

```python
@pytest.mark.skip(reason="See #1073 - Phase 3 feature not yet implemented")
def test_future_feature():
    pass
```

#### Pattern 2: Platform-Specific Skip

```python
@pytest.mark.skipif(sys.platform == "win32", reason="See #1074 - signal pipe not available on Windows")
def test_unix_only_feature():
    pass
```

#### Pattern 3: Optional Dependency Skip

```python
def test_with_optional_dep():
    pytest.importorskip("ebooklib", reason="See #1079 - Optional EPUB processing dependency")
    # Test continues if import succeeds
```

### Verification Commands

```bash
# Show all skips with reasons
pytest tests/ -v -rs

# Count skip decorators by type
rg '@pytest.mark.skip\(' tests/ --type py -c
rg '@pytest.mark.skipif' tests/ --type py -c
rg 'pytest.importorskip' tests/ --type py -c

# Verify all skips have issue references
rg --pcre2 '@pytest.mark.skip\((?!.*reason=)' tests/  # Should return 0 matches
rg --pcre2 '@pytest.mark.skip.*reason="See #\d+' tests/  # All skips should match

# List all tracking issues
rg 'reason="See #(\d+)' tests/ --type py -o -r '$1' | sort | uniq -c | sort -rn
```

### Maintenance Guidelines

1. **Never leave a skip without a tracking issue** - Every `@pytest.mark.skip` and `@pytest.mark.skipif` must have `reason="See #NNN"`
2. **Use pytest.importorskip for optional dependencies** - Decorator-based skips should only be used for platform or environment conditions
3. **Delete irrelevant tests** - If a feature is permanently removed, delete its tests rather than leaving them skipped
4. **Document in tracking issues** - Each issue should explain:
   - Why the test is skipped
   - What needs to happen before it can be unskipped
   - Whether this is temporary (bug fix, feature implementation) or permanent (platform limitation)

### Related Documentation

- [GitHub Issue #1027](https://github.com/curdriceaurora/Local-File-Organizer/issues/1027) - Original audit task
- [pytest skip/xfail documentation](https://docs.pytest.org/en/stable/how-to/skipping.html)
- [pytest.importorskip API](https://docs.pytest.org/en/stable/reference/reference.html#pytest.importorskip)

---

**Last Updated:** 2026-03-30
**Audit Completed By:** auto-claude task #038