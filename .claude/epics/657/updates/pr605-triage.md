# PR #605 Triage Report

**PR**: https://github.com/curdriceaurora/Local-File-Organizer/pull/605
**Title**: Phase B test coverage sprint — raise CI gate from 74% → 95%
**Triaged**: 2026-03-08
**Reviewers**: CodeRabbit (116 comments), Copilot (5 comments)

---

## Summary

- Total inline comments fetched: 121
- Substantive findings classified: 121
- Comments filtered/excluded: 0 (no acknowledgement replies found — all reviewer findings, no author responses)
- New pattern candidates identified: 8

---

## Pattern Tally

| Pattern ID | Name | Count | Example (truncated) |
|------------|------|-------|---------------------|
| T1 | WEAK_ASSERTION | 48 | "assert len(hybrid_tags) >= 0 will always pass since any list has non-negative length" |
| G1 | ABSOLUTE_PATH | 34 | "Uses /tmp/nonexistent_daemon_test.pid, Unix-specific. Use tmp_path fixture" |
| UNKNOWN | (new candidates) | 13 | See section below |
| T8 | BRITTLE_ASSERTION | 6 | "Checking '42' in str(trash_path) can pass for unrelated path content" |
| T2 | MISSING_CALL_VERIFY | 4 | "Route tests verify call_count but not which template or what context rendered" |
| T7 | WRONG_PATCH_TARGET | 4 | "Patches _preview_archive then asserts on mock return — tests mock setup, not real code" |
| F2 | TYPE_ANNOTATION | 4 | "Bare list without generic type parameter in _FakeRecommendation (strict mypy violation)" |
| T5 | GLOBAL_STATE_LEAK | 3 | "type(mock_matrix).__name__ = 'ndarray' mutates MagicMock class globally, leaks to other tests" |
| T9 | RESOURCE_LEAK | 2 | "Background daemon started without guaranteed teardown if assertion fails (thread leak)" |
| T3 | WRONG_PAYLOAD | 1 | "assert call_count >= 1 without asserting specific callback target and payload shape" |
| D1 | INACCURATE_CLAIM | 1 | "PR description says 74%→95% but actual change in pyproject.toml is 91%→95%" |
| G4 | UNUSED_CODE | 1 | "numpy imported and used in test but not declared in repo dependencies" |

**Total classified**: 121

---

## UNKNOWN Findings (New Pattern Candidates)

### Candidate U1: MISSING_PARAMETRIZE
**Count**: 3 occurrences
**Description**: Near-identical test methods repeated N times instead of using `pytest.mark.parametrize`, reducing maintainability and hiding duplication.
**Examples**:
- Comment 19: "Six near-identical case-convention tests are a good candidate for parametrize" (`test_pattern_extractor_coverage.py`)
- Comment 26: "Recommendation tests follow same arrange/assert pattern, can be collapsed with parametrize" (`test_template_manager_coverage.py`)
- Comment 38: "Repeated (EBOOKLIB_AVAILABLE=True, BS4_AVAILABLE=True) setup should be centralized" (`test_epub_enhanced_coverage.py`)

### Candidate U2: WRONG_MOCK_ASYNC
**Count**: 2 occurrences
**Description**: Async methods mocked with synchronous `MagicMock` instead of `AsyncMock`, causing tests to not actually await the mock (silent test pass with wrong behavior).
**Example** (Comment 79): "Lines 100/110/121 mock read() as sync. Implementation uses `await settings_file.read()`. Use AsyncMock." (`test_settings_routes_coverage.py`)
**Example** (Comment 80): "mock_client.get.side_effect = ConnectionError('refused') but httpx raises httpx.ConnectError not builtin ConnectionError" (`test_settings_routes_coverage.py`)

### Candidate U3: WRONG_EXCEPTION_TYPE
**Count**: 2 occurrences
**Description**: Mock raises the wrong exception type — test passes because *an* exception is raised, but the production code would catch a different exception type entirely.
**Example** (Comment 80): "Using builtin ConnectionError instead of httpx.ConnectError — production httpx raises httpx.ConnectError on connection failure"
**Example** (Comment 79): Related — sync mock for async call means await never happens

### Candidate U4: MISLEADING_TEST_COMMENT
**Count**: 3 occurrences
**Description**: Inline test comments describe behavior that doesn't match what the code actually does, creating false confidence and confusing future maintainers.
**Examples**:
- Comment 58: "Comment about finally blocks is verbose and contradicts behavior (finally runs but last_result not assigned on exception)"
- Comment 97 (Copilot): "MemoryProfiler comment says finally assigns last_result, but assignment is after try/finally"
- Comment 101: "Batch sizer test comment says ImportError is expected but patch.dict causes AttributeError, not ImportError"

### Candidate U5: PLATFORM_SPECIFIC_FAILURE_INJECTION
**Count**: 2 occurrences
**Description**: Tests rely on Linux-specific filesystem paths (e.g., `/proc/impossible/`) to trigger I/O failures rather than mocking the failure. Couples tests to host OS and doesn't work on macOS/Windows.
**Example** (Comment 52): "Using /proc/impossible/... couples test to host filesystem behavior. Mock the move primitive to raise OSError instead." (`test_ai_file_mover_branches.py`)
**Example** (Comment 55): "Using /proc/ path for mkdir failure simulation is Linux-specific. Use monkeypatch/mock to force mkdir failure." (`test_para_folder_mapper_branches.py`)

### Candidate U6: WRONG_PATCH_LEVEL_FOR_BUILTINS
**Count**: 1 occurrence
**Description**: Patching `builtins.open` globally rather than at the module level where `open` is called, causing interference with pytest internals.
**Example** (Comment 67): "Patching builtins.open globally at line 185 can interfere with pytest. Patch at module level: `file_organizer.services.deduplication.dedup_extractor.open`" (`test_dedup_extractor_coverage.py`)

### Candidate U7: MISSING_CLEANUP_ASSERTION
**Count**: 1 occurrence
**Description**: Docstring or test name promises side-effect cleanup, but only the primary return value is asserted — the cleanup itself is never verified.
**Example** (Comment 25): "test_update_with_cleanup: docstring says failed update should clean up created profile, but test only checks `result is None`. Profile deletion not asserted." (`test_template_manager_coverage.py`)

### Candidate U8: WRONG_TIMESTAMP_FORMAT
**Count**: 1 occurrence
**Description**: Test SQL data or fixture data uses date-only strings (e.g., `"2024-01-01"`) where the codebase requires UTC ISO-8601 datetimes (e.g., `"2024-01-01T00:00:00Z"`), causing silent format mismatches.
**Example** (Comment 21): "Inserted timestamps are date-only strings, not UTC ISO-8601. Repository requires datetime format with Z suffix." (`test_preference_database_coverage.py`)

---

## Representative Examples for Top Patterns

### T1 WEAK_ASSERTION (48 occurrences — most common finding)

**Example A — Tautological assertion:**
> "assert len(hybrid_tags) >= 0 will always pass since any list has non-negative length. The comment acknowledges uncertainty about the expected outcome. Either strengthen the assertion or mark as skipped with explanation." (Comment 16)

**Example B — Non-falsifiable or/None assertion:**
> "assert num is None or num is not None always passes, so this test doesn't validate any behavior and won't catch regressions. If the goal is to cover the `if not parts: return None` branch, use a path whose .name is actually empty." (Comments 51, 96)

**Example C — Missing negative assertion:**
> "The stack-limit test currently proves only that one expected item is present; it does not fail when items beyond index 19 are still rendered. Add `assert len(rendered_items) <= 20`." (Comment 35)

**Example D — Incomplete test (no method call at all):**
> "test_set_status_with_app sets up mocks but never calls _set_status or asserts any behavior. This test will always pass without verifying the intended functionality." (Comments 33, 72)

### G1 ABSOLUTE_PATH (34 occurrences — second most common)

**Example A — /tmp/ hardcoded:**
> "Line 109 uses /tmp/nonexistent_daemon_test.pid, which is Unix-specific and violates the coding guideline to use platform-agnostic paths. This test will fail on Windows. Use tmp_path fixture." (Comment 2)

**Example B — /nonexistent/ pattern:**
> "Absolute /nonexistent/file.txt is not portable. Use tmp_path with a non-created file path instead." (Comments 13, 15)

**Example C — Root-anchored literals in test data structures:**
> "Hard-coded absolute paths in test payloads violate repo path guidance. Use relative or tmp_path-derived strings." (Comments 23, 47, 52, 53)

### T5 GLOBAL_STATE_LEAK (3 occurrences)

**Example — Class-level property mutation:**
> "type(mock_matrix).__name__ = 'ndarray' — since type(mock_matrix) is the MagicMock class itself, this change leaks into other tests within the same pytest worker and can affect unrelated assertions. Use a small custom class whose __name__ is already 'ndarray'." (Comment 95, Copilot)

---

## Key Observations

1. **T1 WEAK_ASSERTION dominates** at 48/121 (40%) — this PR was optimizing for coverage line count, not assertion quality. The reviewers consistently flagged tests that pass even when the feature regresses.

2. **G1 ABSOLUTE_PATH is endemic** at 34/121 (28%) — the PR used hardcoded `/tmp/`, `/nonexistent/`, `/proc/`, and root-anchored paths throughout. The repo has a clear guideline (use `tmp_path`), but it was systematically ignored.

3. **WEAK_ASSERTION sub-types** are highly diverse — tautologies (`>= 0`, `is None or not None`), incomplete tests (no assertion at all), permissive inequality (`>= 1`), type-only checks (`isinstance(..., int)`), substring-in-str checks. A single T1 bucket understates the variety.

4. **T5 GLOBAL_STATE_LEAK** is specifically the `type(MagicMock).__name__ = ...` anti-pattern — distinct from the catalog description which focuses on `type(MagicMock).prop = property(...)`. Both are the same root issue.

5. **New pattern U5 PLATFORM_SPECIFIC_FAILURE_INJECTION** (`/proc/impossible/`) appeared in PARA tests — a new test smell where Linux-only filesystem behavior is used to trigger error paths deterministically on Linux but silently skip on macOS/Windows.

6. **U2 WRONG_MOCK_ASYNC** is important and missing from the catalog — mocking async callables with sync MagicMock is a common Python mistake that causes tests to always pass (the await returns the MagicMock object instead of a coroutine, but the test doesn't detect the wrong behavior).
