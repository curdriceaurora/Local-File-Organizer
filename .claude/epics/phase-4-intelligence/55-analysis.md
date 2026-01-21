---
issue: 55
title: Build undo/redo functionality
analyzed: 2026-01-21T06:26:33Z
estimated_hours: 24
parallelization_factor: 2.3
---

# Parallel Work Analysis: Issue #55

## Overview
Implement a reliable undo/redo system that allows users to safely revert file organization operations, including both single and batch operations. Builds on the operation history tracking system (Task 53) to provide user-facing rollback capabilities.

## Parallel Streams

### Stream A: Undo Manager & Validation
**Scope**: Core undo/redo logic and pre-operation validation
**Files**:
- `file_organizer/undo/undo_manager.py`
- `file_organizer/undo/validator.py`
- `file_organizer/undo/models.py`
**Agent Type**: backend-specialist
**Can Start**: after Task 53 complete
**Estimated Hours**: 10 hours
**Dependencies**: Task 53 (operation history tracking)

**Deliverables**:
- UndoManager class with undo/redo operations
- undo_last_operation(), undo_operation(), undo_transaction()
- redo_last_operation(), redo_operation()
- Undo/redo stack management
- OperationValidator for pre-checks
- File integrity verification (hash comparison)
- Path availability checks
- Conflict detection
- Validation result reporting

### Stream B: Rollback Executor
**Scope**: Execution of rollback operations for all operation types
**Files**:
- `file_organizer/undo/rollback.py`
- `file_organizer/undo/recovery.py`
**Agent Type**: backend-specialist
**Can Start**: after Task 53 complete
**Estimated Hours**: 8 hours
**Dependencies**: Task 53

**Deliverables**:
- RollbackExecutor class
- rollback_move() - reverse move operations
- rollback_rename() - reverse rename operations
- rollback_delete() - restore from trash
- rollback_copy() - delete copied files
- rollback_transaction() - atomic batch rollback
- Partial rollback handling
- Error recovery procedures
- Rollback result reporting
- Trash management for delete operations

### Stream C: History Viewer & CLI
**Scope**: User interface for viewing and interacting with history
**Files**:
- `file_organizer/undo/viewer.py`
- `file_organizer/cli/undo.py` (new CLI subcommand)
- `file_organizer/cli/history.py` (new CLI subcommand)
**Agent Type**: fullstack-specialist
**Can Start**: after Task 53 complete
**Estimated Hours**: 4 hours
**Dependencies**: Task 53

**Deliverables**:
- HistoryViewer class for CLI display
- show_recent_operations() with formatting
- show_transaction_details()
- filter_operations() by type, date, path
- search_by_path() for path-specific history
- CLI commands: undo, redo, history
- Interactive confirmation prompts
- Progress indicators for batch operations
- Rich formatting for terminal output

### Stream D: Integration & Testing
**Scope**: Integration with file operations and comprehensive testing
**Files**:
- `file_organizer/undo/__init__.py`
- Integration points in `file_organizer/core/organizer.py`
- `tests/undo/test_undo_manager.py`
- `tests/undo/test_validator.py`
- `tests/undo/test_rollback.py`
- `tests/undo/test_viewer.py`
- `tests/integration/test_undo_redo_e2e.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A, B, C complete
**Estimated Hours**: 2 hours
**Dependencies**: Streams A, B, C

**Deliverables**:
- Integration with file operation services
- Unit tests for all components (>90% coverage)
- Integration tests for end-to-end undo/redo
- Edge case tests (conflicts, missing files, permission errors)
- Performance tests (undo 100 operations in <5s)
- User acceptance tests
- Documentation with usage examples

## Coordination Points

### Shared Files
Minimal overlap:
- `file_organizer/undo/__init__.py` - Stream D updates after A, B, C complete
- Core organizer files - Stream D adds integration hooks

### Interface Contracts
To enable parallel work, define these interfaces upfront:

**UndoManager Interface**:
```python
def undo_last_operation() -> bool
def undo_operation(operation_id: int) -> bool
def undo_transaction(transaction_id: str) -> bool
def redo_last_operation() -> bool
def redo_operation(operation_id: int) -> bool
def can_undo(operation_id: int) -> Tuple[bool, str]
def can_redo(operation_id: int) -> Tuple[bool, str]
def get_undo_stack() -> List[Operation]
def get_redo_stack() -> List[Operation]
def clear_redo_stack() -> None
```

**OperationValidator Interface**:
```python
def validate_undo(operation: Operation) -> ValidationResult
def validate_redo(operation: Operation) -> ValidationResult
def check_file_integrity(path: Path, expected_hash: str) -> bool
def check_path_availability(path: Path) -> bool
def check_conflicts(operation: Operation) -> List[Conflict]
```

**RollbackExecutor Interface**:
```python
def rollback_move(operation: Operation) -> bool
def rollback_rename(operation: Operation) -> bool
def rollback_delete(operation: Operation) -> bool
def rollback_copy(operation: Operation) -> bool
def rollback_transaction(transaction_id: str) -> RollbackResult
```

**HistoryViewer Interface**:
```python
def show_recent_operations(limit: int = 10) -> None
def show_transaction_details(transaction_id: str) -> None
def show_operation_details(operation_id: int) -> None
def filter_operations(filters: dict) -> List[Operation]
def search_by_path(path: Path) -> List[Operation]
```

**Data Models**:
```python
@dataclass
class ValidationResult:
    can_proceed: bool
    conflicts: List[Conflict]
    warnings: List[str]
    error_message: Optional[str]

@dataclass
class RollbackResult:
    success: bool
    operations_rolled_back: int
    operations_failed: int
    errors: List[Tuple[int, str]]
```

### Sequential Requirements
1. Streams A, B, C can all run in parallel after Task 53 completes
2. Stream D (integration/testing) must wait for A, B, C to complete
3. Interface contracts and data models must be agreed upon before starting
4. **Hard Dependency**: Task 53 must be complete before any stream can start

## Conflict Risk Assessment
**Low Risk** - Streams work on completely different files:
- Stream A: `undo_manager.py`, `validator.py`, `models.py`
- Stream B: `rollback.py`, `recovery.py`
- Stream C: `viewer.py`, `cli/undo.py`, `cli/history.py`
- Stream D: `__init__.py`, integration points, `tests/**/*`

No shared implementation files between A, B, and C.

## Parallelization Strategy

**Recommended Approach**: parallel after dependency, with final integration

**Execution Plan**:
1. **Pre-work** (0.5 hours): Define and document interface contracts and data models
2. **Wait for dependency**: Task 53 must complete first
3. **Phase 1** (parallel, 10 hours): Launch Streams A, B, C simultaneously
4. **Phase 2** (sequential, 2 hours): Stream D integrates and tests

**Timeline**:
- Stream A: 10 hours
- Stream B: 8 hours (completes early)
- Stream C: 4 hours (completes early)
- Stream D: 2 hours (after Phase 1)

Total wall time: ~12.5 hours (including coordination, after Task 53)

## Expected Timeline

**With parallel execution**:
- Wall time: ~12.5 hours (pre-work + max(A,B,C) + D) after Task 53
- Total work: 24 hours
- Efficiency gain: 48% time savings

**Without parallel execution**:
- Wall time: 24 hours (sequential completion) after Task 53

**Parallelization factor**: 2.3x effective speedup (24h / 10.4h actual)

## Agent Assignment Recommendations

- **Stream A**: Senior backend developer with state management expertise
- **Stream B**: Backend developer familiar with file system operations
- **Stream C**: Fullstack developer with CLI/UX experience
- **Stream D**: QA engineer or full-stack developer for testing and integration

## Notes

### Success Factors
- Clear interface contracts prevent integration issues
- Streams A, B, C are independent after Task 53 completes
- Task 53 provides solid foundation for rollback operations
- Stream D benefits from having all components ready
- Validation-first approach prevents unsafe undo operations

### Risks & Mitigation
- **Risk**: File integrity compromised between operation and undo
  - **Mitigation**: Stream A implements hash verification, refuses undo if file changed
- **Risk**: Undo creates new conflicts
  - **Mitigation**: Stream A includes comprehensive validation before undo
- **Risk**: Partial rollback failure in transactions
  - **Mitigation**: Stream B implements atomic rollback with recovery procedures
- **Risk**: User confusion about undo/redo state
  - **Mitigation**: Stream C provides clear UI and history viewer

### Performance Targets
- Single undo: <100ms
- Batch undo: 100 operations in <5 seconds
- Validation: <50ms per operation
- Redo operation: <100ms
- History query: <100ms
- Stack operations: O(1) time complexity

### Design Considerations
- Delete operations move files to trash (not permanent delete)
- Trash location: `~/.file_organizer/trash/`
- Trash retention: 30 days default
- Undo operations are logged in history
- Redo stack cleared on new operations
- Confirmation prompt for batch undo (>10 operations)
- Dry-run mode to preview undo effects
- Maximum undo stack size: configurable, default 1000

### Integration Points
This task integrates with:
- **Task 53**: Operation history tracking (required foundation)
- All file operation services
- CLI framework for undo/redo/history commands
- Configuration system for trash retention and stack limits

### Undo Logic by Operation Type

**Move Operation**:
- Original: `source_path → destination_path`
- Undo: `destination_path → source_path`
- Validation: destination exists, source location available

**Rename Operation**:
- Original: `old_name → new_name`
- Undo: `new_name → old_name`
- Validation: new_name exists, old_name available

**Delete Operation**:
- Original: file deleted (moved to trash)
- Undo: restore from trash
- Validation: file in trash, destination available, hash matches

**Copy Operation**:
- Original: created copy at destination
- Undo: delete the copy
- Validation: copy exists, hash matches original

### Test Coverage Requirements
- Undo/redo for each operation type
- Transaction rollback (atomic)
- Validation scenarios (all pass/fail cases)
- Conflict detection and handling
- File integrity checks
- Edge cases:
  - File modified after operation
  - Missing files
  - Permission errors
  - Disk space errors
  - Parent directory renamed
  - External modifications
  - Partial transaction rollback
- Performance with large operations
- Concurrent access safety
- Redo stack management

### CLI Interface Design
```bash
# Undo last operation
file-organizer undo

# Undo specific operation
file-organizer undo --operation-id 12345

# Undo transaction
file-organizer undo --transaction-id abc-123

# Redo last undone operation
file-organizer redo

# View history
file-organizer history --limit 20

# View history with filter
file-organizer history --type move --since "2026-01-01"

# Search history
file-organizer history --search "/path/to/file"

# View transaction details
file-organizer history --transaction abc-123
```
