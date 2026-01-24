---
name: code-quality-audit
created: 2026-01-24T03:00:00Z
updated: 2026-01-24T03:00:00Z
status: in-progress
---

# Code Quality Audit - Sprint 2026 Q1

## Purpose

Apply patterns from Day 1 bug fixes (#75, #77, #78) across the entire codebase to prevent similar issues from recurring.

## Bug Fix Patterns to Apply

### Pattern 1: File Locking for Concurrent Access

**Original Fix**: Issue #75 - Added fcntl locking to backup.py

**Problem**: Race conditions when multiple processes read/write same file
**Solution**: Use fcntl for shared (read) and exclusive (write) locks

**Files That Need Locking**:

```python
# Files found with write operations that might need locking:

1. src/file_organizer/services/intelligence/folder_learner.py:82
   - Method: _save_preferences()
   - Risk: Medium - User corrections written concurrently
   - Fix: Add fcntl.LOCK_EX during write

2. src/file_organizer/services/intelligence/preference_store.py:240
   - Method: save()
   - Risk: HIGH - Core preference storage
   - Fix: Already uses temp file + atomic rename, but add fcntl for safety

3. src/file_organizer/services/suggestion_feedback.py:90
   - Method: save_feedback()
   - Risk: Medium - Feedback file might be written concurrently
   - Fix: Add fcntl.LOCK_EX during write

4. src/file_organizer/services/auto_tagging/tag_learning.py:115
   - Method: _save_tags()
   - Risk: Medium - Tag storage concurrent access
   - Fix: Add fcntl.LOCK_EX during write

5. src/file_organizer/history/export.py:45,78,112,145
   - Methods: export_to_json(), export_to_csv(), export_to_html(), export_to_markdown()
   - Risk: Low - Export typically single-user operation
   - Fix: Optional - add for consistency
```

**Implementation Pattern**:

```python
import fcntl

# For reads (shared lock - multiple readers OK)
def _load_data(self) -> Dict:
    with open(self.file_path, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            data = json.load(f)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return data

# For writes (exclusive lock - only one writer)
def _save_data(self, data: Dict) -> None:
    with open(self.file_path, 'w') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Task**: Create Issue for batch fix of file locking

---

### Pattern 2: Parameter Validation

**Original Fix**: Issue #78 - Added chunk_size validation in hasher.py

**Problem**: No validation of constructor parameters leading to runtime errors
**Solution**: Add MIN/MAX constants, type checking, and range validation

**Parameters That Need Validation**:

```python
# Found parameters without validation:

1. src/file_organizer/history/cleanup.py:30
   - Parameter: max_operations (int)
   - Risk: HIGH - Could be negative or too large
   - Fix: Add MIN (1) and MAX (1,000,000) validation

2. src/file_organizer/history/cleanup.py:31
   - Parameter: max_age_days (int)
   - Risk: Medium - Could be negative
   - Fix: Add MIN (1) validation

3. src/file_organizer/services/smart_suggestions.py:35
   - Parameter: min_confidence (float)
   - Risk: Medium - Should be 0.0-100.0
   - Fix: Add range validation (0.0 <= x <= 100.0)

4. src/file_organizer/services/misplacement_detector.py:38
   - Parameter: min_mismatch_score (float)
   - Risk: Medium - Should be 0.0-100.0
   - Fix: Add range validation (0.0 <= x <= 100.0)

5. src/file_organizer/services/deduplication/document_dedup.py:32
   - Parameter: max_features (int)
   - Risk: Low - Could be too small or large
   - Fix: Add MIN (100) and MAX (50,000) validation

6. src/file_organizer/services/deduplication/embedder.py:33
   - Parameter: max_features (int)
   - Risk: Low - Could be too small or large
   - Fix: Add MIN (100) and MAX (50,000) validation

7. src/file_organizer/services/auto_tagging/content_analyzer.py:33
   - Parameters: min_keyword_length (int), max_keywords (int)
   - Risk: Medium - Could be invalid ranges
   - Fix: Validate min_keyword_length >= 1, max_keywords >= 1

8. src/file_organizer/services/pattern_analyzer.py:37
   - Parameters: min_pattern_count (int), max_depth (int)
   - Risk: Medium - Could be < 1 or unreasonably large
   - Fix: Validate >= 1, max_depth <= 100
```

**Implementation Pattern**:

```python
class MyService:
    MIN_PARAM = 1
    MAX_PARAM = 10000

    def __init__(self, param: int = 100):
        # Type validation
        if not isinstance(param, int):
            raise ValueError(
                f"param must be an integer, got {type(param).__name__}"
            )

        # Range validation
        if param < self.MIN_PARAM:
            raise ValueError(
                f"param must be at least {self.MIN_PARAM}, got {param}"
            )

        if param > self.MAX_PARAM:
            raise ValueError(
                f"param must not exceed {self.MAX_PARAM}, got {param}"
            )

        self.param = param
```

**Task**: Create Issue for batch fix of parameter validation

---

### Pattern 3: Misleading Feature Claims

**Original Fix**: Issue #77 - Removed .doc from supported formats

**Problem**: Advertising support for formats that aren't actually implemented
**Solution**: Only list formats that are truly supported with working readers

**Areas to Audit**:

```python
# Files to check for misleading claims:

1. src/file_organizer/utils/file_readers.py
   - Status: ✅ FIXED (Issue #77)
   - Only lists supported formats

2. README.md - Supported File Types section
   - Status: NEEDS AUDIT
   - Check: Are all listed formats actually supported?
   - Check: Are there unsupported features mentioned?

3. src/file_organizer/services/text_processor.py:SUPPORTED_EXTENSIONS
   - Status: NEEDS AUDIT
   - Verify each extension has working reader
   - Test each format with real files

4. src/file_organizer/services/vision_processor.py:SUPPORTED_VIDEO_FORMATS
   - Status: NEEDS AUDIT
   - Verify all video formats work with current implementation
   - Check codec support

5. Documentation in docstrings
   - Status: NEEDS AUDIT
   - Search for "supports", "handles", "processes"
   - Verify claims match implementation
```

**Implementation Pattern**:

```python
# Good: Only list what's implemented
SUPPORTED_FORMATS = {
    '.txt': read_text_file,
    '.md': read_markdown_file,
    '.pdf': read_pdf_file,
    '.docx': read_docx_file,  # Note: .doc NOT supported
}

# Add clear documentation
def process_file(file_path: Path) -> ProcessedFile:
    """
    Process supported file formats.

    Supported formats:
    - Text: .txt, .md
    - Documents: .pdf, .docx (NOT .doc)
    - Spreadsheets: .xlsx (NOT .xls)

    Args:
        file_path: Path to file

    Raises:
        ValueError: If file format is not supported
    """
    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: {ext}. "
            f"Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        )
```

**Task**: Create Issue for documentation audit

---

## Implementation Plan

### Phase 1: Immediate Fixes (High Priority)

**Create Issues**:
1. Issue: Add file locking to preference storage files
   - Priority: HIGH
   - Files: 5 identified
   - Estimate: 2 hours
   - Target: Day 3

2. Issue: Add parameter validation to all __init__ methods
   - Priority: HIGH
   - Files: 8+ identified
   - Estimate: 3 hours
   - Target: Day 4

3. Issue: Audit and fix misleading format support claims
   - Priority: MEDIUM
   - Files: Documentation + code
   - Estimate: 2 hours
   - Target: Day 5

### Phase 2: Systematic Code Review (Medium Priority)

**Create Tasks**:
1. Add tests for concurrent file access scenarios
2. Add tests for parameter validation edge cases
3. Add integration tests for all "supported" formats
4. Update documentation with accurate feature lists

### Phase 3: Prevention (Ongoing)

**Add to Code Review Checklist**:
- [ ] All file writes use appropriate locking
- [ ] All constructor parameters are validated
- [ ] All "supported" features are actually tested
- [ ] Documentation matches implementation

**Add to CCPM Quality Standards** (CLAUDE.md):
- Require validation for all numeric parameters
- Require file locking for any concurrent-access files
- Require tests for all advertised features
- Prohibit "TODO" comments claiming future support

---

## Testing Requirements

### For File Locking Fixes

```python
def test_concurrent_writes():
    """Test that concurrent writes don't corrupt file."""
    import multiprocessing

    def writer(n):
        service = MyService()
        for i in range(10):
            service.save_data({"process": n, "iteration": i})

    # Run 5 processes writing concurrently
    processes = [
        multiprocessing.Process(target=writer, args=(i,))
        for i in range(5)
    ]

    for p in processes:
        p.start()
    for p in processes:
        p.join()

    # Verify file is not corrupted
    data = service.load_data()
    assert data is not None
```

### For Parameter Validation Fixes

```python
def test_parameter_validation():
    """Test that invalid parameters are rejected."""
    # Type validation
    with pytest.raises(ValueError, match="must be an integer"):
        MyService(param="invalid")

    # Range validation
    with pytest.raises(ValueError, match="at least"):
        MyService(param=-1)

    with pytest.raises(ValueError, match="not exceed"):
        MyService(param=999999999)

    # Valid values work
    service = MyService(param=100)
    assert service.param == 100
```

### For Format Support Fixes

```python
def test_all_supported_formats():
    """Test that all advertised formats actually work."""
    processor = TextProcessor()

    for ext in processor.SUPPORTED_FORMATS:
        # Create sample file with this extension
        sample_file = create_sample_file(ext)

        # Should not raise exception
        result = processor.process(sample_file)

        # Should return valid result
        assert result is not None
        assert result.description != ""
```

---

## Tracking

### GitHub Issues to Create

- [ ] Issue: Add file locking to concurrent-access files
- [ ] Issue: Add parameter validation to all constructors
- [ ] Issue: Audit and fix misleading format support claims
- [ ] Issue: Add concurrent access tests
- [ ] Issue: Add parameter validation tests
- [ ] Issue: Add format support integration tests

### CCPM Updates

- [ ] Add to execution-status.md under "Code Quality Improvements"
- [ ] Track in daily logs as completed
- [ ] Update sprint metrics with quality improvements

### PRs to Create

Following new PR strategy (task-level PRs):
- [ ] PR: File locking improvements
- [ ] PR: Parameter validation improvements
- [ ] PR: Documentation accuracy improvements

Each PR should be < 800 LOC and focused on one pattern.

---

## Success Criteria

**Code Quality Goals**:
- [ ] Zero race conditions in file operations
- [ ] 100% parameter validation coverage
- [ ] 100% accuracy in feature claims
- [ ] All new code follows these patterns from Day 1

**Testing Goals**:
- [ ] Concurrent access tests for all shared files
- [ ] Validation tests for all parameters
- [ ] Integration tests for all supported formats
- [ ] Coverage: 90%+ on all new/modified code

**Documentation Goals**:
- [ ] README accurately lists supported features
- [ ] All docstrings match implementation
- [ ] Migration guide for any breaking changes
- [ ] Code review checklist updated

---

**Next Steps**:
1. Create GitHub issues for identified problems (Day 3)
2. Implement fixes in priority order (Days 3-5)
3. Add comprehensive tests (Days 3-5)
4. Create task-level PRs as each fix completes
5. Update code review standards to prevent recurrence

**Owner**: Sprint team
**Timeline**: Days 3-5 (immediate), ongoing prevention
**Dependencies**: None - can start immediately
