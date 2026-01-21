---
issue: 50
title: Build preference tracking system
analyzed: 2026-01-21T06:20:56Z
estimated_hours: 16
parallelization_factor: 2.7
---

# Parallel Work Analysis: Issue #50

## Overview
Build a comprehensive preference tracking system that captures user corrections and stores preferences in JSON format. The system implements per-directory learning with inheritance, conflict resolution for contradictory preferences, and thread-safe access. This is a foundational component for the intelligence system that Task #49 (pattern learning) will build upon.

## Parallel Streams

### Stream A: Core Preference Tracking
**Scope**: Main preference tracking engine and correction capture
**Files**:
- `file_organizer/services/intelligence/preference_tracker.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 6 hours
**Dependencies**: none

**Deliverables**:
- PreferenceTracker class
- Correction tracking (file moves, renames, category overrides)
- Preference data structures
- Real-time preference updates
- In-memory preference management
- Thread-safe operations with locks
- Preference metadata (timestamps, confidence, frequency)

### Stream B: Preference Storage & Persistence
**Scope**: JSON-based persistence with atomic writes
**Files**:
- `file_organizer/services/intelligence/preference_store.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 5 hours
**Dependencies**: none

**Deliverables**:
- PreferenceStore class
- JSON schema definition (v1.0)
- Serialization/deserialization logic
- Atomic file writes (safe persistence)
- Schema validation and versioning
- Preference loading with error recovery
- Backup/restore functionality
- Migration support for schema updates

### Stream C: Directory Hierarchy & Conflict Resolution
**Scope**: Per-directory preferences with inheritance and conflict handling
**Files**:
- `file_organizer/services/intelligence/directory_prefs.py`
- `file_organizer/services/intelligence/conflict_resolver.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 3 hours
**Dependencies**: none

**Deliverables**:
- Directory-level preference scoping
- Parent directory inheritance
- Override capabilities for subdirectories
- ConflictResolver class
- Recency-weighted conflict resolution
- Frequency-based prioritization
- Deterministic resolution algorithm
- Confidence scoring for ambiguous cases

### Stream D: Integration & Testing
**Scope**: Module integration, comprehensive testing, and CLI hooks
**Files**:
- `file_organizer/services/intelligence/__init__.py`
- `tests/services/intelligence/test_preference_tracker.py`
- `tests/services/intelligence/test_preference_store.py`
- `tests/services/intelligence/test_directory_prefs.py`
- `tests/services/intelligence/test_conflict_resolver.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A, B, and C complete
**Estimated Hours**: 2 hours
**Dependencies**: Streams A, B, C

**Deliverables**:
- Module exports in __init__.py
- Unit tests for all classes
- JSON schema validation tests
- Conflict resolution scenario tests
- Directory inheritance tests
- Concurrent access tests
- Performance benchmarks (lookup < 10ms)
- Integration with FileOrganizer service
- Documentation and examples

## Coordination Points

### Shared Files
Minimal - only module init:
- `file_organizer/services/intelligence/__init__.py` - Stream D updates after A, B, C complete

### Interface Contracts
Define these interfaces upfront:

**PreferenceTracker Interface**:
```python
def track_correction(source: Path, destination: Path, context: dict) -> None
def get_preference(file_path: Path, preference_type: str) -> Optional[dict]
def save_preferences() -> None
def load_preferences() -> None
def get_statistics() -> dict
```

**PreferenceStore Interface**:
```python
def add_preference(path: Path, preference_data: dict) -> None
def get_preference(path: Path, fallback_to_parent: bool = True) -> Optional[dict]
def resolve_conflicts(preference_list: List[dict]) -> dict
def update_confidence(path: Path, success: bool) -> None
def export_json(output_path: Path) -> None
def import_json(input_path: Path) -> None
```

**DirectoryPrefs Interface**:
```python
def get_preference_with_inheritance(path: Path) -> Optional[dict]
def set_preference(path: Path, pref: dict, override_parent: bool) -> None
def list_directory_preferences() -> List[Tuple[Path, dict]]
```

**ConflictResolver Interface**:
```python
def resolve(conflicting_preferences: List[dict]) -> dict
def weight_by_recency(preferences: List[dict]) -> List[float]
def weight_by_frequency(preferences: List[dict]) -> List[float]
def score_confidence(preference: dict) -> float
```

### Sequential Requirements
1. Streams A, B, and C can all run in parallel
2. Stream D requires A, B, C to complete for integration and testing

## Conflict Risk Assessment
**Low Risk** - Streams work on completely different files:
- Stream A: `preference_tracker.py` only
- Stream B: `preference_store.py` only
- Stream C: `directory_prefs.py`, `conflict_resolver.py` only
- Stream D: `__init__.py`, `tests/**/*`

No implementation file overlap between A, B, and C.

## Parallelization Strategy

**Recommended Approach**: parallel with final integration

**Execution Plan**:
1. **Phase 1** (parallel, 6 hours): Launch Streams A, B, C simultaneously
2. **Phase 2** (sequential, 2 hours): Stream D integrates and tests

**Timeline**:
- Stream A: 6 hours (longest)
- Stream B: 5 hours (completes early)
- Stream C: 3 hours (completes early)
- Stream D: 2 hours (after Phase 1)

Total wall time: ~8 hours

## Expected Timeline

**With parallel execution**:
- Wall time: ~8 hours (max(A,B,C) + D)
- Total work: 16 hours
- Efficiency gain: 50% time savings

**Without parallel execution**:
- Wall time: 16 hours (sequential)

**Parallelization factor**: 2.7x effective speedup (16h / 5.9h per developer)

## Agent Assignment Recommendations

- **Stream A**: Senior backend developer with system design experience
- **Stream B**: Backend developer familiar with JSON and file I/O
- **Stream C**: Backend developer with algorithmic thinking
- **Stream D**: QA engineer or fullstack developer for testing and integration

## Notes

### Success Factors
- Streams A, B, C are completely independent
- Clear interface contracts prevent integration issues
- This is a foundational component - design quality matters
- JSON format makes preferences human-readable for debugging

### Risks & Mitigation
- **Risk**: Concurrent access might cause race conditions
  - **Mitigation**: Stream A implements proper locking from the start
- **Risk**: Preference file corruption
  - **Mitigation**: Stream B uses atomic writes and backup files
- **Risk**: Conflict resolution might be non-deterministic
  - **Mitigation**: Stream C ensures deterministic algorithm with clear rules

### Performance Targets
- Preference lookup: <10ms for typical cases
- Save operation: <100ms with atomic writes
- Conflict resolution: <50ms per conflict
- Memory usage: <10MB for typical preference database

### Design Considerations
- JSON schema v1.0 should be extensible for future versions
- Preference data should not leak sensitive information
- Support for future ML model integration
- Consider multi-user support in design (even if not implemented now)
- Preferences should be portable across systems

### JSON Schema Structure
```json
{
  "version": "1.0",
  "user_id": "default",
  "global_preferences": {
    "folder_mappings": {},
    "naming_patterns": {},
    "category_overrides": {}
  },
  "directory_preferences": {
    "/absolute/path": {
      "folder_mappings": {},
      "naming_patterns": {},
      "category_overrides": {},
      "created": "2026-01-21T06:20:56Z",
      "updated": "2026-01-21T06:20:56Z",
      "confidence": 0.85,
      "correction_count": 15
    }
  }
}
```

### Integration Points
- FileOrganizer service (capture corrections)
- Task #49 will build pattern learning on top of this
- Future ML models will use this preference data
- CLI commands for viewing/editing preferences

### Test Data Requirements
Stream D should test:
- Single correction tracking
- Multiple corrections for same file type
- Conflicting preferences
- Directory inheritance scenarios
- Concurrent access patterns
- Large preference databases (1000+ entries)
- Corrupted JSON recovery
