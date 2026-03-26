# Complexity Analysis: Remaining 9 C901-Exempted Files

**Analysis Date:** 2026-03-24
**Scope:** Comprehensive analysis of 9 remaining files with C901 complexity exemptions
**Total Lines Analyzed:** 4,143 lines across 9 files

---

## Executive Summary

This analysis covers the 9 remaining files with C901 complexity exemptions after the initial analysis of `cli/dedupe.py`, `cli/undo_redo.py`, and `web/files_routes.py`. These files range from 224 to 536 lines and exhibit varying levels of complexity.

### Complexity Distribution

| Priority | File | Lines | Complexity Level | Risk |
|----------|------|-------|------------------|------|
| **HIGH** | `methodologies/para/ai/suggestion_engine.py` | 536 | HIGH | Medium |
| **HIGH** | `services/intelligence/profile_merger.py` | 491 | HIGH | Medium |
| **HIGH** | `services/intelligence/profile_importer.py` | 460 | HIGH | Medium |
| **MEDIUM** | `api/config.py` | 434 | MEDIUM | Low |
| **MEDIUM** | `cli/utilities.py` | 402 | MEDIUM | Low |
| **MEDIUM** | `services/intelligence/profile_migrator.py` | 393 | MEDIUM | Low |
| **MEDIUM** | `parallel/processor.py` | 381 | MEDIUM | Low |
| **LOW** | `updater/installer.py` | 350 | LOW | Low |
| **LOW** | `services/copilot/intent_parser.py` | 224 | LOW | Low |

### Key Findings

1. **Intelligence Module (3 files, 1,344 lines)** - Highest complexity concentration
   - Profile import/merge/migration logic with extensive validation
   - Recommendation: Extract into sub-modules with clear separation

2. **API Config (434 lines)** - Long environment variable parsing
   - One large function with 100+ environment variable checks
   - Recommendation: Extract environment parsers by domain

3. **CLI Utilities (402 lines)** - Dual-mode search complexity
   - Semantic search vs traditional search in single function
   - Recommendation: Split into separate command variants

4. **Low Priority Files (955 lines)** - Already well-structured
   - Moderate complexity, mostly acceptable
   - Recommendation: Minor simplifications only

---

## Detailed File Analysis

### 1. methodologies/para/ai/suggestion_engine.py ⚠️ HIGH PRIORITY

**Lines:** 536
**Complexity Level:** HIGH
**Risk:** Medium

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `suggest()` | 82 | **HIGH** | Multiple feature extraction and scoring steps |
| `_compute_feature_scores()` | 76 | **HIGH** | Nested conditionals, multiple scoring strategies |
| `_build_reasoning()` | 45 | **MEDIUM** | Multiple conditional branches |
| `_combine_scores()` | 10 | LOW | Simple weighted average |
| `suggest_batch()` | 17 | LOW | Simple iteration |

#### Complexity Issues

1. **Feature Score Computation** (`_compute_feature_scores`, lines 321-411)
   - **91 lines** of nested if-statements
   - Mixes text, metadata, and structural feature scoring
   - Multiple scoring strategies in one function
   - Hard-coded magic numbers (0.4, 0.15, 0.25, etc.)

2. **Reasoning Builder** (`_build_reasoning`, lines 442-506)
   - **65 lines** of conditional logic
   - Collects reasoning from multiple sources
   - Mixes different signal types

3. **Main Suggest Method** (`suggest`, lines 133-231)
   - **99 lines** orchestrating multiple steps
   - Could be decomposed into pipeline stages

#### Code Smells

- **God Method**: `_compute_feature_scores` does too much
- **Magic Numbers**: Hard-coded thresholds (0.4, 0.15, 0.05, etc.)
- **Mixed Concerns**: Scoring and reasoning in same class
- **Poor Testability**: Hard to unit test individual scoring strategies

#### Refactoring Strategy

**Phase 1: Extract Scoring Strategies** (RECOMMENDED)
```python
# Current: One massive function
def _compute_feature_scores(self, text_features, metadata, structural):
    scores = {}
    # 91 lines of nested ifs
    return scores

# Proposed: Strategy pattern
class FeatureScorer(ABC):
    @abstractmethod
    def score(self, features) -> dict[PARACategory, float]: ...

class TextFeatureScorer(FeatureScorer):
    def score(self, text_features):
        # Text-based scoring only

class MetadataScorer(FeatureScorer):
    def score(self, metadata):
        # Metadata-based scoring only

class StructuralScorer(FeatureScorer):
    def score(self, structural):
        # Path structure scoring only
```

**Phase 2: Extract Configuration**
- Move magic numbers to `PARAConfig`
- Make thresholds configurable
- Document scoring weights

**Phase 3: Extract Reasoning Builder**
- Move to separate `ReasoningBuilder` class
- Unit test each reasoning source independently

**Estimated Effort:** 6-8 hours
**Impact:** High - Improves testability and maintainability

---

### 2. services/intelligence/profile_merger.py ⚠️ HIGH PRIORITY

**Lines:** 491
**Complexity Level:** HIGH
**Risk:** Medium

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `merge_profiles()` | 70 | **HIGH** | Multiple merge operations, error handling |
| `_merge_preferences()` | 62 | **HIGH** | Nested loops, complex data structures |
| `resolve_conflicts()` | 54 | **HIGH** | Multiple strategy branches |
| `preserve_high_confidence()` | 48 | **MEDIUM** | Nested conditionals for preference types |
| `get_merge_conflicts()` | 53 | **MEDIUM** | Similar structure to `_merge_preferences` |

#### Complexity Issues

1. **Preference Merging** (`_merge_preferences`, lines 142-204)
   - **63 lines** with nested loops
   - Iterates through profiles × preference keys
   - Builds complex nested dictionaries
   - Duplicated logic for global vs directory-specific

2. **Conflict Resolution** (`resolve_conflicts`, lines 285-339)
   - **55 lines** with 5 strategy branches
   - Each strategy has different logic
   - Strategy pattern not used despite clear need

3. **High Confidence Preservation** (`preserve_high_confidence`, lines 341-393)
   - **53 lines** checking multiple preference types
   - Repetitive code for global/directory/patterns

#### Code Smells

- **Duplicated Logic**: `_merge_preferences`, `_merge_learned_patterns`, `_merge_confidence_data` have similar structure
- **Strategy Pattern Missing**: `resolve_conflicts` uses if-elif instead of polymorphism
- **Deep Nesting**: 3-4 levels of nesting in merge functions
- **Type Checking**: Multiple `if key in dict` checks

#### Refactoring Strategy

**Phase 1: Extract Merge Strategies** (RECOMMENDED)
```python
# Current: Multiple similar merge methods
def _merge_preferences(self, profiles, strategy): ...
def _merge_learned_patterns(self, profiles, strategy): ...
def _merge_confidence_data(self, profiles, strategy): ...

# Proposed: Generic merge with type-specific handlers
class DataMerger(ABC):
    @abstractmethod
    def extract_data(self, profile: Profile) -> dict: ...

    @abstractmethod
    def merge_values(self, values: list, strategy: MergeStrategy) -> Any: ...

class PreferenceMerger(DataMerger): ...
class PatternMerger(DataMerger): ...
class ConfidenceMerger(DataMerger): ...
```

**Phase 2: Strategy Pattern for Conflict Resolution**
```python
class ConflictResolver(ABC):
    @abstractmethod
    def resolve(self, values: list[dict]) -> Any: ...

class RecentResolver(ConflictResolver): ...
class ConfidentResolver(ConflictResolver): ...
class FrequentResolver(ConflictResolver): ...

RESOLVERS = {
    MergeStrategy.RECENT: RecentResolver(),
    MergeStrategy.CONFIDENT: ConfidentResolver(),
    # ...
}
```

**Phase 3: Simplify Preserve Logic**
- Extract preference type checking to helper
- Use lookup table instead of if-elif chains

**Estimated Effort:** 8-10 hours
**Impact:** High - Removes 150+ lines of duplication

---

### 3. services/intelligence/profile_importer.py ⚠️ HIGH PRIORITY

**Lines:** 460
**Complexity Level:** HIGH
**Risk:** Medium

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `validate_import_file()` | 91 | **CRITICAL** | Excessive validation checks |
| `import_profile()` | 93 | **CRITICAL** | Long transaction with multiple steps |
| `import_selective()` | 42 | **MEDIUM** | Data filtering and transformation |
| `preview_import()` | 60 | **MEDIUM** | Builds preview dictionary |

#### Complexity Issues

1. **Validation Function** (`validate_import_file`, lines 68-167)
   - **100 lines** of validation logic
   - File checks, JSON parsing, field validation, version checks
   - Builds multiple lists (errors, warnings)
   - Mixes I/O with validation logic

2. **Import Function** (`import_profile`, lines 230-321)
   - **92 lines** orchestrating import
   - Validation → Backup → Profile creation → Data update
   - Branching for full vs selective import
   - Complex error recovery

3. **Selective Import** (`_import_selective_profile`, lines 323-379)
   - **57 lines** merging selective data
   - Multiple dictionary updates with null checks
   - Repetitive update patterns

#### Code Smells

- **God Function**: `validate_import_file` does too much
- **Long Method**: Both validation and import exceed 90 lines
- **Primitive Obsession**: Returning tuples/dicts instead of objects
- **Error Handling**: Try-except wrapping entire functions
- **I/O Mixed with Logic**: File reading mixed with validation

#### Refactoring Strategy

**Phase 1: Extract Validators** (RECOMMENDED)
```python
# Current: One massive validation function
def validate_import_file(self, path) -> ValidationResult:
    # 100 lines of checks

# Proposed: Validator chain
class ImportValidator:
    def __init__(self):
        self.validators = [
            FileExistenceValidator(),
            FileSizeValidator(),
            JSONFormatValidator(),
            SchemaValidator(),
            VersionValidator(),
            TimestampValidator(),
        ]

    def validate(self, path: Path) -> ValidationResult:
        result = ValidationResult(valid=True, errors=[], warnings=[])
        for validator in self.validators:
            validator.validate(path, result)
        return result
```

**Phase 2: Extract Import Steps**
```python
# Current: One long import function
def import_profile(self, path, new_name):
    # validate
    # backup
    # create/update
    # return

# Proposed: Pipeline pattern
class ImportPipeline:
    def __init__(self, steps: list[ImportStep]):
        self.steps = steps

    def execute(self, path, new_name) -> Profile | None:
        context = ImportContext(path, new_name)
        for step in self.steps:
            if not step.execute(context):
                return None
        return context.profile
```

**Phase 3: Simplify Selective Import**
- Extract dictionary merge logic to helper
- Use dictionary comprehensions where possible

**Estimated Effort:** 8-10 hours
**Impact:** High - Validation becomes unit testable

---

### 4. api/config.py 🔶 MEDIUM PRIORITY

**Lines:** 434
**Complexity Level:** MEDIUM
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `load_settings()` | 223 | **CRITICAL** | Massive environment variable parsing |
| `_parse_list()` | 13 | LOW | Simple parsing |
| `_load_yaml()` | 12 | LOW | Simple file loading |

#### Complexity Issues

1. **Settings Loader** (`load_settings`, lines 119-341)
   - **223 lines** of environment variable checks
   - ~60 individual environment variables
   - Repetitive if-env-in-check → parse → assign pattern
   - Type conversion (int, bool, list) scattered throughout
   - No grouping by domain

#### Code Smells

- **Long Method**: 223 lines is excessive
- **Repetition**: Same if-env-check pattern repeated 60 times
- **Mixed Concerns**: YAML loading, env parsing, type conversion all in one place
- **Hard to Extend**: Adding new config requires modifying massive function

#### Refactoring Strategy

**Phase 1: Extract Environment Parsers by Domain** (RECOMMENDED)
```python
# Current: One massive function
def load_settings() -> ApiSettings:
    data = {}
    if "FO_API_APP_NAME" in env: data["app_name"] = env["FO_API_APP_NAME"]
    if "FO_API_PORT" in env: data["port"] = int(env["FO_API_PORT"])
    # ... 60 more ...
    return ApiSettings(**data)

# Proposed: Domain-specific parsers
class EnvParser:
    @staticmethod
    def parse_basic(env: dict, data: dict):
        """Parse basic app settings."""
        if "FO_API_APP_NAME" in env: data["app_name"] = env["FO_API_APP_NAME"]
        if "FO_API_ENVIRONMENT" in env: data["environment"] = env["FO_API_ENVIRONMENT"]
        # ... 5-10 related settings ...

    @staticmethod
    def parse_auth(env: dict, data: dict):
        """Parse auth settings."""
        # All auth-related env vars

    @staticmethod
    def parse_database(env: dict, data: dict):
        """Parse database settings."""
        # All database-related env vars

    # ... more domain parsers ...

def load_settings() -> ApiSettings:
    data = _load_yaml_if_present()
    env = os.environ

    EnvParser.parse_basic(env, data)
    EnvParser.parse_auth(env, data)
    EnvParser.parse_database(env, data)
    EnvParser.parse_cors(env, data)
    EnvParser.parse_security(env, data)

    return ApiSettings(**data)
```

**Phase 2: Extract Type Converters**
```python
class TypeConverter:
    @staticmethod
    def to_int(value: str, field: str) -> int | None:
        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid {field} value: {value}")
            return None

    @staticmethod
    def to_bool(value: str) -> bool:
        return value.lower() in ("1", "true", "yes")
```

**Estimated Effort:** 4-6 hours
**Impact:** Medium - Easier to add new config options

---

### 5. cli/utilities.py 🔶 MEDIUM PRIORITY

**Lines:** 402
**Complexity Level:** MEDIUM
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `search()` | 214 | **CRITICAL** | Dual-mode search (semantic + traditional) |
| `analyze()` | 90 | **MEDIUM** | File analysis with error handling |

#### Complexity Issues

1. **Search Function** (`search`, lines 18-312)
   - **295 lines** with two completely different code paths
   - Lines 137-224: Semantic search mode (87 lines)
   - Lines 226-312: Traditional glob/keyword search (86 lines)
   - Shared type filtering logic (duplicated)
   - Shared output formatting logic (duplicated)

2. **Analyze Function** (`analyze`, lines 314-403)
   - **90 lines** orchestrating analysis
   - Binary detection, content reading, model init, analysis, output
   - Acceptable complexity for CLI command

#### Code Smells

- **Feature Envy**: Semantic search logic should be in HybridRetriever
- **Duplicated Logic**: Type filtering and output formatting duplicated
- **Long Method**: 295 lines is excessive
- **Flag Argument**: `semantic` flag causes branching

#### Refactoring Strategy

**Phase 1: Split Search Modes** (RECOMMENDED)
```python
# Current: One function with --semantic flag
def search(query, directory, semantic=False, ...):
    if semantic:
        # 87 lines of semantic search
    else:
        # 86 lines of traditional search

# Proposed: Separate commands
def search(query, directory, type_filter, limit, recursive, json_out):
    """Traditional glob/keyword search."""
    # Only traditional search logic

def search_semantic(query, directory, type_filter, limit, recursive, json_out):
    """Semantic search using embeddings."""
    # Only semantic search logic

# Or even better: Extract to classes
class TraditionalSearch:
    def search(self, query, options) -> list[Path]: ...

class SemanticSearch:
    def search(self, query, options) -> list[tuple[Path, float]]: ...
```

**Phase 2: Extract Common Logic**
```python
class SearchFormatter:
    @staticmethod
    def format_results(results, as_json=False) -> str:
        """Format search results for display."""

class TypeFilter:
    def __init__(self, type_name: str):
        self.extensions = TYPE_EXTENSIONS[type_name]

    def matches(self, path: Path) -> bool:
        """Check if file matches type filter."""
```

**Estimated Effort:** 4-5 hours
**Impact:** Medium - Better separation of concerns

---

### 6. services/intelligence/profile_migrator.py 🔶 MEDIUM PRIORITY

**Lines:** 393
**Complexity Level:** MEDIUM
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `migrate_version()` | 105 | **HIGH** | Complex migration orchestration |
| `rollback_migration()` | 40 | LOW | Simple rollback logic |
| `validate_migration()` | 37 | LOW | Validation checks |
| `list_backups()` | 21 | LOW | File listing |

#### Complexity Issues

1. **Version Migration** (`migrate_version`, lines 54-157)
   - **104 lines** orchestrating migration
   - Validation → Backup → Find path → Execute steps → Save
   - Multiple error exit points
   - Good error recovery with rollback

2. **Migration Path Logic** (`_find_migration_path`, lines 159-181)
   - Currently simple (only v1.0 exists)
   - Comments suggest future graph traversal complexity
   - Placeholder for future complexity

#### Code Smells

- **Long Method**: 104 lines for migration orchestration
- **Future Complexity**: Comments indicate planned complexity growth
- **Error Handling**: Multiple early returns

#### Refactoring Strategy

**Phase 1: Extract Migration Steps** (OPTIONAL)
```python
# Current: Long orchestration function
def migrate_version(self, profile_name, target, backup=True):
    # validate
    # backup
    # find path
    # execute
    # validate
    # save

# Proposed: Step pattern (if adding more versions)
class MigrationStep:
    def execute(self, profile: Profile) -> Profile: ...
    def rollback(self): ...

class MigrationPipeline:
    def __init__(self, steps: list[MigrationStep]):
        self.steps = steps

    def execute(self, profile: Profile) -> Profile:
        for step in self.steps:
            profile = step.execute(profile)
        return profile
```

**Recommendation:** Wait until v2.0 migration is needed
**Estimated Effort:** 2-3 hours (if/when needed)
**Impact:** Low - Current code is acceptable

---

### 7. parallel/processor.py 🔶 MEDIUM PRIORITY

**Lines:** 381
**Complexity Level:** MEDIUM
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `process_batch_iter()` | 137 | **HIGH** | Complex executor and backpressure management |
| `process_batch()` | 45 | MEDIUM | Retry loop orchestration |
| `_run_batch()` | 75 | MEDIUM | Future submission and timeout handling |

#### Complexity Issues

1. **Iterator Processing** (`process_batch_iter`, lines 96-232)
   - **137 lines** managing concurrent futures
   - Backpressure control with prefetch depth
   - Timeout handling per file
   - Progress callback integration
   - Complex edge case handling (prefetch_depth=0)

2. **Batch Runner** (`_run_batch`, lines 234-308)
   - **75 lines** submitting and collecting futures
   - Timeout management
   - Cleanup of futures
   - Two different execution modes

#### Code Smells

- **Complex State Management**: Multiple dictionaries tracking futures
- **Special Cases**: prefetch_depth=0 has different code path
- **Callback Hell**: Progress callbacks make flow hard to follow
- **Resource Management**: Manual future cleanup

#### Refactoring Strategy

**Phase 1: Extract Backpressure Manager** (OPTIONAL)
```python
# Current: Inline backpressure logic
if prefetch_depth == 0:
    limit = 1
else:
    limit = max_workers * max(1, prefetch_depth)

# Proposed: Dedicated class
class BackpressureManager:
    def __init__(self, max_workers: int, prefetch_depth: int):
        self.limit = self._compute_limit(max_workers, prefetch_depth)

    def can_submit(self, pending_count: int) -> bool:
        return pending_count < self.limit
```

**Phase 2: Extract Timeout Handler**
```python
class TimeoutHandler:
    def __init__(self, timeout_ms: int):
        self.timeout = timeout_ms / 1000

    def wait_with_timeout(self, futures: set) -> tuple[set, set]:
        """Wait for futures with timeout, return (done, not_done)."""
```

**Recommendation:** Current code works well; refactor only if adding features
**Estimated Effort:** 3-4 hours
**Impact:** Low - Code is acceptable

---

### 8. updater/installer.py ✅ LOW PRIORITY

**Lines:** 350
**Complexity Level:** LOW
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `select_asset()` | 60 | **MEDIUM** | Platform and architecture matching with scoring |
| `download_asset()` | 43 | LOW | Straightforward download |
| `install()` | 40 | LOW | Simple file operations |
| `find_checksum()` | 17 | LOW | Pattern matching |

#### Complexity Issues

1. **Asset Selection** (`select_asset`, lines 198-264)
   - **67 lines** with platform detection and scoring
   - Multiple if-statements for platform/arch matching
   - Score-based ranking system
   - Well-commented and clear logic

#### Code Smells

- **Magic Numbers**: Score values (3, -5, 5, etc.) not documented
- **Platform-Specific**: Multiple platform checks

#### Refactoring Strategy

**Recommendation:** No refactoring needed
- Code is clear and well-structured
- Complexity is inherent to the problem (multi-platform support)
- Consider extracting score constants if adding more platforms

**Estimated Effort:** N/A
**Impact:** Very Low

---

### 9. services/copilot/intent_parser.py ✅ LOW PRIORITY

**Lines:** 224
**Complexity Level:** LOW
**Risk:** Low

#### Complexity Metrics

| Function | Lines | Complexity | Issues |
|----------|-------|------------|--------|
| `parse()` | 44 | LOW | Simple pattern matching loop |
| `_extract_parameters()` | 56 | MEDIUM | Multiple extraction strategies |

#### Complexity Issues

1. **Parameter Extraction** (`_extract_parameters`, lines 116-171)
   - **56 lines** extracting intent-specific parameters
   - Pattern matching for quoted strings, paths
   - Intent-specific extraction (if-elif chains)
   - Clear and readable

#### Code Smells

- **Intent-Specific Logic**: if-elif for different intent types
- Could benefit from intent-specific extractors

#### Refactoring Strategy

**Recommendation:** No refactoring needed
- Code is already well-structured
- Pattern matching is appropriate for the use case
- Small enough to maintain easily

**Estimated Effort:** N/A
**Impact:** Very Low

---

## Summary and Recommendations

### Refactoring Priorities

#### **MUST DO** (Priority 1)
These files have critical complexity issues that should be addressed:

1. **methodologies/para/ai/suggestion_engine.py** (536 lines)
   - Extract scoring strategies
   - Move magic numbers to config
   - Estimated: 6-8 hours

2. **services/intelligence/profile_merger.py** (491 lines)
   - Extract merge strategies
   - Implement strategy pattern for conflict resolution
   - Estimated: 8-10 hours

3. **services/intelligence/profile_importer.py** (460 lines)
   - Extract validator chain
   - Implement import pipeline
   - Estimated: 8-10 hours

**Total High Priority Effort:** 22-28 hours

---

#### **SHOULD DO** (Priority 2)
These files would benefit from refactoring but are not critical:

4. **api/config.py** (434 lines)
   - Extract environment parsers by domain
   - Estimated: 4-6 hours

5. **cli/utilities.py** (402 lines)
   - Split semantic and traditional search
   - Extract common formatting
   - Estimated: 4-5 hours

**Total Medium Priority Effort:** 8-11 hours

---

#### **NICE TO HAVE** (Priority 3)
These files are acceptable but could be improved:

6. **services/intelligence/profile_migrator.py** (393 lines)
   - Wait until v2.0 migration needed
   - Estimated: 2-3 hours (future)

7. **parallel/processor.py** (381 lines)
   - Extract backpressure manager (optional)
   - Estimated: 3-4 hours (optional)

---

#### **NO ACTION NEEDED** (Priority 4)
These files are well-structured:

8. **updater/installer.py** (350 lines) ✅
9. **services/copilot/intent_parser.py** (224 lines) ✅

---

### Overall Recommendations

1. **Start with Intelligence Module** (files 2-3)
   - High impact (1,344 lines total)
   - Clear refactoring patterns
   - Medium risk (good test coverage expected)

2. **Then PARA Suggestion Engine** (file 1)
   - High complexity
   - Scoring logic is hard to test
   - Extract strategies for testability

3. **Config and Utilities** (files 4-5)
   - Lower priority
   - Easier refactoring
   - Good for learning patterns

4. **Leave Low Priority Files** (files 6-9)
   - Acceptable complexity
   - Refactor only if touching for other reasons

### Acceptance Criteria

Refactoring is successful when:

- [ ] All functions under 75 lines
- [ ] No function has McCabe complexity > 15
- [ ] Extractable strategies extracted to classes
- [ ] Magic numbers moved to configuration
- [ ] All tests still pass
- [ ] New unit tests for extracted components
- [ ] C901 exemptions removed for refactored files

### Testing Strategy

For each refactored file:

1. **Capture Baseline Behavior**
   - Create integration tests before refactoring
   - Document expected inputs/outputs

2. **Add Unit Tests for Extracted Components**
   - Test each strategy independently
   - Test validators independently
   - Achieve >90% coverage for new modules

3. **Regression Testing**
   - Verify integration tests still pass
   - Compare outputs before/after
   - Performance benchmarks

### Risk Mitigation

- **High-Risk Files**: Profile merger/importer (complex logic)
  - Comprehensive test coverage first
  - Incremental refactoring
  - Feature flags for new code paths

- **Medium-Risk Files**: Config, utilities (simple logic)
  - Direct refactoring acceptable
  - Basic test coverage

- **Low-Risk Files**: No changes needed
  - Skip refactoring

---

## Conclusion

Of the 9 remaining C901-exempted files analyzed:

- **3 files (HIGH priority)** require significant refactoring: 1,487 lines, 22-28 hours effort
- **2 files (MEDIUM priority)** would benefit from refactoring: 836 lines, 8-11 hours effort
- **2 files (LOW priority)** are acceptable as-is but could be improved: 774 lines, 5-7 hours effort
- **2 files (NO ACTION)** are well-structured: 574 lines, no action needed

**Total Refactoring Effort:** 35-46 hours for all priority 1-3 files
**Recommended Focus:** Intelligence module (profile_importer, profile_merger) + PARA suggestion engine
**Expected Outcome:** Removal of C901 exemptions for 5-7 of 9 files, reducing complexity by ~40%

The intelligence module files show the most consistent pattern of complexity issues and would benefit most from refactoring. The PARA suggestion engine has the highest single-file complexity and should be prioritized for testability improvements.
