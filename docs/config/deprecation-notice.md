# Path Deprecation Notice

## Deprecated: Hardcoded Legacy Paths

**Status**: Deprecated in v2.x | Removal target: next major release

### Affected Paths

These hardcoded path patterns are deprecated. We will remove them in a future major release:

```python
# DEPRECATED - Do not use in new code
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "file-organizer"
DEFAULT_DATA_DIR = Path.home() / ".file-organizer"
DEFAULT_PREFERENCES_DIR = Path.home() / ".file_organizer" / "preferences"
```

### Reason for Change

The hardcoded paths were not flexible. They were not standard:

- They do not support the XDG Base Directory Specification.
- They do not use environment variables.
- They do not have centralized path management.
- They are difficult to test and change.

### Migration Path

**Timeline**:

- **Current**: Use PathManager-based paths.
- **Future major release**: We will remove legacy hardcoded paths.

**Required Actions**:

1. Update your code. Use `PathManager`.
2. Test your code with new XDG paths.
3. Update your documentation and scripts.

### Before & After

#### Old Pattern (DEPRECATED)

```python
from pathlib import Path

# ❌ DEPRECATED - Direct path construction
config_dir = Path.home() / ".config" / "file-organizer"
config_file = config_dir / "config.yaml"

# Hard to test, not customizable
if config_file.exists():
    config = json.loads(config_file.read_text())
```

#### New Pattern (RECOMMENDED)

```python
from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager

# ✅ NEW - Use centralized path/config managers
path_manager = PathManager()
config_manager = ConfigManager(config_dir=path_manager.config_dir)
config_file = config_manager.config_dir / "config.yaml"

# Testable, respects XDG, customizable
if config_file.exists():
    config = json.loads(config_file.read_text())
```

### Deprecation Warnings

Starting in v2.0, these patterns will show warnings:

```python
import warnings
from pathlib import Path

# This pattern is deprecated
config_dir = Path.home() / ".config" / "file-organizer"

# DeprecationWarning: Hardcoded path construction is deprecated.
# Use PathManager instead: from file_organizer.config.path_manager import PathManager
```

### Modules to Update

We will update these modules to use `PathManager`:

| Module | Path Type | Status | PR/Issue |
|--------|-----------|--------|----------|
| `ConfigManager` | config_dir | Supports custom path (v2.0) | #471 |
| `PreferenceStore` | storage_path | Supports custom path (v2.0) | #471 |
| `EventDiscovery` | event logs | Pending update | #471 Task 6 |
| `ParallelStatePersistence` | state_dir | Pending update | #471 Task 6 |
| All CLI commands | Various | Gradual migration | Ongoing |

### FAQ

**Q: Can I use legacy paths?**
A: Yes, current versions support legacy paths with automatic migration. We will remove this support in a future major release.

**Q: Will you migrate my data automatically?**
A: Yes, PathMigrator does automatic migration with backups during the first run.

**Q: How do I update my code?**
A: Read the [Path Standardization Guide](./path-standardization.md) for migration examples.

**Q: How do I use custom path configuration?**
A: Use environment variables (XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_STATE_HOME) or send PathManager to relevant classes.

**Q: When will you remove legacy support?**
A: We plan to remove it in a future major release. Read release notes for the final schedule.

### Stop Deprecation Warnings

To stop warnings temporarily (not recommended):

```python
import warnings
from file_organizer.config.path_manager import DEPRECATION_WARNINGS

# Suppress specific warning category
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Or specifically for File Organizer
warnings.filterwarnings("ignore", message=".*hardcoded path.*")
```

### Getting Help

If you find problems with path migration:

1. **Read the guide**: [Path Standardization Guide](./path-standardization.md)
2. **Start diagnostics**: `file-organizer config paths --verbose`
3. **Report a problem**: https://github.com/curdriceaurora/Local-File-Organizer/issues
4. **Examine backups**: We save migration backups with a `.backup.TIMESTAMP` suffix.

## See Also

- [Path Standardization Guide](./path-standardization.md)
- [PathManager Guide](./path-standardization.md)
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
