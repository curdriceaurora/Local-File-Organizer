# Path Standardization and Migration Guide

## Overview

File Organizer v2.0 standardizes application paths. We use the **XDG Base Directory Specification**. This system replaces legacy hardcoded paths. We now use a centralized, configurable path management system.

## Key Changes

### New: Centralized PathManager

The `PathManager` class gives unified access to all application paths:

```python
from file_organizer.config.path_manager import PathManager

path_manager = PathManager()

# Access standard directories
config_dir = path_manager.config_dir          # ~/.config/file-organizer (XDG_CONFIG_HOME)
data_dir = path_manager.data_dir              # ~/.local/share/file-organizer (XDG_DATA_HOME)
state_dir = path_manager.state_dir            # ~/.local/state/file-organizer (XDG_STATE_HOME)
cache_dir = path_manager.cache_dir            # data_dir/cache

# Access specific files
config_file = path_manager.config_file        # config_dir/config.json (low-level helper)
preferences_file = path_manager.preferences_file  # config_dir/preferences.json
history_db = path_manager.history_db          # data_dir/history/operations.db
undo_redo_db = path_manager.undo_redo_db      # state_dir/undo-redo.db
```

> Note: The software saves profile settings as `config.yaml` in the config directory.

### XDG Base Directory Specification

The new system reads XDG environment variables. It has sensible fallback values:

| Variable | Default | Purpose |
|----------|---------|---------|
| `XDG_CONFIG_HOME` | `~/.config` | User-specific configuration files |
| `XDG_DATA_HOME` | `~/.local/share` | User-specific data files |
| `XDG_STATE_HOME` | `~/.local/state` | User-specific state or cache data |

### Legacy Paths

These legacy paths are deprecated. Do not use them:

| Old Path | New Path | Notes |
|----------|----------|-------|
| `~/.config/file-organizer` | `~/.config/file-organizer` | The software still supports this config path. |
| `~/.file-organizer` | `~/.local/share/file-organizer` | Data files move to data_dir. |
| `~/.file_organizer` | `~/.local/share/file-organizer` | This is a legacy typo variant. |

## Migration Guide

### End Users

File Organizer v2.0 automatically migrates data from legacy paths:

1. **First Run**: The software finds legacy paths. It creates a backup.
2. **Migration**: The software copies files to new XDG locations.
3. **Backup**: The software saves original files with a timestamp suffix (e.g., `.backup.20260227_143022_123456`).

To start migration manually:

```bash
file-organizer config migrate --from-legacy
```

### Developers

#### Use PathManager in New Code

Always use PathManager to access paths:

```python
from file_organizer.config.path_manager import PathManager

path_manager = PathManager()

# Ensure all directories exist
path_manager.ensure_directories()

# Save configuration
config_file = path_manager.config_file
config_file.parent.mkdir(parents=True, exist_ok=True)
config_file.write_text(config_yaml)

# Access data directories
data_file = path_manager.data_dir / "mydata.json"
```

#### Update Existing Code

Replace hardcoded paths with PathManager.

**Before (Legacy):**

```python
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "file-organizer"
config_path = DEFAULT_CONFIG_DIR / "config.yaml"
```

**After (New):**

```python
from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager

path_manager = PathManager()
config_mgr = ConfigManager(config_dir=path_manager.config_dir)
config_path = config_mgr.config_dir / "config.yaml"
```

#### Module Integration

Modules must accept a PathManager parameter if they manage their own paths:

```python
from file_organizer.config.path_manager import PathManager

class MyService:
    def __init__(self, path_manager: PathManager | None = None):
        self.path_manager = path_manager or PathManager()
        self.data_dir = self.path_manager.data_dir / "myservice"
        self.data_dir.mkdir(parents=True, exist_ok=True)
```

#### ConfigManager and PreferenceStore

Both classes accept custom path parameters:

```python
from file_organizer.config import ConfigManager, PathManager
from file_organizer.services.intelligence.preference_store import PreferenceStore

path_manager = PathManager()
path_manager.ensure_directories()

# ConfigManager with PathManager
config_manager = ConfigManager(config_dir=path_manager.config_dir)

# PreferenceStore with PathManager
pref_store = PreferenceStore(storage_path=path_manager.data_dir / "preferences")
```

## Migration Classes

### PathManager

- **Purpose**: Provides a unified interface for all application paths.
- **Location**: `file_organizer.config.path_manager`
- **Key Methods**:
  - `ensure_directories()`: Create all necessary directories.
  - `get_path(category)`: Get a path by its category name.

### PathMigrator

- **Purpose**: Migrates files from legacy paths to canonical paths.
- **Location**: `file_organizer.config.path_migration`
- **Features**:
  - Creates automatic backups with timestamps.
  - Copies files safely and preserves metadata.
  - Logs migration data for an audit trail.
  - Reverts changes with backups.

### detect_legacy_paths()

- **Purpose**: Detects legacy path locations.
- **Returns**: A list of legacy paths that exist.
- **Checks**:
  - `~/.file-organizer` (legacy hyphen variant)
  - `~/.file_organizer` (legacy underscore variant)
  - `~/.config/file-organizer` (old canonical location)

## Backwards Compatibility

All existing code operates normally during the transition:

- The software auto-migrates legacy paths on the first run.
- ConfigManager and PreferenceStore work with old and new paths.
- Default fallbacks maintain system compatibility.

## Environment Variables

Use environment variables to configure paths:

```bash
# Use custom config directory
export XDG_CONFIG_HOME=/custom/config
file-organizer config list

# Use custom data directory
export XDG_DATA_HOME=/custom/data
file-organizer analyze

# Use custom state directory
export XDG_STATE_HOME=/custom/state
file-organizer daemon start
```

## Test Path Configuration

Verify your path configuration:

```bash
# Show current paths
file-organizer config paths

# Show path debug info
file-organizer config paths --verbose

# Show migration status
file-organizer config migration-status
```

## Troubleshooting

### Files Not Found After Migration

If you cannot find files after migration:

1. Check the backup location: `ls -la ~/.file-organizer.backup.*`
2. Restore files manually: `cp -r ~/.file-organizer.backup.TIMESTAMP/* ~/.local/share/file-organizer/`
3. Report the issue and include the migration log.

### Permission Denied Errors

If you see permission errors:

```bash
# Fix directory permissions
chmod -R 755 ~/.config/file-organizer
chmod -R 755 ~/.local/share/file-organizer
chmod -R 755 ~/.local/state/file-organizer
```

### XDG Variables Do Not Work

Set environment variables before you start the application:

```bash
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
file-organizer
```

## See Also

- **XDG Base Directory Specification**: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
- **Path Manager Implementation**: `src/file_organizer/config/path_manager.py`
- **Path Migration**: `src/file_organizer/config/path_migration.py`
- **Integration Tests**: `tests/integration/config/test_path_integration.py`
