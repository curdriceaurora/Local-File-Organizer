# Complexity Analysis: web/files_routes.py

**Date:** 2026-03-24
**Analyzer:** Claude (auto-claude task 005)
**File:** `src/file_organizer/web/files_routes.py`
**Total Lines:** 739

## Executive Summary

The `files_routes.py` module contains 11 functions with a total of 739 lines. Two functions exhibit high complexity and warrant refactoring:

1. **`_collect_entries`** (~147 lines) - Primary complexity hotspot
2. **`files_upload`** (~113 lines) - Secondary complexity hotspot

Both functions violate the Single Responsibility Principle and would benefit from extraction of distinct concerns into separate functions.

---

## Complexity Metrics by Function

| Function | Lines | Complexity | Status | Priority |
|----------|-------|------------|--------|----------|
| `_collect_entries` | 147 | **High** | 🔴 Needs Refactoring | P1 |
| `files_upload` | 113 | **High** | 🔴 Needs Refactoring | P1 |
| `_build_file_results_context` | 76 | Medium | 🟡 Monitor | P3 |
| `files_tree` | 72 | Medium | 🟡 Monitor | P3 |
| `files_preview` | 59 | Medium | 🟡 Monitor | P3 |
| `files_thumbnail` | 41 | Medium | 🟡 Monitor | P3 |
| `_build_breadcrumbs` | 35 | Low | 🟢 Good | - |
| `files_browser` | 35 | Low | 🟢 Good | - |
| `_list_tree_nodes` | 31 | Low | 🟢 Good | - |
| `files_list` | 29 | Low | 🟢 Good | - |
| `files_raw` | 23 | Low | 🟢 Good | - |

---

## Detailed Analysis

### 🔴 Priority 1: `_collect_entries` (Lines 122-269)

**Current Responsibilities:**
1. Directory scanning and file system iteration
2. Hidden file filtering
3. Query string filtering
4. File type filtering
5. Sorting by multiple criteria (name, size, created, modified, type)
6. Pagination logic
7. Building entry metadata dictionaries for directories
8. Building entry metadata dictionaries for files
9. Thumbnail URL generation

**Complexity Indicators:**
- **Lines of Code:** 147
- **Cyclomatic Complexity:** ~15+ (multiple conditional branches)
- **Nested Functions:** Contains `_creation_key` inner function
- **Responsibilities:** 9 distinct concerns

**Specific Issues:**
1. **Sorting Logic Duplication:** Lines 179-218 contain multiple similar sort operations with different key functions
2. **Entry Building Duplication:** Lines 229-247 (directories) and 249-267 (files) build similar dictionary structures
3. **Platform-Specific Code:** Lines 187-210 handle cross-platform file creation timestamps inline
4. **Complex Conditional Chain:** Lines 179-218 use if/elif chain for sort strategies

**Proposed Extractions:**

```python
# Extract to separate functions:
1. _filter_entries(children, include_hidden, query, file_type)
   - Lines 155-166: Filtering logic

2. _sort_entries(files, sort_by, sort_order, file_stats)
   - Lines 178-218: Sorting strategies

3. _get_file_stats(files, sort_by)
   - Lines 170-176: Stat collection

4. _get_creation_timestamp(stat_result)
   - Lines 188-209: Platform-specific creation time

5. _paginate_entries(directories, files, limit)
   - Lines 220-227: Pagination logic

6. _build_directory_entry(path)
   - Lines 229-247: Directory metadata

7. _build_file_entry(path)
   - Lines 249-267: File metadata
```

**Expected Outcome:**
- Main function reduced from 147 → ~30-40 lines
- Each extracted function has a single, clear responsibility
- Improved testability (can unit test sorting/filtering independently)
- Reduced cyclomatic complexity

---

### 🔴 Priority 2: `files_upload` (Lines 626-738)

**Current Responsibilities:**
1. Path resolution and validation
2. Query parameter normalization
3. File upload validation
4. Multi-file processing loop
5. Filename sanitization
6. File existence checking
7. Chunk-based file writing
8. File size validation
9. Error collection and formatting
10. Cleanup on failure
11. Success message generation
12. Context building for response

**Complexity Indicators:**
- **Lines of Code:** 113
- **Cyclomatic Complexity:** ~12+ (nested loops and conditionals)
- **Nested Loops:** Lines 664-716 contain a loop with multiple error scenarios
- **Responsibilities:** 12 distinct concerns

**Specific Issues:**
1. **Long Loop Body:** Lines 664-716 contain 52 lines of processing logic per file
2. **Repeated Cleanup Pattern:** Lines 671, 677, 683, 706, 713 all close upload.file
3. **Mixed Concerns:** Validation, processing, and error handling interleaved
4. **Error Handling Duplication:** Similar try/except patterns repeated

**Proposed Extractions:**

```python
# Extract to separate functions:
1. _validate_upload_request(path, files, settings)
   - Lines 648-656: Initial validation

2. _normalize_upload_params(view, sort_by, sort_order, limit)
   - Lines 658-661: Parameter normalization

3. _process_single_upload(upload, target_dir)
   - Lines 664-716: Single file upload logic
   - Returns: Result[success_count, error_message]

4. _validate_upload_filename(upload)
   - Lines 665-678: Filename validation

5. _save_upload_file(upload, destination)
   - Lines 686-714: Chunk writing with size validation

6. _format_upload_messages(saved, errors)
   - Lines 718-721: Message generation
```

**Expected Outcome:**
- Main function reduced from 113 → ~40-50 lines
- Upload processing loop simplified to single function call
- Reduced duplication in error handling
- Better separation of validation vs. processing

---

### 🟡 Medium Complexity Functions (Monitor)

#### `_build_file_results_context` (Lines 272-347, 76 lines)
- **Status:** Acceptable for a context-building function
- **Concern:** Multiple responsibilities but they are cohesive (all template context)
- **Recommendation:** Monitor; consider extraction if it grows beyond 100 lines

#### `files_tree` (Lines 423-494, 72 lines)
- **Status:** Acceptable for a route handler
- **Concern:** Mix of business logic and response building
- **Recommendation:** Consider extracting tree node building logic (lines 448-477)

#### `files_preview` (Lines 565-623, 59 lines)
- **Status:** Acceptable
- **Concern:** Multiple conditional branches for different file types
- **Recommendation:** Monitor; could extract preview content generation

#### `files_thumbnail` (Lines 497-537, 41 lines)
- **Status:** Acceptable
- **Concern:** Conditional chain for different thumbnail types
- **Recommendation:** Could benefit from strategy pattern but not urgent

---

## Code Quality Observations

### ✅ Strengths

1. **Good Documentation:** All functions have clear docstrings
2. **Type Hints:** Comprehensive type annotations throughout
3. **Error Handling:** Consistent use of try/except with ApiError
4. **Separation of Concerns:** Helper functions extracted to `_helpers` module
5. **Naming Convention:** Clear naming with `_` prefix for private functions

### ⚠️ Areas for Improvement

1. **Function Length:** Two functions exceed 100 lines (typical threshold: 50-75)
2. **Cyclomatic Complexity:** `_collect_entries` has 15+ decision points
3. **Code Duplication:**
   - Entry dictionary building (directories vs. files)
   - File cleanup in upload error handling
   - Similar error handling patterns
4. **Mixed Abstraction Levels:** Low-level file I/O mixed with high-level business logic
5. **Testing Challenges:** Complex functions are harder to unit test in isolation

---

## Refactoring Strategy

### Phase 1: Extract `_collect_entries` Components
**Effort:** Medium | **Impact:** High | **Risk:** Low

1. Create `src/file_organizer/web/_file_collection.py` module
2. Extract filtering functions
3. Extract sorting functions
4. Extract entry building functions
5. Refactor `_collect_entries` to orchestrate extracted functions
6. Add unit tests for each extracted function

**Expected Metrics:**
- `_collect_entries`: 147 → ~40 lines (-73% reduction)
- Cyclomatic complexity: 15+ → ~5 (-67% reduction)
- New testable functions: 7

### Phase 2: Extract `files_upload` Components
**Effort:** Medium | **Impact:** High | **Risk:** Medium

1. Create `src/file_organizer/web/_upload_handler.py` module
2. Extract validation functions
3. Extract single-file upload processing
4. Refactor `files_upload` to use extracted components
5. Add unit tests for upload validation and processing

**Expected Metrics:**
- `files_upload`: 113 → ~50 lines (-56% reduction)
- Cyclomatic complexity: 12+ → ~6 (-50% reduction)
- New testable functions: 6

### Phase 3: Review Medium Complexity Functions (Optional)
**Effort:** Low | **Impact:** Medium | **Risk:** Low

1. Monitor `_build_file_results_context` for growth
2. Consider extracting tree building logic from `files_tree`
3. Evaluate strategy pattern for thumbnail generation

---

## Risk Assessment

| Refactoring | Risk Level | Mitigation |
|-------------|-----------|------------|
| Extract filtering logic | **Low** | Pure functions, easy to test |
| Extract sorting logic | **Low** | Well-defined inputs/outputs |
| Extract entry building | **Low** | No side effects |
| Extract upload processing | **Medium** | File I/O and cleanup handling |
| Extract validation | **Low** | Stateless validation |

---

## Dependencies and Impact

### Affected Modules
- `src/file_organizer/web/files_routes.py` (primary)
- `src/file_organizer/web/_helpers.py` (may need additional helpers)

### New Modules to Create
- `src/file_organizer/web/_file_collection.py` (Phase 1)
- `src/file_organizer/web/_upload_handler.py` (Phase 2)

### Test Coverage Requirements
- Unit tests for all extracted functions
- Integration tests for refactored route handlers
- Regression tests for existing functionality

---

## Recommendations

### Immediate Actions (Sprint 1)
1. ✅ **Refactor `_collect_entries`** (Priority 1)
   - Extract sorting strategies
   - Extract filtering logic
   - Extract entry builders

2. ✅ **Refactor `files_upload`** (Priority 1)
   - Extract validation
   - Extract single-file processing
   - Simplify error handling

### Future Considerations (Sprint 2+)
1. ⏭️ Consider strategy pattern for thumbnail generation
2. ⏭️ Extract tree building logic if `files_tree` grows
3. ⏭️ Add complexity linting (e.g., `radon`, `mccabe`) to CI/CD

---

## Appendix: Complexity Calculation Method

**Cyclomatic Complexity Estimation:**
- Based on McCabe's cyclomatic complexity metric
- Counted: if, elif, for, while, except, and, or, ternary operators
- Thresholds:
  - 1-5: Low (simple)
  - 6-10: Medium (moderate)
  - 11-20: High (complex)
  - 21+: Very High (needs immediate attention)

**Lines of Code:**
- Counted executable lines (excluding docstrings, comments, blank lines)
- Thresholds:
  - 0-50: Acceptable
  - 51-100: Monitor
  - 101-200: Consider refactoring
  - 201+: Immediate refactoring needed
