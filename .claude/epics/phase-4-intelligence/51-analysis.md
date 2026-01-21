---
issue: 51
title: Add preference profile management
analyzed: 2026-01-21T06:26:33Z
estimated_hours: 16
parallelization_factor: 2.2
---

# Parallel Work Analysis: Issue #51

## Overview
Implement comprehensive preference profile management enabling users to export, import, manage multiple profiles, merge preferences, and use default templates. This enables sharing preferences across machines, maintaining different organizational styles, and quick environment setup.

## Parallel Streams

### Stream A: Core Profile Management
**Scope**: Backend logic for profile CRUD operations and activation
**Files**:
- `file_organizer/services/preferences/profile_manager.py`
- `file_organizer/services/preferences/models.py`
- `file_organizer/services/preferences/storage.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 5 hours
**Dependencies**: Tasks 49, 50 (preference tracking must exist)

**Deliverables**:
- ProfileManager class with CRUD operations
- create_profile(), activate_profile(), list_profiles()
- delete_profile(), get_active_profile()
- JSON-based profile storage with versioning
- Atomic profile switching
- Profile validation and sanitization

### Stream B: Import/Export & Migration
**Scope**: Profile serialization, import/export, and version migration
**Files**:
- `file_organizer/services/preferences/exporter.py`
- `file_organizer/services/preferences/importer.py`
- `file_organizer/services/preferences/migrator.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 5 hours
**Dependencies**: Tasks 49, 50

**Deliverables**:
- ProfileExporter with full/selective export
- ProfileImporter with validation and preview
- ProfileMigrator for version upgrades
- Backup/rollback functionality
- JSON validation and sanitization
- Compatibility checks

### Stream C: Profile Merging & Templates
**Scope**: Profile merge operations and default template system
**Files**:
- `file_organizer/services/preferences/merger.py`
- `file_organizer/services/preferences/templates.py`
- `file_organizer/services/preferences/templates/` (directory with 5 default templates)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4 hours
**Dependencies**: Tasks 49, 50

**Deliverables**:
- ProfileMerger with conflict resolution
- Merge strategies (recent, frequent, confident)
- TemplateManager for template operations
- 5 default templates (Work, Personal, Photography, Development, Academic)
- Template preview functionality
- Custom template creation from existing profiles

### Stream D: CLI Integration & Testing
**Scope**: CLI commands, integration, and comprehensive testing
**Files**:
- `file_organizer/cli/profile.py` (new CLI subcommand group)
- `tests/services/preferences/test_profile_manager.py`
- `tests/services/preferences/test_exporter.py`
- `tests/services/preferences/test_importer.py`
- `tests/services/preferences/test_merger.py`
- `tests/services/preferences/test_templates.py`
- `tests/integration/test_profile_management_e2e.py`
**Agent Type**: fullstack-specialist
**Can Start**: after Streams A, B, and C complete
**Estimated Hours**: 2 hours
**Dependencies**: Streams A, B, C

**Deliverables**:
- CLI commands for all profile operations
- Unit tests for all components (>90% coverage)
- Integration tests for end-to-end workflows
- Profile round-trip tests (export/import)
- Merge scenario tests
- Template validation tests
- Performance benchmarks (profile switch < 100ms)

## Coordination Points

### Shared Files
Minimal overlap:
- `file_organizer/services/preferences/__init__.py` - Stream D updates exports after A, B, C complete
- Profile templates directory - Stream C owns exclusively

### Interface Contracts
To enable parallel work, define these interfaces upfront:

**ProfileManager Interface**:
```python
def create_profile(name: str, description: str) -> Profile
def activate_profile(profile_name: str) -> bool
def list_profiles() -> List[Profile]
def delete_profile(profile_name: str) -> bool
def get_active_profile() -> Profile
```

**ProfileExporter Interface**:
```python
def export_profile(profile_name: str, file_path: Path) -> bool
def export_selective(profile_name: str, file_path: Path, preferences_list: List[str]) -> bool
def validate_export(file_path: Path) -> bool
```

**ProfileImporter Interface**:
```python
def import_profile(file_path: Path, new_name: str) -> Profile
def import_selective(file_path: Path, preferences_list: List[str]) -> Profile
def validate_import_file(file_path: Path) -> ValidationResult
def preview_import(file_path: Path) -> dict
```

**ProfileMerger Interface**:
```python
def merge_profiles(profile_list: List[str], merge_strategy: str) -> Profile
def resolve_conflicts(conflicting_prefs: dict) -> dict
def create_merged_profile(name: str, merged_data: dict) -> Profile
```

**TemplateManager Interface**:
```python
def list_templates() -> List[str]
def get_template(template_name: str) -> dict
def create_profile_from_template(template_name: str, profile_name: str) -> Profile
def preview_template(template_name: str) -> dict
```

**Profile Data Structure**:
```python
{
  "profile_name": str,
  "profile_version": str,
  "description": str,
  "created": str,  # ISO 8601
  "updated": str,  # ISO 8601
  "preferences": {
    "global": dict,
    "directory_specific": dict
  },
  "learned_patterns": dict,
  "confidence_data": dict
}
```

### Sequential Requirements
1. Streams A, B, C can all run in parallel
2. Stream D (CLI/testing) must wait for A, B, C to complete
3. Interface contracts and profile data structure must be agreed upon before starting

## Conflict Risk Assessment
**Low Risk** - Streams work on completely different files:
- Stream A: `profile_manager.py`, `models.py`, `storage.py`
- Stream B: `exporter.py`, `importer.py`, `migrator.py`
- Stream C: `merger.py`, `templates.py`, `templates/` directory
- Stream D: `cli/profile.py`, `tests/**/*`

No shared implementation files between A, B, and C.

## Parallelization Strategy

**Recommended Approach**: parallel with final integration

**Execution Plan**:
1. **Pre-work** (0.5 hours): Define and document interface contracts and profile data structure
2. **Phase 1** (parallel, 5 hours): Launch Streams A, B, C simultaneously
3. **Phase 2** (sequential, 2 hours): Stream D integrates and tests

**Timeline**:
- Stream A: 5 hours
- Stream B: 5 hours
- Stream C: 4 hours (completes early)
- Stream D: 2 hours (after Phase 1)

Total wall time: ~7.5 hours (including coordination)

## Expected Timeline

**With parallel execution**:
- Wall time: ~7.5 hours (pre-work + max(A,B,C) + D)
- Total work: 16 hours
- Efficiency gain: 53% time savings

**Without parallel execution**:
- Wall time: 16 hours (sequential completion)

**Parallelization factor**: 2.2x effective speedup (16h / 7.3h actual)

## Agent Assignment Recommendations

- **Stream A**: Senior backend developer with Python expertise
- **Stream B**: Backend developer familiar with serialization and data migration
- **Stream C**: Backend developer with template/configuration experience
- **Stream D**: QA engineer or full-stack developer for testing and CLI integration

## Notes

### Success Factors
- Clear interface contracts prevent integration issues
- Streams A, B, C are completely independent - no coordination needed during development
- Profile data structure agreed upon upfront enables parallel work
- Stream D benefits from having all components ready for comprehensive testing

### Risks & Mitigation
- **Risk**: Profile format incompatibility across versions
  - **Mitigation**: Stream B includes versioning and migration from day one
- **Risk**: Merge conflicts difficult to resolve automatically
  - **Mitigation**: Stream C implements multiple strategies and allows user intervention
- **Risk**: Profile switching not atomic (partial failures)
  - **Mitigation**: Stream A implements transaction-like switching with rollback

### Performance Targets
- Profile switch: <100ms
- Export/import: <500ms for typical profile
- Merge operation: <1 second
- Template application: <200ms
- Profile listing: <50ms

### Design Considerations
- Profile files are human-readable JSON (pretty-printed)
- Profile directory: `~/.file-organizer/profiles/`
- Active profile tracked in: `~/.file-organizer/active_profile.txt`
- Backup created before destructive operations
- Profile names must be unique and filesystem-safe
- All timestamps in ISO 8601 UTC format

### Integration Points
This task integrates with:
- Task 49: Build preference tracking system (required)
- Task 50: Implement pattern learning from user feedback (required)
- Existing configuration system
- CLI framework for new profile subcommand group

### Dependencies
**Hard Dependencies**: Tasks 49 and 50 must be complete - this task builds on their preference tracking infrastructure.
