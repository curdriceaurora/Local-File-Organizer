# Complexity Analysis: cli/undo_redo.py

**Analysis Date:** 2026-03-24
**File:** `src/file_organizer/cli/undo_redo.py`
**Total Lines:** 352
**Functions:** 6

## Executive Summary

The `cli/undo_redo.py` module provides CLI commands for undo/redo operations. While functionally complete, it suffers from significant code duplication and high cyclomatic complexity in the main command functions. The primary issues are:

1. **High duplication** between `undo_command` and `redo_command` (~70% code similarity)
2. **Deep nesting** in dry-run logic (up to 4 levels)
3. **Repeated patterns** for logging setup, resource management, and output formatting
4. **Long functions** with multiple responsibilities

## Complexity Metrics

### Function Analysis

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `undo_command` | 101 | High | Deep nesting, multiple exit points, code duplication |
| `redo_command` | 81 | High | Nearly identical to undo_command |
| `history_command` | 64 | Medium | Multiple conditional branches |
| `main_undo` | 19 | Low | Simple argument parsing |
| `main_redo` | 14 | Low | Simple argument parsing |
| `main_history` | 32 | Low | Simple argument parsing |

## Identified Complexity Issues

### 1. Code Duplication (Critical)

**Location:** `undo_command` (lines 19-119) and `redo_command` (lines 122-202)

**Problem:** These functions share approximately 70% of their code:
- Identical logging setup (lines 36-39 vs 135-138)
- Identical resource management pattern (try/finally with manager.close())
- Identical operation display logic
- Identical success/failure handling
- Identical error handling

**Impact:**
- Maintenance burden: bugs must be fixed in two places
- Testing overhead: similar test cases needed for both
- Increased file size and cognitive load

**Example Duplication:**
```python
# undo_command (lines 36-39)
if verbose:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

# redo_command (lines 135-138) - IDENTICAL
if verbose:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)
```

### 2. Deep Nesting in Dry-Run Logic (High)

**Location:** `undo_command` lines 46-93, `redo_command` lines 144-179

**Problem:** Dry-run preview logic has 4 levels of nesting:
```
if dry_run:
    if operation_id:
        can_undo, reason = ...
        if can_undo:
            operations = [...]
            if operations:  # Level 4
                ...
```

**Impact:**
- Hard to read and understand
- Easy to introduce bugs
- Difficult to test individual branches

### 3. Repeated Operation Display Logic (Medium)

**Location:** Multiple locations in both undo and redo commands

**Problem:** Operation details are displayed in identical ways at:
- Lines 52-58 (undo dry-run with operation_id)
- Lines 82-87 (undo dry-run without specific ID)
- Lines 151-157 (redo dry-run with operation_id)
- Lines 168-173 (redo dry-run without specific ID)

**Example:**
```python
# This pattern appears 4 times with slight variations
print(f"\nWould undo operation {operation_id}:")
print(f"  Type: {op.operation_type.value}")
print(f"  Source: {op.source_path}")
if op.destination_path:
    print(f"  Destination: {op.destination_path}")
```

### 4. Transaction Display Logic Duplication (Medium)

**Location:** Lines 66-77 in `undo_command`

**Problem:** Transaction preview logic exists only in undo but uses a repeated pattern:
- Get transaction
- Get operations
- Display count
- Loop through first 5 operations
- Show "and X more" message

This logic could be extracted and potentially reused.

### 5. Multiple Responsibilities (Medium)

**Location:** Both `undo_command` and `redo_command`

**Problem:** Each function handles:
- Logging configuration
- Manager initialization
- Dry-run preview (with multiple sub-cases)
- Actual operation execution (with multiple sub-cases)
- Success/failure reporting
- Error handling
- Resource cleanup

**Impact:**
- Functions are too long (100+ lines)
- Hard to test individual concerns
- Violates Single Responsibility Principle

### 6. Inconsistent Error Handling (Low)

**Location:** Lines 267-268 in `history_command`

**Problem:** Uses `if "viewer" in locals()` check instead of the clearer pattern used in undo/redo:
```python
# history_command uses:
if "viewer" in locals():
    viewer.close()

# vs undo/redo pattern:
if manager is not None:
    manager.close()
```

## Refactoring Opportunities

### Priority 1: Extract Common Display Functions

**Complexity Reduction:** High
**Risk:** Low

Create helper functions for repeated display patterns:

```python
def _display_operation_preview(op, action: str = "undo") -> None:
    """Display operation preview for dry-run mode."""
    print(f"\nWould {action} operation {op.id}:")
    print(f"  Type: {op.operation_type.value}")
    print(f"  Source: {op.source_path}")
    if op.destination_path:
        print(f"  Destination: {op.destination_path}")

def _display_transaction_preview(manager, transaction_id: str) -> bool:
    """Display transaction preview. Returns True if found, False otherwise."""
    transaction = manager.history.get_transaction(transaction_id)
    if transaction:
        operations = manager.history.get_operations(transaction_id=transaction_id)
        print(f"  Operations: {len(operations)}")
        for op in operations[:5]:
            print(f"    - {op.operation_type.value}: {op.source_path.name}")
        if len(operations) > 5:
            print(f"    ... and {len(operations) - 5} more")
        return True
    return False
```

**Lines Saved:** ~40-50 lines
**Files Affected:** 1

### Priority 2: Extract Dry-Run Logic

**Complexity Reduction:** High
**Risk:** Low

Create separate functions for dry-run preview logic:

```python
def _preview_undo(
    manager: UndoManager,
    operation_id: int | None,
    transaction_id: str | None,
) -> int:
    """Preview undo operation in dry-run mode."""
    # Move lines 46-93 here
    ...

def _preview_redo(
    manager: UndoManager,
    operation_id: int | None,
) -> int:
    """Preview redo operation in dry-run mode."""
    # Move lines 144-179 here
    ...
```

**Lines Saved:** ~50-60 lines from main functions
**Complexity Reduction:** Reduces nesting in main functions
**Files Affected:** 1

### Priority 3: Extract Logging Configuration

**Complexity Reduction:** Medium
**Risk:** Low

Create a helper function for common logging setup:

```python
def _configure_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level)
```

**Lines Saved:** ~6 lines (appears 3 times)
**Files Affected:** 1

### Priority 4: Extract Execution Logic

**Complexity Reduction:** High
**Risk:** Medium

Create helper functions for actual undo/redo execution:

```python
def _execute_undo(
    manager: UndoManager,
    operation_id: int | None,
    transaction_id: str | None,
) -> bool:
    """Execute undo operation."""
    if transaction_id:
        print(f"Undoing transaction {transaction_id}...")
        return manager.undo_transaction(transaction_id)
    elif operation_id:
        print(f"Undoing operation {operation_id}...")
        return manager.undo_operation(operation_id)
    else:
        print("Undoing last operation...")
        return manager.undo_last_operation()

def _execute_redo(
    manager: UndoManager,
    operation_id: int | None,
) -> bool:
    """Execute redo operation."""
    if operation_id:
        print(f"Redoing operation {operation_id}...")
        return manager.redo_operation(operation_id)
    else:
        print("Redoing last operation...")
        return manager.redo_last_operation()
```

**Lines Saved:** ~10-15 lines
**Files Affected:** 1

### Priority 5: Create Command Base Class (Optional)

**Complexity Reduction:** High
**Risk:** High

Create a base class for common command patterns:

```python
class BaseCommand:
    """Base class for CLI commands with common functionality."""

    def __init__(self, verbose: bool = False):
        self._configure_logging(verbose)

    def _configure_logging(self, verbose: bool) -> None:
        """Configure logging based on verbosity level."""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level)

    def _display_success(self, action: str) -> None:
        """Display success message."""
        print(f"✓ {action} successful")

    def _display_failure(self, action: str) -> None:
        """Display failure message."""
        print(f"✗ {action} failed")
```

**Note:** This is a more significant refactoring that would require changes to function signatures and calling patterns. Consider this for a future iteration.

## Proposed Extraction Plan

### Phase 1: Low-Risk Extractions (Recommended for immediate implementation)

1. **Extract `_configure_logging` helper**
   - Lines: 36-39, 135-138, 234-237
   - Risk: Low
   - Test: Verify logging levels are set correctly

2. **Extract `_display_operation_preview` helper**
   - Lines: 52-58, 82-87, 151-157, 168-173
   - Risk: Low
   - Test: Verify output formatting is identical

3. **Extract `_display_transaction_preview` helper**
   - Lines: 66-77
   - Risk: Low
   - Test: Verify transaction display logic

### Phase 2: Medium-Risk Extractions

4. **Extract `_preview_undo` function**
   - Lines: 46-93
   - Risk: Medium (complex control flow)
   - Test: Comprehensive dry-run tests for all cases

5. **Extract `_preview_redo` function**
   - Lines: 144-179
   - Risk: Medium (complex control flow)
   - Test: Comprehensive dry-run tests for all cases

6. **Extract `_execute_undo` function**
   - Lines: 96-111
   - Risk: Medium (core functionality)
   - Test: All existing undo tests

7. **Extract `_execute_redo` function**
   - Lines: 182-194
   - Risk: Medium (core functionality)
   - Test: All existing redo tests

### Phase 3: Cleanup

8. **Refactor `undo_command` to use helpers**
   - Simplify main function to ~30 lines
   - Use extracted helpers

9. **Refactor `redo_command` to use helpers**
   - Simplify main function to ~25 lines
   - Use extracted helpers

10. **Standardize resource cleanup in `history_command`**
    - Change lines 267-268 to use `if viewer is not None:` pattern
    - Initialize `viewer = None` at start

## Expected Outcomes

### After Refactoring

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Lines | 352 | ~280 | -20% |
| `undo_command` Lines | 101 | ~35 | -65% |
| `redo_command` Lines | 81 | ~30 | -63% |
| Code Duplication | High | Low | -70% |
| Max Nesting Depth | 4 | 2 | -50% |
| Cyclomatic Complexity | High | Medium | Significant |

### Benefits

1. **Maintainability:** Bugs only need to be fixed once
2. **Readability:** Main functions become high-level overviews
3. **Testability:** Helpers can be tested independently
4. **Reusability:** Display/execution logic can be reused
5. **Consistency:** Ensures uniform behavior across commands

### Risks

1. **Testing Required:** All extraction must maintain behavior
2. **Import Changes:** May need to adjust imports if helpers are moved
3. **Backward Compatibility:** Function signatures should remain the same

## Testing Strategy

### For Each Extraction

1. **Before Extraction:**
   - Run existing test suite
   - Document current behavior

2. **After Extraction:**
   - Run test suite again (must pass)
   - Add unit tests for new helper functions
   - Test edge cases explicitly

3. **Integration Testing:**
   - Test all command-line argument combinations
   - Test dry-run vs actual execution
   - Test error conditions

### Critical Test Cases

- Undo with operation_id (dry-run and actual)
- Undo with transaction_id (dry-run and actual)
- Undo last operation (dry-run and actual)
- Redo with operation_id (dry-run and actual)
- Redo last operation (dry-run and actual)
- Error handling when operation not found
- Error handling when operation cannot be undone/redone
- Logging configuration (verbose vs normal)
- Resource cleanup (manager.close() called)

## Implementation Notes

### Naming Conventions

- Use `_` prefix for private/helper functions
- Keep function names descriptive and action-oriented
- Match existing code style (snake_case)

### Code Organization

All extracted functions should remain in the same file initially to:
- Minimize import changes
- Keep related code together
- Simplify testing

Future iteration could move helpers to a separate `cli/helpers.py` or `cli/command_utils.py` module.

### Documentation

Each extracted function should have:
- Docstring with description
- Args documentation
- Returns documentation
- Type hints

## Recommendations

### Immediate Actions (This Sprint)

1. ✅ Extract `_configure_logging` helper
2. ✅ Extract `_display_operation_preview` helper
3. ✅ Extract `_display_transaction_preview` helper

### Next Sprint

4. Extract `_preview_undo` and `_preview_redo` functions
5. Extract `_execute_undo` and `_execute_redo` functions
6. Refactor main command functions to use helpers

### Future Consideration

7. Consider creating a `cli/command_utils.py` module for helpers
8. Evaluate base class approach for common CLI patterns
9. Add comprehensive integration tests for CLI commands

## Conclusion

The `cli/undo_redo.py` module has significant complexity issues primarily due to code duplication and deep nesting. The proposed refactoring plan can reduce complexity by ~65% in the main functions while improving maintainability and testability. The extraction plan is designed to be low-risk with incremental improvements that can be tested independently.

**Priority:** High
**Effort:** Medium (2-3 days)
**Risk:** Low-Medium (with proper testing)
**ROI:** High (significant complexity reduction and maintainability improvement)
