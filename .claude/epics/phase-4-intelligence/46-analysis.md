---
issue: 46
title: Implement hash-based exact duplicate detection
analyzed: 2026-01-21T06:02:22Z
estimated_hours: 16
parallelization_factor: 2.5
---

# Parallel Work Analysis: Issue #46

## Overview
Implement a hash-based duplicate file detection system with MD5/SHA256 support, duplicate index, user confirmation interface, and safe backup mode. The system needs to efficiently handle large file sets and provide a user-friendly CLI experience.

## Parallel Streams

### Stream A: Core Hash & Index Implementation
**Scope**: Backend logic for hash computation and duplicate tracking
**Files**:
- `file_organizer/services/deduplication/__init__.py`
- `file_organizer/services/deduplication/hasher.py`
- `file_organizer/services/deduplication/index.py`
- `file_organizer/services/deduplication/detector.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 7 hours
**Dependencies**: none

**Deliverables**:
- FileHasher class with MD5/SHA256 support
- Chunked reading for large files
- DuplicateIndex for hash-to-files mapping
- DuplicateDetector orchestrator
- File size pre-filtering optimization
- Batch hash computation

### Stream B: Backup & Safety System
**Scope**: Safe mode implementation with backup management
**Files**:
- `file_organizer/services/deduplication/backup.py`
- Backup directory structure and manifest
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4 hours
**Dependencies**: none

**Deliverables**:
- BackupManager class
- Backup directory creation (.file_organizer_backups/)
- Backup manifest with timestamps
- Restore functionality
- Cleanup command for old backups

### Stream C: CLI & User Interface
**Scope**: User-facing command-line interface and interaction
**Files**:
- `file_organizer/cli/dedupe.py` (new CLI subcommand)
- Interactive prompt implementation
**Agent Type**: fullstack-specialist
**Can Start**: immediately
**Estimated Hours**: 3 hours
**Dependencies**: none

**Deliverables**:
- CLI subcommand for deduplication
- Interactive confirmation prompts
- Duplicate group display with metadata
- Selection strategies (keep oldest/newest/largest)
- Dry-run mode flag
- Progress indicators (using tqdm)

### Stream D: Integration & Testing
**Scope**: Bring all components together, comprehensive testing
**Files**:
- `tests/services/deduplication/test_hasher.py`
- `tests/services/deduplication/test_index.py`
- `tests/services/deduplication/test_detector.py`
- `tests/services/deduplication/test_backup.py`
- `tests/integration/test_deduplication_e2e.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A, B, and C complete
**Estimated Hours**: 2 hours
**Dependencies**: Streams A, B, C

**Deliverables**:
- Unit tests for all classes (>90% coverage)
- Integration tests for end-to-end flow
- Performance tests (10,000+ files)
- Edge case testing
- Documentation with usage examples

## Coordination Points

### Shared Files
None - streams work on completely independent file sets

### Interface Contracts
To enable parallel work, define these interfaces upfront:

**FileHasher Interface**:
```python
def compute_hash(file_path: Path, algorithm: str = "sha256") -> str
def compute_batch(file_paths: List[Path]) -> Dict[Path, str]
```

**DuplicateIndex Interface**:
```python
def add_file(file_path: Path, file_hash: str, metadata: dict) -> None
def get_duplicates() -> Dict[str, List[Path]]
def get_statistics() -> dict
```

**BackupManager Interface**:
```python
def create_backup(file_path: Path) -> Path
def restore_backup(backup_path: Path) -> None
def cleanup_old_backups(max_age_days: int) -> None
```

**DuplicateDetector Interface**:
```python
def scan_directory(directory: Path) -> DuplicateIndex
def remove_duplicates(index: DuplicateIndex, strategy: str) -> None
```

### Sequential Requirements
1. Streams A, B, C can all run in parallel
2. Stream D (testing/integration) must wait for A, B, C to complete
3. Interface contracts must be agreed upon before starting

## Conflict Risk Assessment
**Low Risk** - Streams work on completely different directories with no file overlap:
- Stream A: `file_organizer/services/deduplication/{hasher,index,detector}.py`
- Stream B: `file_organizer/services/deduplication/backup.py`
- Stream C: `file_organizer/cli/dedupe.py`
- Stream D: `tests/**/*`

No shared configuration files or types need modification.

## Parallelization Strategy

**Recommended Approach**: parallel with final integration

**Execution Plan**:
1. **Pre-work** (0.5 hours): Define and document interface contracts
2. **Phase 1** (parallel, 7 hours): Launch Streams A, B, C simultaneously
3. **Phase 2** (sequential, 2 hours): Stream D integrates and tests

**Timeline**:
- Stream A: 7 hours
- Stream B: 4 hours (completes early)
- Stream C: 3 hours (completes early)
- Stream D: 2 hours (after Phase 1)

Total wall time: ~9.5 hours (including coordination)

## Expected Timeline

**With parallel execution**:
- Wall time: ~9.5 hours (pre-work + max(A,B,C) + D)
- Total work: 16 hours
- Efficiency gain: 41% time savings

**Without parallel execution**:
- Wall time: 16 hours (sequential completion)

**Parallelization factor**: 2.5x effective speedup (16h / 6.4h actual)

## Agent Assignment Recommendations

- **Stream A**: Senior backend developer with Python expertise
- **Stream B**: Backend developer familiar with file system operations
- **Stream C**: Fullstack developer with CLI/UX experience
- **Stream D**: QA engineer or full-stack developer for testing

## Notes

### Success Factors
- Clear interface contracts prevent integration issues
- Streams A, B, C are completely independent - no coordination needed during development
- Stream D benefits from having all components ready for comprehensive testing

### Risks & Mitigation
- **Risk**: Interface mismatch between components
  - **Mitigation**: Document interfaces before starting, include in acceptance criteria
- **Risk**: Performance issues discovered during testing
  - **Mitigation**: Stream A includes performance optimization from the start (chunked reading, batch processing)

### Performance Targets
- Hash computation: >100 files/second for small files (<1MB)
- Large file handling: No memory issues with files >1GB
- Index lookup: O(1) for duplicate detection
- UI responsiveness: Progress updates every 100 files

### Integration Points
This task integrates with:
- Existing `FileOrganizer` service (for directory scanning)
- CLI framework (for new dedupe subcommand)
- Configuration system (for algorithm selection, backup settings)

All integration points are handled in Stream D, keeping Streams A-C focused on implementation.
