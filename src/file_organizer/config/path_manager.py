"""Centralized path management following XDG Base Directory specification."""

import os
from pathlib import Path


def get_canonical_paths() -> dict[str, Path]:
    """Get canonical paths for config, data, and state directories.

    Uses XDG Base Directory specification with fallbacks for Windows/macOS.

    Returns:
        Dictionary with keys: config, data, state, cache, history, metadata
    """
    # Get base directories from environment or use defaults
    home = Path.home()

    # Handle empty string environment variables by treating them as unset
    xdg_config = os.environ.get('XDG_CONFIG_HOME') or str(home / '.config')
    xdg_data = os.environ.get('XDG_DATA_HOME') or str(home / '.local' / 'share')
    xdg_state = os.environ.get('XDG_STATE_HOME') or str(home / '.local' / 'state')

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
