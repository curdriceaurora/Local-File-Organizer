# Path Deprecation Notice

## Deprecated: Hardcoded Legacy Paths

**Status**: Deprecated in v2.0 | Scheduled for Removal: v3.0

### Affected Paths

The following hardcoded path patterns are **deprecated** and will be removed in v3.0:

```python
# DEPRECATED - Do not use in new code
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "file-organizer"
DEFAULT_DATA_DIR = Path.home() / ".file-organizer"
DEFAULT_PREFERENCES_DIR = Path.home() / ".file_organizer" / "preferences"
```

### Why This Change?

The hardcoded paths were inflexible and non-standard:

- No support for XDG Base Directory Specification
- No environment variable configuration
- No centralized path management
- Difficult to test and customize

### Migration Path

**Timeline**:

- **v2.0** (Current): New PathManager available, legacy paths still functional
- **v2.1-2.4**: Deprecation warnings when using legacy patterns
- **v3.0**: Legacy path handling removed

**Action Required**:

1. Update your code to use `PathManager`
2. Test with new XDG paths
3. Update documentation and scripts

### Before & After

#### Old Pattern (DEPRECATED)

```python
from pathlib import Path

# ❌ DEPRECATED - Direct path construction
config_dir = Path.home() / ".config" / "file-organizer"
config_file = config_dir / "config.json"

# Hard to test, not customizable
if config_file.exists():
    config = json.loads(config_file.read_text())
```

#### New Pattern (RECOMMENDED)

```python
from file_organizer.config.path_manager import PathManager

# ✅ NEW - Use centralized PathManager
path_manager = PathManager()
config_file = path_manager.config_file

# Testable, respects XDG, customizable
if config_file.exists():
    config = json.loads(config_file.read_text())
```

### Deprecation Warnings

Starting in v2.0, the following patterns will generate warnings:

```python
import warnings
from pathlib import Path

# This pattern is deprecated
config_dir = Path.home() / ".config" / "file-organizer"

# DeprecationWarning: Hardcoded path construction is deprecated.
# Use PathManager instead: from file_organizer.config.path_manager import PathManager
```

### Modules Being Updated

The following modules will be updated to use `PathManager`:

| Module | Path Type | Status | PR/Issue |
|--------|-----------|--------|----------|
| `ConfigManager` | config_dir | Supports custom path (v2.0) | #471 |
| `PreferenceStore` | storage_path | Supports custom path (v2.0) | #471 |
| `EventDiscovery` | event logs | Pending update | #471 Task 6 |
| `ParallelStatePersistence` | state_dir | Pending update | #471 Task 6 |
| All CLI commands | Various | Gradual migration | Ongoing |

### FAQ

**Q: Can I still use legacy paths?**
A: Yes, v2.0 still supports them via automatic migration. v3.0 will remove this support.

**Q: Will my data be migrated automatically?**
A: Yes, PathMigrator handles automatic migration with backups on first run.

**Q: How do I update my code?**
A: See the [Path Standardization Guide](./path-standardization.md) for migration examples.

**Q: What if I have custom path configuration?**
A: Use environment variables (XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_STATE_HOME) or pass PathManager to relevant classes.

**Q: When will legacy support be removed?**
A: v3.0 (estimated 3-6 months after v2.0 release).

### Suppressing Deprecation Warnings

If you need to suppress warnings temporarily (not recommended):

```python
import warnings
from file_organizer.config.path_manager import DEPRECATION_WARNINGS

# Suppress specific warning category
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Or specifically for File Organizer
warnings.filterwarnings("ignore", message=".*hardcoded path.*")
```

### Getting Help

If you encounter issues with path migration:

1. **Check the guide**: [Path Standardization Guide](./path-standardization.md)
2. **Run diagnostics**: `file-organizer config paths --verbose`
3. **File an issue**: https://github.com/curdriceaurora/Local-File-Organizer/issues
4. **Check backups**: Migration backups are preserved with `.backup.TIMESTAMP` suffix

## See Also

- [Path Standardization Guide](./path-standardization.md)
- [PathManager Guide](./path-standardization.md)
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
