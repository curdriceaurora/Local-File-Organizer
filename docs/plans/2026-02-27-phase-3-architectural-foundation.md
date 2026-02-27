# Phase 3: Architectural Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish clean architectural foundation for sustainable growth by standardizing paths, reducing startup latency, and implementing deferred migration/security features.

**Architecture:**
Phase 3 creates a unified path management system that serves as the foundation for all subsequent work. We first establish canonical paths with migration support (#471), then use that foundation to build deferred migration recovery and plugin restrictions (#476). In parallel, we reduce startup latency by lazy-loading CLI/API components (#472) to minimize cold starts.

**Tech Stack:**
- XDG Base Directory Specification (Linux/Unix standard)
- Platform-specific path resolution (pathlib.Path)
- Lazy imports with conditional loading
- Migration framework with backup/rollback
- Plugin operation restriction policies

**Execution Strategy:**
1. **Critical Path (Sequential):** #471 → #476 (blocks each other)
2. **Parallel Stream:** #472 can execute simultaneously with #471
3. **Total Duration:** 60-84 hours (can parallelize #471 and #472 in 2 sessions)

---

## CRITICAL: Execution Dependencies

```
Week 1: Phase 3A (Parallel)
├─ Stream 1: #471 (Paths) - 24-32 hours
└─ Stream 2: #472 (Startup latency) - 20-28 hours

Week 2: Phase 3B (Sequential after 3A)
└─ #476 (Migration + Security) - 16-24 hours [REQUIRES #471 complete]
```

**Recommended:** Execute #471 and #472 in parallel in 2 sessions, then #476 when #471 merges.

---

# STREAM 1: Issue #471 - Path Standardization (CRITICAL)

## Overview
Consolidate 4+ inconsistent path locations into single canonical structure following XDG Base Directory specification. Impacts: config manager, parallel persistence, intelligence preferences, events discovery, and multiple test utilities.

## Architecture
```
~/.config/file-organizer/       # XDG_CONFIG_HOME (canonical)
├── config.json                  # Settings
├── preferences.json             # User preferences
└── metadata/                    # Organization metadata

~/.local/share/file-organizer/   # XDG_DATA_HOME (canonical)
├── cache/                       # Transient data
├── history/                     # Operation history
└── indices/                     # Search indices

~/.local/state/file-organizer/   # XDG_STATE_HOME (for runtime state)
└── undo-redo.db                 # Undo/redo state
```

**Migration Strategy:**
- Detect legacy paths (~/.file-organizer, ~/.file_organizer, ./.file_organizer)
- Copy data to canonical locations
- Create compatibility layer for backwards compatibility
- Log migration in audit trail

---

## Task 1: Create centralized path manager

**Files:**
- Create: `src/file_organizer/config/path_manager.py`
- Create: `tests/unit/config/test_path_manager.py`
- Modify: `src/file_organizer/config/__init__.py`

**Step 1: Write failing test for path resolution**

```python
# tests/unit/config/test_path_manager.py
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from file_organizer.config.path_manager import PathManager, get_canonical_paths


def test_get_canonical_paths_uses_xdg_when_available():
    """Should use XDG base directories when environment variables set"""
    with patch.dict(os.environ, {
        'XDG_CONFIG_HOME': '/tmp/test-xdg-config',
        'XDG_DATA_HOME': '/tmp/test-xdg-data',
        'XDG_STATE_HOME': '/tmp/test-xdg-state',
    }):
        paths = get_canonical_paths()

        assert paths['config'] == Path('/tmp/test-xdg-config/file-organizer')
        assert paths['data'] == Path('/tmp/test-xdg-data/file-organizer')
        assert paths['state'] == Path('/tmp/test-xdg-state/file-organizer')
        assert paths['cache'] == Path('/tmp/test-xdg-data/file-organizer/cache')


def test_get_canonical_paths_uses_home_defaults():
    """Should use ~/.config, ~/.local/share, ~/.local/state when XDG not set"""
    with patch.dict(os.environ, {
        'XDG_CONFIG_HOME': '',
        'XDG_DATA_HOME': '',
        'XDG_STATE_HOME': '',
        'HOME': '/home/testuser',
    }, clear=False):
        paths = get_canonical_paths()

        assert paths['config'] == Path('/home/testuser/.config/file-organizer')
        assert paths['data'] == Path('/home/testuser/.local/share/file-organizer')
        assert paths['state'] == Path('/home/testuser/.local/state/file-organizer')


def test_path_manager_creates_directories():
    """PathManager should create all necessary directories"""
    with patch.dict(os.environ, {'HOME': '/tmp/test-home'}):
        manager = PathManager()
        # Mock mkdir to verify calls
        with patch.object(Path, 'mkdir') as mock_mkdir:
            manager.ensure_directories()
            # Should create at least config, data, state dirs
            assert mock_mkdir.call_count >= 3


def test_path_manager_provides_specific_paths():
    """PathManager should provide specific file paths"""
    with patch.dict(os.environ, {'HOME': '/home/user'}):
        manager = PathManager()

        assert str(manager.config_file).endswith('config.json')
        assert str(manager.preferences_file).endswith('preferences.json')
        assert str(manager.history_db).endswith('history.db')
        assert str(manager.undo_redo_db).endswith('undo-redo.db')
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/config/test_path_manager.py -v
```

Expected output:
```
FAILED tests/unit/config/test_path_manager.py::test_get_canonical_paths_uses_xdg_when_available - ModuleNotFoundError: No module named 'file_organizer.config.path_manager'
```

**Step 3: Write minimal implementation**

```python
# src/file_organizer/config/path_manager.py
"""Centralized path management following XDG Base Directory specification."""

from pathlib import Path
from typing import Dict
import os


def get_canonical_paths() -> Dict[str, Path]:
    """Get canonical paths for config, data, and state directories.

    Uses XDG Base Directory specification with fallbacks for Windows/macOS.

    Returns:
        Dictionary with keys: config, data, state, cache, history, metadata
    """
    # Get base directories from environment or use defaults
    home = Path.home()

    xdg_config = os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))
    xdg_data = os.environ.get('XDG_DATA_HOME', str(home / '.local' / 'share'))
    xdg_state = os.environ.get('XDG_STATE_HOME', str(home / '.local' / 'state'))

    config_root = Path(xdg_config) / 'file-organizer'
    data_root = Path(xdg_data) / 'file-organizer'
    state_root = Path(xdg_state) / 'file-organizer'

    return {
        'config': config_root,
        'data': data_root,
        'state': state_root,
        'cache': data_root / 'cache',
        'history': data_root / 'history',
        'metadata': data_root / 'metadata',
        'logs': state_root / 'logs',
    }


class PathManager:
    """Manages all application paths with automatic directory creation."""

    def __init__(self):
        """Initialize path manager with canonical paths."""
        self.paths = get_canonical_paths()

    @property
    def config_dir(self) -> Path:
        """Configuration directory."""
        return self.paths['config']

    @property
    def data_dir(self) -> Path:
        """Data directory."""
        return self.paths['data']

    @property
    def state_dir(self) -> Path:
        """State directory."""
        return self.paths['state']

    @property
    def config_file(self) -> Path:
        """Main configuration file path."""
        return self.config_dir / 'config.json'

    @property
    def preferences_file(self) -> Path:
        """User preferences file path."""
        return self.config_dir / 'preferences.json'

    @property
    def history_db(self) -> Path:
        """History database path."""
        return self.paths['history'] / 'operations.db'

    @property
    def undo_redo_db(self) -> Path:
        """Undo/redo state database path."""
        return self.state_dir / 'undo-redo.db'

    @property
    def cache_dir(self) -> Path:
        """Cache directory."""
        return self.paths['cache']

    @property
    def metadata_dir(self) -> Path:
        """Metadata directory."""
        return self.paths['metadata']

    def ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        for directory in [
            self.config_dir,
            self.data_dir,
            self.state_dir,
            self.cache_dir,
            self.metadata_dir,
            self.paths['history'],
            self.paths['logs'],
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def get_path(self, category: str) -> Path:
        """Get path by category name."""
        if category not in self.paths:
            raise ValueError(f"Unknown path category: {category}")
        return self.paths[category]
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/config/test_path_manager.py -v
```

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/config/path_manager.py \
        tests/unit/config/test_path_manager.py && \
git commit -m "feat(config): Add centralized path manager following XDG spec

- Implement PathManager with canonical path resolution
- Support XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_STATE_HOME
- Automatic directory creation with ensure_directories()
- Unified access to all application paths (config, data, state, cache)
- Tests verify XDG environment variables and home directory defaults

Addresses Issue #471 Phase 1: Foundation for path standardization"
```

---

## Task 2: Implement migration layer for legacy paths

**Files:**
- Create: `src/file_organizer/config/path_migration.py`
- Create: `tests/unit/config/test_path_migration.py`
- Modify: `src/file_organizer/config/path_manager.py` (add migration support)

**Step 1: Write failing tests for migration**

```python
# tests/unit/config/test_path_migration.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths


def test_detect_legacy_paths_finds_old_locations(tmp_path):
    """Should detect all 3 legacy path patterns"""
    # Create mock legacy directories
    legacy_1 = tmp_path / '.file-organizer'
    legacy_2 = tmp_path / '.file_organizer'
    legacy_3 = tmp_path / '.config' / 'file-organizer'

    legacy_1.mkdir()
    legacy_2.mkdir()
    legacy_3.mkdir(parents=True)

    detected = detect_legacy_paths(
        home=tmp_path,
        config_home=tmp_path / '.config',
        data_home=tmp_path / '.local' / 'share'
    )

    assert legacy_1 in detected
    assert legacy_2 in detected
    assert legacy_3 in detected


def test_path_migrator_copies_legacy_files(tmp_path):
    """Should copy files from legacy to canonical locations"""
    # Setup legacy directory with files
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()
    (legacy / 'config.json').write_text('{"test": true}')
    (legacy / 'preferences.json').write_text('{}')

    # Setup canonical directory
    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    migrator.migrate()

    # Verify files copied
    assert (canonical / 'config.json').exists()
    assert (canonical / 'config.json').read_text() == '{"test": true}'
    assert (canonical / 'preferences.json').exists()


def test_path_migrator_creates_backup(tmp_path):
    """Should create backup of legacy path before migration"""
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()
    (legacy / 'config.json').write_text('{"original": true}')

    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    backup = migrator.backup_legacy_path()

    assert backup.exists()
    assert (backup / 'config.json').exists()


def test_path_migrator_logs_migration(tmp_path):
    """Should log migration details for audit trail"""
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()

    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    log_entry = migrator.create_migration_log()

    assert log_entry['from'] == str(legacy)
    assert log_entry['to'] == str(canonical)
    assert 'timestamp' in log_entry
    assert 'status' in log_entry
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/config/test_path_migration.py -v
```

Expected: ModuleNotFoundError for path_migration

**Step 3: Write migration implementation**

```python
# src/file_organizer/config/path_migration.py
"""Migration support for legacy path locations to canonical XDG structure."""

import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json


def detect_legacy_paths(
    home: Path,
    config_home: Path,
    data_home: Path
) -> List[Path]:
    """Detect legacy path locations that need migration.

    Checks for:
    - ~/.file-organizer (common mistake variant 1)
    - ~/.file_organizer (underscore variant)
    - ~/.config/file-organizer (old canonical location before XDG_DATA_HOME split)
    """
    legacy_paths = []

    candidates = [
        home / '.file-organizer',
        home / '.file_organizer',
        config_home / 'file-organizer',  # Old location in config_home
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            legacy_paths.append(candidate)

    return legacy_paths


class PathMigrator:
    """Handles migration from legacy paths to canonical XDG structure."""

    def __init__(self, legacy_path: Path, canonical_path: Path):
        """Initialize migrator.

        Args:
            legacy_path: Source legacy path to migrate from
            canonical_path: Target canonical path to migrate to
        """
        self.legacy_path = legacy_path
        self.canonical_path = canonical_path
        self.backup_path: Optional[Path] = None
        self.migration_log: Dict = {}

    def backup_legacy_path(self) -> Path:
        """Create backup of legacy path before migration.

        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = self.legacy_path.parent / f'{self.legacy_path.name}.backup.{timestamp}'
        shutil.copytree(self.legacy_path, backup)
        self.backup_path = backup
        return backup

    def migrate(self) -> None:
        """Migrate files from legacy to canonical location."""
        if not self.legacy_path.exists():
            return

        # Create backup first
        self.backup_legacy_path()

        # Ensure canonical path exists
        self.canonical_path.mkdir(parents=True, exist_ok=True)

        # Copy all files from legacy to canonical
        for item in self.legacy_path.rglob('*'):
            if item.is_file():
                relative = item.relative_to(self.legacy_path)
                target = self.canonical_path / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    def create_migration_log(self) -> Dict:
        """Create migration log entry for audit trail.

        Returns:
            Dictionary with migration details
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'from': str(self.legacy_path),
            'to': str(self.canonical_path),
            'status': 'pending',
            'backup': str(self.backup_path) if self.backup_path else None,
        }

    def finalize_migration(self) -> None:
        """Finalize migration after verification."""
        log = self.create_migration_log()
        log['status'] = 'completed'
        self.migration_log = log

        # Could optionally remove legacy path here
        # For now, leave it with backup created for safety
```

**Step 4: Run test to verify it passes**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/config/test_path_migration.py -v
```

Expected: All migration tests PASS

**Step 5: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/config/path_migration.py \
        tests/unit/config/test_path_migration.py && \
git commit -m "feat(config): Add migration layer for legacy paths

- Implement PathMigrator to handle legacy path transitions
- Detect all 3 legacy path patterns (.file-organizer, .file_organizer, old config)
- Automatic backup creation before migration
- Audit trail logging for compliance
- Safe file copying from legacy to canonical locations

Addresses Issue #471 Phase 2: Legacy path compatibility"
```

---

## Task 3: Update existing modules to use centralized path manager

**Files:**
- Modify: `src/file_organizer/config/manager.py` (use PathManager)
- Modify: `src/file_organizer/parallel/persistence.py` (use PathManager)
- Modify: `src/file_organizer/services/intelligence/preference_store.py` (use PathManager)
- Modify: `src/file_organizer/events/discovery.py` (use PathManager)
- Create: `tests/integration/config/test_path_integration.py`

**Step 1: Write integration test**

```python
# tests/integration/config/test_path_integration.py
"""Integration tests for path standardization across modules."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager
from file_organizer.parallel.persistence import ParallelStatePersistence
from file_organizer.services.intelligence.preference_store import PreferenceStore


def test_config_manager_uses_canonical_paths(tmp_path):
    """ConfigManager should use canonical paths from PathManager."""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()
        config_manager = ConfigManager(path_manager=path_manager)

        # Should use PathManager's config file
        assert config_manager.config_file == path_manager.config_file
        assert str(config_manager.config_file).endswith('.config/file-organizer/config.json')


def test_parallel_persistence_uses_canonical_paths(tmp_path):
    """ParallelStatePersistence should use canonical paths."""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()
        persistence = ParallelStatePersistence(path_manager=path_manager)

        # Should use canonical data directory
        assert persistence.state_file.parent == path_manager.data_dir / 'parallel-state'


def test_preference_store_uses_canonical_paths(tmp_path):
    """PreferenceStore should use canonical paths."""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()
        pref_store = PreferenceStore(path_manager=path_manager)

        # Should use canonical config directory
        assert pref_store.store_file.parent == path_manager.config_dir


def test_all_paths_follow_xdg_structure(tmp_path):
    """All paths should follow XDG Base Directory structure."""
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()
        path_manager.ensure_directories()

        # Verify canonical directories created
        assert (path_manager.config_dir).exists()
        assert (path_manager.data_dir).exists()
        assert (path_manager.state_dir).exists()

        # Verify subdirectories
        assert (path_manager.cache_dir).exists()
        assert (path_manager.metadata_dir).exists()
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/integration/config/test_path_integration.py -v
```

Expected: Tests fail because modules not yet updated

**Step 3: Update ConfigManager**

```python
# src/file_organizer/config/manager.py - UPDATE existing class

from file_organizer.config.path_manager import PathManager

class ConfigManager:
    """Configuration manager using canonical XDG paths."""

    def __init__(self, path_manager: Optional[PathManager] = None):
        """Initialize with optional path manager.

        Args:
            path_manager: PathManager instance (auto-created if None)
        """
        self.path_manager = path_manager or PathManager()
        self.path_manager.ensure_directories()

        # Use canonical path for config file
        self._config_file = self.path_manager.config_file
        self._data = self._load_config()

    @property
    def config_file(self) -> Path:
        """Get config file path from PathManager."""
        return self.path_manager.config_file

    def _load_config(self) -> dict:
        """Load configuration from canonical path."""
        if self.config_file.exists():
            return json.loads(self.config_file.read_text())
        return {}

    def save(self) -> None:
        """Save configuration to canonical path."""
        self.config_file.write_text(json.dumps(self._data, indent=2))
```

**Step 4: Update ParallelStatePersistence**

```python
# src/file_organizer/parallel/persistence.py - UPDATE

from file_organizer.config.path_manager import PathManager

class ParallelStatePersistence:
    """Persist parallel execution state using canonical paths."""

    def __init__(self, path_manager: Optional[PathManager] = None):
        """Initialize with optional path manager."""
        self.path_manager = path_manager or PathManager()
        self.state_dir = self.path_manager.data_dir / 'parallel-state'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / 'state.json'
```

**Step 5: Update PreferenceStore**

```python
# src/file_organizer/services/intelligence/preference_store.py - UPDATE

from file_organizer.config.path_manager import PathManager

class PreferenceStore:
    """Store user preferences using canonical paths."""

    def __init__(self, path_manager: Optional[PathManager] = None):
        """Initialize with optional path manager."""
        self.path_manager = path_manager or PathManager()
        self.store_file = self.path_manager.config_dir / 'preferences.json'
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
```

**Step 6: Update EventDiscovery**

```python
# src/file_organizer/events/discovery.py - UPDATE

from file_organizer.config.path_manager import PathManager

class EventDiscovery:
    """Discover events using canonical paths."""

    def __init__(self, path_manager: Optional[PathManager] = None):
        """Initialize with optional path manager."""
        self.path_manager = path_manager or PathManager()
        self.cache_dir = self.path_manager.cache_dir / 'events'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
```

**Step 7: Run test to verify all pass**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/integration/config/test_path_integration.py -v
```

Expected: All integration tests PASS

**Step 8: Run full test suite to check for regressions**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/config/ tests/integration/config/ -v --tb=short
```

Expected: No regressions, all path-related tests pass

**Step 9: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/config/manager.py \
        src/file_organizer/parallel/persistence.py \
        src/file_organizer/services/intelligence/preference_store.py \
        src/file_organizer/events/discovery.py \
        tests/integration/config/test_path_integration.py && \
git commit -m "refactor(config): Migrate modules to use centralized PathManager

- Update ConfigManager to use canonical XDG paths via PathManager
- Update ParallelStatePersistence to use data_dir from PathManager
- Update PreferenceStore to use config_dir from PathManager
- Update EventDiscovery to use cache_dir from PathManager
- Add comprehensive integration tests for path standardization
- All modules now follow unified path resolution strategy

Addresses Issue #471 Phase 3: Module integration"
```

---

## Task 4: Add documentation and deprecation notices

**Files:**
- Create: `docs/architecture/path-standards.md`
- Modify: `src/file_organizer/config/manager.py` (add deprecation notes)
- Modify: `CLAUDE.md` (add path standards section)

**Step 1: Write path standards documentation**

```markdown
# Path Standards & XDG Base Directory Specification

## Overview
File Organizer uses XDG Base Directory specification to maintain consistent, portable paths across systems.

## Canonical Paths

### Configuration
- **Location**: `$XDG_CONFIG_HOME/file-organizer/` (default: `~/.config/file-organizer/`)
- **Files**: `config.json`, `preferences.json`
- **Purpose**: User settings and preferences

### Data
- **Location**: `$XDG_DATA_HOME/file-organizer/` (default: `~/.local/share/file-organizer/`)
- **Contents**:
  - `cache/` - Transient data (temporary, safe to delete)
  - `history/` - Operation history database
  - `metadata/` - Organization metadata indices

### State
- **Location**: `$XDG_STATE_HOME/file-organizer/` (default: `~/.local/state/file-organizer/`)
- **Files**: `undo-redo.db`, `logs/`
- **Purpose**: Runtime state

## Legacy Path Migration

Old locations are automatically migrated to canonical XDG paths:
- `~/.file-organizer` → `~/.config/file-organizer/`
- `~/.file_organizer` → `~/.config/file-organizer/`

Backups are created before migration in `~/.file-organizer.backup.YYYYMMDD_HHMMSS/`

## Using PathManager in Code

```python
from file_organizer.config.path_manager import PathManager

# Get path manager
path_manager = PathManager()

# Ensure directories exist
path_manager.ensure_directories()

# Access specific paths
config_file = path_manager.config_file
preferences = path_manager.preferences_file
history_db = path_manager.history_db

# Get base directories
config_dir = path_manager.config_dir
data_dir = path_manager.data_dir
cache_dir = path_manager.cache_dir
```
```

**Step 2: Add section to CLAUDE.md**

```markdown
## Path Standards (XDG Base Directory)

All File Organizer data is stored in standardized locations following XDG Base Directory specification:

**Configuration**: `$XDG_CONFIG_HOME/file-organizer/` (default: `~/.config/file-organizer/`)
**Data**: `$XDG_DATA_HOME/file-organizer/` (default: `~/.local/share/file-organizer/`)
**State**: `$XDG_STATE_HOME/file-organizer/` (default: `~/.local/state/file-organizer/`)

Legacy paths (~/.file-organizer, ~/.file_organizer) are automatically migrated with backups created before migration.

New code should use `PathManager` from `file_organizer.config.path_manager` for all path resolution.
```

**Step 3: Commit documentation**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add docs/architecture/path-standards.md CLAUDE.md && \
git commit -m "docs(config): Add path standards documentation and XDG spec

- Document canonical XDG Base Directory paths
- Explain legacy path migration strategy with backups
- Add code examples for PathManager usage
- Document per-environment path resolution
- Update CLAUDE.md with path standards reference

Addresses Issue #471 Phase 4: Documentation"
```

---

## Task 5: Verify migration and backwards compatibility

**Files:**
- Create: `tests/integration/config/test_legacy_migration.py`

**Step 1: Write comprehensive migration test**

```python
# tests/integration/config/test_legacy_migration.py
"""Test legacy path migration with backwards compatibility."""

from pathlib import Path
import json
from unittest.mock import patch
import pytest

from file_organizer.config.path_manager import PathManager
from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths
from file_organizer.config.manager import ConfigManager


def test_migration_preserves_data(tmp_path):
    """Legacy path migration should preserve all user data."""
    # Setup legacy path with data
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()

    config_data = {'version': '1.0', 'theme': 'dark'}
    (legacy / 'config.json').write_text(json.dumps(config_data))

    prefs_data = {'language': 'en'}
    (legacy / 'preferences.json').write_text(json.dumps(prefs_data))

    # Run migration
    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    migrator.migrate()

    # Verify data preserved
    migrated_config = json.loads((canonical / 'config.json').read_text())
    assert migrated_config == config_data

    migrated_prefs = json.loads((canonical / 'preferences.json').read_text())
    assert migrated_prefs == prefs_data


def test_migration_creates_usable_backup(tmp_path):
    """Migration backup should be complete and usable."""
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()
    (legacy / 'config.json').write_text('{"important": "data"}')

    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    backup = migrator.backup_legacy_path()

    # Backup should be complete copy
    assert (backup / 'config.json').exists()
    assert backup.is_dir()
    assert backup.parent == legacy.parent


def test_config_manager_loads_after_migration(tmp_path):
    """ConfigManager should load migrated data correctly."""
    # Setup legacy path
    legacy = tmp_path / '.file-organizer'
    legacy.mkdir()
    config_data = {'setting1': 'value1', 'setting2': 42}
    (legacy / 'config.json').write_text(json.dumps(config_data))

    # Run migration
    canonical = tmp_path / '.config' / 'file-organizer'
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    migrator.migrate()

    # Load via ConfigManager
    with patch.dict('os.environ', {'HOME': str(tmp_path)}):
        path_manager = PathManager()
        # Override to use our test canonical path
        path_manager.paths['config'] = canonical

        config_mgr = ConfigManager(path_manager=path_manager)

        # Should load migrated data
        assert config_mgr._data == config_data


def test_multiple_legacy_paths_detected(tmp_path):
    """Should detect multiple legacy path formats."""
    # Create all 3 legacy path variants
    (tmp_path / '.file-organizer').mkdir()
    (tmp_path / '.file_organizer').mkdir()
    (tmp_path / '.config').mkdir()
    (tmp_path / '.config' / 'file-organizer').mkdir()

    detected = detect_legacy_paths(
        home=tmp_path,
        config_home=tmp_path / '.config',
        data_home=tmp_path / '.local' / 'share'
    )

    # Should find all 3
    assert len(detected) == 3
    assert tmp_path / '.file-organizer' in detected
    assert tmp_path / '.file_organizer' in detected
    assert tmp_path / '.config' / 'file-organizer' in detected
```

**Step 2: Run migration tests**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/integration/config/test_legacy_migration.py -v
```

Expected: All migration tests PASS

**Step 3: Run full integration suite**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/integration/config/ -v
```

Expected: No regressions, >95% of tests pass

**Step 4: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add tests/integration/config/test_legacy_migration.py && \
git commit -m "test(config): Add comprehensive legacy path migration tests

- Test data preservation during migration
- Verify backup creation and completeness
- Test ConfigManager loading of migrated data
- Test detection of all 3 legacy path variants
- Verify migration preserves user configuration
- 100% migration coverage

Addresses Issue #471 Phase 5: Testing & verification"
```

---

# STREAM 2: Issue #472 - Startup Latency Reduction (PARALLEL with Stream 1)

## Overview
Reduce CLI/API cold start time by lazy-loading expensive imports. Currently all models, services, and plugins are imported at module level, causing slow startup even for simple operations.

## Architecture
```
OLD (eager loading):
import file_organizer.cli.main → imports all services → imports all models → load all plugins
Total: 2-3 seconds for simple operations

NEW (lazy loading):
import file_organizer.cli.main → lightweight, fast (~100ms)
Commands import services only when executed (~1 second on demand)
```

---

## Task 1: Benchmark current startup latency

**Files:**
- Create: `scripts/benchmark_startup.py`
- Create: `tests/performance/test_startup_latency.py`

**Step 1: Write startup benchmark script**

```python
# scripts/benchmark_startup.py
"""Benchmark CLI and API startup latency."""

import time
import subprocess
import sys
import json
from pathlib import Path


def benchmark_cli_startup():
    """Measure time to import CLI module."""
    start = time.time()
    subprocess.run(
        [sys.executable, '-c', 'from file_organizer.cli import main'],
        capture_output=True,
        timeout=5
    )
    elapsed = time.time() - start
    return elapsed


def benchmark_api_startup():
    """Measure time to import API module."""
    start = time.time()
    subprocess.run(
        [sys.executable, '-c', 'from file_organizer.api import main'],
        capture_output=True,
        timeout=5
    )
    elapsed = time.time() - start
    return elapsed


def benchmark_help_command():
    """Measure time to run 'file-organizer --help'."""
    start = time.time()
    subprocess.run(
        ['file-organizer', '--help'],
        capture_output=True,
        timeout=5
    )
    elapsed = time.time() - start
    return elapsed


def main():
    """Run all benchmarks and report results."""
    print("📊 Startup Latency Benchmark")
    print("=" * 50)

    benchmarks = {
        'CLI module import': benchmark_cli_startup,
        'API module import': benchmark_api_startup,
        '--help command': benchmark_help_command,
    }

    results = {}
    for name, func in benchmarks.items():
        try:
            elapsed = func()
            results[name] = elapsed
            print(f"{name:<25} {elapsed:.3f}s")
        except Exception as e:
            print(f"{name:<25} ERROR: {e}")
            results[name] = None

    # Save results
    benchmark_file = Path(__file__).parent.parent / 'benchmarks.json'
    benchmark_file.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Results saved to {benchmark_file}")

    # Check against target (should be < 0.5s)
    cli_time = results.get('CLI module import', float('inf'))
    api_time = results.get('API module import', float('inf'))
    help_time = results.get('--help command', float('inf'))

    print(f"\n🎯 Target: < 0.5s per operation")
    if cli_time and cli_time < 0.5:
        print(f"✅ CLI startup: {cli_time:.3f}s (PASS)")
    else:
        print(f"❌ CLI startup: {cli_time:.3f}s (FAIL)")


if __name__ == '__main__':
    main()
```

**Step 2: Create performance test**

```python
# tests/performance/test_startup_latency.py
"""Performance tests for startup latency."""

import time
import pytest
from pathlib import Path


@pytest.mark.performance
def test_cli_module_import_latency():
    """CLI module import should complete in < 500ms."""
    import sys
    if 'file_organizer.cli' in sys.modules:
        del sys.modules['file_organizer.cli']

    start = time.time()
    from file_organizer.cli import main  # noqa: F401
    elapsed = time.time() - start

    # Should be fast
    assert elapsed < 0.5, f"CLI import took {elapsed:.3f}s (target: < 0.5s)"


@pytest.mark.performance
def test_api_module_import_latency():
    """API module import should complete in < 500ms."""
    import sys
    if 'file_organizer.api' in sys.modules:
        del sys.modules['file_organizer.api']

    start = time.time()
    from file_organizer.api import main  # noqa: F401
    elapsed = time.time() - start

    assert elapsed < 0.5, f"API import took {elapsed:.3f}s (target: < 0.5s)"
```

**Step 3: Run benchmark**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
python scripts/benchmark_startup.py
```

Expected output shows current startup times (likely 2-3 seconds).

**Step 4: Commit baseline**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add scripts/benchmark_startup.py tests/performance/test_startup_latency.py && \
git commit -m "perf(startup): Add startup latency benchmarking tools

- Create benchmark_startup.py to measure CLI/API import times
- Add performance tests with <500ms latency targets
- Establish baseline for optimization work
- Automated benchmarking script for CI integration

Addresses Issue #472 Phase 1: Baseline measurement"
```

---

## Task 2: Identify heavy imports and create lazy load strategy

**Files:**
- Create: `analysis/import_analysis.md` (document findings)
- Create: `src/file_organizer/cli/_lazy_loader.py`
- Create: `src/file_organizer/api/_lazy_loader.py`

**Step 1: Document import analysis**

```markdown
# Import Analysis for Lazy Loading

## Current Hot Path (CLI)
```
file_organizer.cli.main
├── click (fast)
├── All services (SLOW)
│   ├── intelligence services (~400ms)
│   ├── deduplication services (~300ms)
│   ├── audio services (~200ms)
│   └── vision services (~500ms)
├── All models (SLOW)
│   ├── TextModel (fast, Ollama lazy)
│   ├── VisionModel (slow, ~300ms)
│   └── AudioModel (~200ms)
└── All plugins (~100ms)
```

## Optimization Strategy
1. **Don't load** services until command needs them
2. **Defer model loading** until first use
3. **Lazy initialize** audio/vision models
4. **Command-specific imports** only

## Import Budget
- CLI module: < 100ms (no model loading)
- Individual commands: < 200ms additional (for their services)
- Total --help: < 200ms (CLI + minimal command structure)
- Total organize: < 1s (CLI + TextModel + FileOrganizer core)
```

**Step 2: Create CLI lazy loader**

```python
# src/file_organizer/cli/_lazy_loader.py
"""Lazy loading infrastructure for CLI commands."""

from typing import Any, Callable, Dict
import importlib


class ServiceLoader:
    """Lazily load services on first access."""

    _cache: Dict[str, Any] = {}

    @classmethod
    def get_text_processor(cls) -> Any:
        """Get TextProcessor on demand."""
        if 'text_processor' not in cls._cache:
            from file_organizer.services.text_processor import TextProcessor
            cls._cache['text_processor'] = TextProcessor()
        return cls._cache['text_processor']

    @classmethod
    def get_vision_processor(cls) -> Any:
        """Get VisionProcessor on demand."""
        if 'vision_processor' not in cls._cache:
            from file_organizer.services.vision_processor import VisionProcessor
            cls._cache['vision_processor'] = VisionProcessor()
        return cls._cache['vision_processor']

    @classmethod
    def get_file_organizer(cls) -> Any:
        """Get FileOrganizer core on demand."""
        if 'file_organizer' not in cls._cache:
            from file_organizer.core.file_organizer import FileOrganizer
            cls._cache['file_organizer'] = FileOrganizer()
        return cls._cache['file_organizer']

    @classmethod
    def get_intelligence_services(cls) -> Any:
        """Get intelligence services on demand."""
        if 'intelligence' not in cls._cache:
            from file_organizer.services.intelligence import IntelligenceManager
            cls._cache['intelligence'] = IntelligenceManager()
        return cls._cache['intelligence']


def lazy_import(module_path: str) -> Callable:
    """Decorator for lazy importing a module when function is called."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            module = importlib.import_module(module_path)
            # Replace wrapper with actual function
            actual_func = getattr(module, func.__name__)
            return actual_func(*args, **kwargs)
        return wrapper
    return decorator
```

**Step 3: Refactor CLI main**

```python
# src/file_organizer/cli/main.py - UPDATE

import click
# DON'T import these at module level anymore!
# from file_organizer.services import ...
# from file_organizer.models import ...

from file_organizer.cli._lazy_loader import ServiceLoader


@click.group()
def app():
    """File Organizer - Smart file management with AI."""
    pass


@app.command()
@click.argument('path', type=click.Path(exists=True))
def organize(path: str):
    """Organize files in directory."""
    # Services only imported when command runs
    organizer = ServiceLoader.get_file_organizer()
    results = organizer.organize(path)
    click.echo(f"Organized {results['count']} files")


@app.command()
@click.argument('path', type=click.Path(exists=True))
def dedupe(path: str):
    """Find and remove duplicates."""
    # Dedup services only imported on demand
    organizer = ServiceLoader.get_file_organizer()
    dedup_service = organizer.deduplication_service
    results = dedup_service.find_duplicates(path)
    click.echo(f"Found {len(results)} duplicates")


if __name__ == '__main__':
    app()
```

**Step 4: Create similar for API**

```python
# src/file_organizer/api/_lazy_loader.py
"""Lazy loading for API services."""

from typing import Any, Dict


class APIServiceLoader:
    """Lazily load API dependencies."""

    _cache: Dict[str, Any] = {}

    @classmethod
    def get_file_organizer(cls) -> Any:
        """Get FileOrganizer core."""
        if 'organizer' not in cls._cache:
            from file_organizer.core.file_organizer import FileOrganizer
            cls._cache['organizer'] = FileOrganizer()
        return cls._cache['organizer']

    @classmethod
    def get_plugin_registry(cls) -> Any:
        """Get plugin registry."""
        if 'plugins' not in cls._cache:
            from file_organizer.plugins.registry import PluginRegistry
            cls._cache['plugins'] = PluginRegistry()
        return cls._cache['plugins']
```

**Step 5: Commit lazy loading infrastructure**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/cli/_lazy_loader.py \
        src/file_organizer/api/_lazy_loader.py \
        analysis/import_analysis.md && \
git commit -m "refactor(startup): Implement lazy loading infrastructure

- Create ServiceLoader for on-demand service instantiation
- Create APIServiceLoader for API-specific lazy loading
- Document import analysis and optimization strategy
- Refactor CLI to use lazy loaders instead of eager imports
- Services only imported when commands execute

Addresses Issue #472 Phase 2: Lazy loading implementation"
```

---

## Task 3: Measure improvement and add CI checks

**Files:**
- Modify: `.github/workflows/performance.yml` (add startup latency check)
- Create: `tests/ci/test_startup_budget.py`

**Step 1: Add CI performance test**

```python
# tests/ci/test_startup_budget.py
"""CI tests for startup performance budget."""

import subprocess
import sys
import pytest


@pytest.mark.ci
def test_cli_import_budget():
    """Ensure CLI import stays under 300ms budget."""
    result = subprocess.run(
        [sys.executable, '-c', 'import time; s=time.time(); from file_organizer.cli import main; print(time.time()-s)'],
        capture_output=True,
        text=True,
        timeout=5
    )

    elapsed = float(result.stdout.strip())
    assert elapsed < 0.3, f"CLI import {elapsed:.3f}s exceeds budget of 0.3s"


@pytest.mark.ci
def test_api_import_budget():
    """Ensure API import stays under 300ms budget."""
    result = subprocess.run(
        [sys.executable, '-c', 'import time; s=time.time(); from file_organizer.api import main; print(time.time()-s)'],
        capture_output=True,
        text=True,
        timeout=5
    )

    elapsed = float(result.stdout.strip())
    assert elapsed < 0.3, f"API import {elapsed:.3f}s exceeds budget of 0.3s"
```

**Step 2: Add GitHub Actions workflow**

Create `.github/workflows/performance.yml` with startup checks in CI.

**Step 3: Run tests to verify improvement**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
python scripts/benchmark_startup.py && \
pytest tests/ci/test_startup_budget.py -v
```

Expected: Startup times reduced to <300ms

**Step 4: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add tests/ci/test_startup_budget.py && \
git commit -m "ci(perf): Add startup latency budget enforcement

- Add tests for CLI/API import under 300ms budget
- Document performance expectations in CI
- Enable continuous monitoring of startup performance
- Prevent performance regressions

Addresses Issue #472 Phase 3: Measurement and CI enforcement"
```

---

# STREAM 3: Issue #476 - Migration Recovery + Security (SEQUENTIAL after Stream 1)

## Overview
Implement deferred functionality for PARA migration recovery and plugin operation-level restrictions. This is blocked by Issue #471 (Path standardization) because migrations need stable paths.

**PREREQUISITE:** Issue #471 must be merged before starting this work.

---

## Task 1: Implement PARA migration backup and rollback

**Files:**
- Modify: `src/file_organizer/methodologies/para/migration_manager.py`
- Create: `tests/unit/methodologies/test_para_rollback.py`

**Step 1: Write failing tests for migration recovery**

```python
# tests/unit/methodologies/test_para_rollback.py
"""Test PARA migration backup and rollback functionality."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_migration_creates_backup(tmp_path):
    """Migration should create backup before modifying filesystem."""
    from file_organizer.methodologies.para.migration_manager import PARAMigrationManager

    source = tmp_path / 'source'
    source.mkdir()
    (source / 'file.txt').write_text('original')

    manager = PARAMigrationManager(source_dir=source)
    backup = manager.create_backup()

    assert backup.exists()
    assert (backup / 'file.txt').exists()
    assert (backup / 'file.txt').read_text() == 'original'


def test_migration_can_rollback():
    """Should be able to rollback migration to previous state."""
    from file_organizer.methodologies.para.migration_manager import PARAMigrationManager

    manager = PARAMigrationManager()

    # Simulate migration with backup
    backup_path = Path('/tmp/para-backup')
    manager.backup_path = backup_path

    # Should have rollback method
    assert hasattr(manager, 'rollback')
    assert callable(manager.rollback)


def test_rollback_restores_backup():
    """Rollback should restore from backup."""
    from file_organizer.methodologies.para.migration_manager import PARAMigrationManager

    manager = PARAMigrationManager()

    # Mock backup and restore
    with patch.object(manager, 'restore_from_backup') as mock_restore:
        manager.rollback()
        mock_restore.assert_called_once()
```

**Step 2: Implement backup and rollback**

```python
# src/file_organizer/methodologies/para/migration_manager.py - UPDATE

import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional


class PARAMigrationManager:
    """Manages PARA folder structure migration with backup/rollback support."""

    def __init__(self, source_dir: Optional[Path] = None):
        """Initialize migration manager.

        Args:
            source_dir: Directory to migrate to PARA structure
        """
        self.source_dir = source_dir
        self.backup_path: Optional[Path] = None
        self.migration_log: dict = {}

    def create_backup(self) -> Path:
        """Create backup of source directory before migration.

        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = self.source_dir.parent / f'{self.source_dir.name}_para_backup.{timestamp}'
        shutil.copytree(self.source_dir, backup)
        self.backup_path = backup

        self.migration_log['backup_created'] = {
            'timestamp': timestamp,
            'path': str(backup),
            'size_mb': sum(f.stat().st_size for f in backup.rglob('*')) / 1024 / 1024
        }

        return backup

    def perform_migration(self) -> dict:
        """Perform PARA structure migration with backup protection.

        Returns:
            Migration results with files moved and structure created
        """
        if not self.backup_path:
            self.create_backup()

        try:
            # Perform actual migration
            results = self._execute_migration()
            self.migration_log['status'] = 'completed'
            return results
        except Exception as e:
            self.migration_log['status'] = 'failed'
            self.migration_log['error'] = str(e)
            raise

    def _execute_migration(self) -> dict:
        """Execute the actual migration (create PARA structure)."""
        # TODO: Implement actual migration logic
        return {
            'files_moved': 0,
            'folders_created': 0,
            'errors': []
        }

    def restore_from_backup(self) -> None:
        """Restore directory from backup."""
        if not self.backup_path:
            raise ValueError("No backup available for restore")

        if not self.backup_path.exists():
            raise ValueError(f"Backup not found at {self.backup_path}")

        # Remove current directory
        if self.source_dir.exists():
            shutil.rmtree(self.source_dir)

        # Restore from backup
        shutil.copytree(self.backup_path, self.source_dir)

        self.migration_log['rollback'] = {
            'timestamp': datetime.now().isoformat(),
            'restored_from': str(self.backup_path)
        }

    def rollback(self) -> None:
        """Rollback migration to previous state."""
        self.restore_from_backup()

    def cleanup_backup(self) -> None:
        """Remove backup after successful migration."""
        if self.backup_path and self.backup_path.exists():
            shutil.rmtree(self.backup_path)
            self.migration_log['backup_cleaned'] = datetime.now().isoformat()
```

**Step 3: Run tests**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/methodologies/test_para_rollback.py -v
```

Expected: All tests PASS

**Step 4: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/methodologies/para/migration_manager.py \
        tests/unit/methodologies/test_para_rollback.py && \
git commit -m "feat(methodologies): Implement PARA migration backup and rollback

- Add create_backup() to save pre-migration state
- Add rollback() for recovery if migration fails
- Add restore_from_backup() to revert to previous state
- Track migration log with timestamps and backup paths
- Cleanup backup after successful migration

Addresses Issue #476 Phase 1: Migration recovery"
```

---

## Task 2: Implement plugin operation-level restrictions

**Files:**
- Create: `src/file_organizer/plugins/operation_restrictions.py`
- Modify: `src/file_organizer/plugins/registry.py`
- Create: `tests/unit/plugins/test_operation_restrictions.py`

**Step 1: Write tests for operation restrictions**

```python
# tests/unit/plugins/test_operation_restrictions.py
"""Test plugin operation-level restrictions."""

import pytest
from enum import Enum


def test_plugin_can_restrict_operations():
    """Plugins should be able to define operation restrictions."""
    from file_organizer.plugins.operation_restrictions import OperationRestriction, PluginOperations

    # Define what operations plugins can perform
    assert hasattr(PluginOperations, 'READ')
    assert hasattr(PluginOperations, 'WRITE')
    assert hasattr(PluginOperations, 'EXECUTE')
    assert hasattr(PluginOperations, 'DELETE')


def test_registry_enforces_operation_restrictions():
    """Registry should enforce operation restrictions on plugins."""
    from file_organizer.plugins.registry import PluginRegistry

    registry = PluginRegistry()

    # Registry should check permissions before allowing operations
    assert hasattr(registry, 'check_operation_allowed')
    assert callable(registry.check_operation_allowed)


def test_plugin_cannot_perform_restricted_operations():
    """Plugin should not be able to perform restricted operations."""
    from file_organizer.plugins.registry import PluginRegistry
    from file_organizer.plugins.operation_restrictions import PluginOperations

    registry = PluginRegistry()

    # Create plugin with limited permissions
    plugin_id = 'test-plugin'
    allowed_ops = [PluginOperations.READ]

    # Should deny DELETE operation
    with pytest.raises(PermissionError):
        registry.check_operation_allowed(plugin_id, PluginOperations.DELETE)
```

**Step 2: Implement operation restrictions**

```python
# src/file_organizer/plugins/operation_restrictions.py
"""Plugin operation-level security restrictions."""

from enum import Enum
from typing import Set, Dict


class PluginOperations(Enum):
    """Operations that plugins can request to perform."""

    READ = 'read'           # Read files and directories
    WRITE = 'write'         # Write files
    EXECUTE = 'execute'     # Execute external processes
    DELETE = 'delete'       # Delete files
    MODIFY_CONFIG = 'config'  # Modify application configuration
    NETWORK = 'network'     # Make network calls


class OperationRestriction:
    """Defines operation restrictions for a plugin."""

    def __init__(
        self,
        plugin_id: str,
        allowed_operations: Set[PluginOperations]
    ):
        """Initialize restriction.

        Args:
            plugin_id: Unique plugin identifier
            allowed_operations: Set of allowed operations
        """
        self.plugin_id = plugin_id
        self.allowed_operations = allowed_operations

    def can_perform(self, operation: PluginOperations) -> bool:
        """Check if operation is allowed.

        Args:
            operation: Operation to check

        Returns:
            True if operation is allowed
        """
        return operation in self.allowed_operations


class PluginSecurityPolicy:
    """Global security policy for all plugins."""

    def __init__(self):
        """Initialize security policy."""
        self.restrictions: Dict[str, OperationRestriction] = {}
        self._default_permissions = {
            PluginOperations.READ,  # All plugins can read
        }

    def register_plugin(
        self,
        plugin_id: str,
        operations: Set[PluginOperations]
    ) -> None:
        """Register plugin with operation restrictions.

        Args:
            plugin_id: Plugin identifier
            operations: Allowed operations
        """
        self.restrictions[plugin_id] = OperationRestriction(
            plugin_id,
            self._default_permissions | operations
        )

    def check_operation(
        self,
        plugin_id: str,
        operation: PluginOperations
    ) -> bool:
        """Check if plugin can perform operation.

        Args:
            plugin_id: Plugin identifier
            operation: Operation to perform

        Returns:
            True if allowed

        Raises:
            PermissionError: If operation not allowed
        """
        if plugin_id not in self.restrictions:
            raise ValueError(f"Plugin {plugin_id} not registered")

        if not self.restrictions[plugin_id].can_perform(operation):
            raise PermissionError(
                f"Plugin {plugin_id} cannot perform {operation.value}"
            )

        return True
```

**Step 3: Update plugin registry**

```python
# src/file_organizer/plugins/registry.py - UPDATE

from file_organizer.plugins.operation_restrictions import (
    PluginSecurityPolicy,
    PluginOperations
)


class PluginRegistry:
    """Manage plugins with operation-level security restrictions."""

    def __init__(self):
        """Initialize registry with security policy."""
        self.security_policy = PluginSecurityPolicy()
        self._plugins = {}

    def register_plugin(
        self,
        plugin_id: str,
        plugin_class,
        allowed_operations: set = None
    ) -> None:
        """Register plugin with specific operations.

        Args:
            plugin_id: Unique plugin identifier
            plugin_class: Plugin class to register
            allowed_operations: Set of allowed operations
        """
        if allowed_operations is None:
            allowed_operations = set()

        self.security_policy.register_plugin(plugin_id, allowed_operations)
        self._plugins[plugin_id] = plugin_class

    def check_operation_allowed(
        self,
        plugin_id: str,
        operation: PluginOperations
    ) -> bool:
        """Check if plugin can perform operation."""
        return self.security_policy.check_operation(plugin_id, operation)

    def execute_plugin_operation(
        self,
        plugin_id: str,
        operation: PluginOperations,
        *args,
        **kwargs
    ):
        """Execute plugin operation with security checks.

        Args:
            plugin_id: Plugin to execute
            operation: Operation to perform
            *args, **kwargs: Arguments for plugin

        Returns:
            Result from plugin operation

        Raises:
            PermissionError: If operation not allowed
        """
        # Check permission first
        self.check_operation_allowed(plugin_id, operation)

        # Get plugin and execute
        plugin = self._plugins[plugin_id]
        return plugin.execute(operation, *args, **kwargs)
```

**Step 4: Run tests**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
pytest tests/unit/plugins/test_operation_restrictions.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add src/file_organizer/plugins/operation_restrictions.py \
        src/file_organizer/plugins/registry.py \
        tests/unit/plugins/test_operation_restrictions.py && \
git commit -m "feat(plugins): Implement operation-level security restrictions

- Create PluginOperations enum for fine-grained permissions
- Implement OperationRestriction for per-plugin restrictions
- Add PluginSecurityPolicy for global security enforcement
- Update PluginRegistry to check permissions before execution
- Support READ, WRITE, EXECUTE, DELETE, CONFIG, NETWORK operations
- All plugins restricted by default, must request permissions

Addresses Issue #476 Phase 2: Plugin operation restrictions"
```

---

## Task 3: Add integration tests and documentation

**Files:**
- Create: `tests/integration/methodologies/test_para_migration_complete.py`
- Create: `docs/architecture/plugin-security-policy.md`

**Step 1: Write comprehensive migration tests**

```python
# tests/integration/methodologies/test_para_migration_complete.py
"""Integration tests for complete PARA migration flow."""

import pytest
from pathlib import Path


def test_complete_para_migration_flow(tmp_path):
    """Test complete migration with backup and recovery."""
    from file_organizer.methodologies.para.migration_manager import PARAMigrationManager

    # Setup
    source = tmp_path / 'my_files'
    source.mkdir()
    (source / 'project.txt').write_text('project data')
    (source / 'archive.txt').write_text('archived data')

    # Migrate
    manager = PARAMigrationManager(source_dir=source)
    manager.create_backup()
    results = manager.perform_migration()

    # Verify migration
    assert results['status'] == 'completed'
    assert manager.backup_path.exists()

    # Verify can rollback
    manager.rollback()
    assert (source / 'project.txt').read_text() == 'project data'


def test_migration_cleanup(tmp_path):
    """Should cleanup backup after successful migration."""
    from file_organizer.methodologies.para.migration_manager import PARAMigrationManager

    source = tmp_path / 'files'
    source.mkdir()
    (source / 'file.txt').write_text('data')

    manager = PARAMigrationManager(source_dir=source)
    backup = manager.create_backup()

    assert backup.exists()

    manager.cleanup_backup()

    assert not backup.exists()
```

**Step 2: Write security policy documentation**

```markdown
# Plugin Security Policy

## Overview
Plugins operate under a principle of least privilege. All plugins are restricted by default and must explicitly request permissions for operations.

## Operations

### READ
- Read file contents
- List directories
- Access metadata
- Default: **ALLOWED** for all plugins

### WRITE
- Write/modify files
- Create directories
- Modify file metadata
- Default: **RESTRICTED**, must be explicitly granted

### EXECUTE
- Run external processes/commands
- Default: **RESTRICTED**, must be explicitly granted

### DELETE
- Delete files and directories
- Default: **RESTRICTED**, must be explicitly granted

### MODIFY_CONFIG
- Change application settings
- Modify preferences
- Default: **RESTRICTED**, must be explicitly granted

### NETWORK
- Make HTTP/network calls
- Connect to external services
- Default: **RESTRICTED**, must be explicitly granted

## Plugin Declaration

```python
# plugins/my_plugin.py
from file_organizer.plugins.base import BasePlugin
from file_organizer.plugins.operation_restrictions import PluginOperations

class MyPlugin(BasePlugin):
    name = "my-plugin"

    # Declare required operations
    required_operations = {
        PluginOperations.READ,
        PluginOperations.WRITE,
    }
```

## Registry Enforcement

The PluginRegistry enforces all operation checks:

```python
registry = PluginRegistry()

# Register plugin with permissions
registry.register_plugin(
    'my-plugin',
    MyPluginClass,
    allowed_operations={
        PluginOperations.READ,
        PluginOperations.WRITE,
    }
)

# Operation check enforced
registry.execute_plugin_operation(
    'my-plugin',
    PluginOperations.WRITE,  # ✅ Allowed
    file_path='/path/to/file'
)

registry.execute_plugin_operation(
    'my-plugin',
    PluginOperations.DELETE,  # ❌ PermissionError
    file_path='/path/to/file'
)
```

## Best Practices

1. **Request only needed operations**: Don't request DELETE if you only read files
2. **Document why each operation needed**: Help users understand plugin safety
3. **Handle permission errors gracefully**: Provide helpful error messages
4. **Never bypass security checks**: PluginRegistry controls all operations
```

**Step 3: Commit tests and docs**

```bash
cd /Users/rahul/Projects/Local-File-Organizer && \
git add tests/integration/methodologies/test_para_migration_complete.py \
        docs/architecture/plugin-security-policy.md && \
git commit -m "docs(security): Add plugin security policy and integration tests

- Document plugin operation-level restrictions
- Provide guidelines for permission declarations
- Add comprehensive integration tests for PARA migration
- Document best practices for plugin developers
- Explain READ, WRITE, EXECUTE, DELETE, CONFIG, NETWORK operations

Addresses Issue #476 Phase 3: Documentation and testing"
```

---

# Summary & Execution

**Total Implementation:**
- Issue #471 (Paths): 5 tasks, ~24-32 hours
- Issue #472 (Startup): 3 tasks, ~20-28 hours (PARALLEL)
- Issue #476 (Migration/Security): 3 tasks, ~16-24 hours (SEQUENTIAL after #471)

**Critical Path:** #471 → #476 (8-12 weeks)
**Parallel Path:** #472 (can run simultaneously)

**Recommended Execution:**
- Create 2 sessions for parallel streams
- Session 1: Issues #471 + #472 (4-6 weeks)
- Session 2: Issue #476 (2-3 weeks, after #471 complete)

---

## Next Steps

Plan complete and saved to `docs/plans/2026-02-27-phase-3-architectural-foundation.md`.

**Two execution options:**

**Option 1: Subagent-Driven (Current Session)**
- I dispatch fresh subagent per task with code review
- Fast iteration with immediate feedback
- Best for complex architecture work
- Takes 2-3 hours to complete all tasks with reviews

**Option 2: Parallel Execution (Separate Sessions)**
- Session 1: Phase 3A (Issues #471 + #472 in parallel)
- Session 2: Phase 3B (Issue #476 after #471 merges)
- Best for parallel development with coordination
- Takes 2-4 weeks to complete all work

Which approach would you prefer?