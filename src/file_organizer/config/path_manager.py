"""Centralized path management following platform-appropriate conventions."""

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_state_dir

APP_NAME = "file-organizer"


def get_config_dir() -> Path:
    """Return the platform-appropriate user config directory.

    Returns:
        - macOS:   ~/Library/Application Support/file-organizer/
        - Linux:   ~/.config/file-organizer/   (or $XDG_CONFIG_HOME/file-organizer/)
        - Windows: %APPDATA%/file-organizer/

    The XDG_CONFIG_HOME environment variable is respected on Linux/macOS.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_NAME
    return Path(user_config_dir(APP_NAME))


def get_data_dir() -> Path:
    """Return the platform-appropriate user data directory.

    Returns:
        - macOS:   ~/Library/Application Support/file-organizer/
        - Linux:   ~/.local/share/file-organizer/   (or $XDG_DATA_HOME/...)
        - Windows: %APPDATA%/file-organizer/
    """
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / APP_NAME
    return Path(user_data_dir(APP_NAME))


def get_state_dir() -> Path:
    """Return the platform-appropriate user state directory.

    Returns:
        - macOS:   ~/Library/Application Support/file-organizer/
        - Linux:   ~/.local/state/file-organizer/   (or $XDG_STATE_HOME/...)
        - Windows: %APPDATA%/file-organizer/
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / APP_NAME
    return Path(user_state_dir(APP_NAME))


def get_cache_dir() -> Path:
    """Return the platform-appropriate user cache directory."""
    return Path(user_cache_dir(APP_NAME))


def get_canonical_paths() -> dict[str, Path]:
    """Get canonical paths for config, data, and state directories.

    Uses platformdirs for correct platform-specific paths:
    - macOS: ~/Library/Application Support/file-organizer/
    - Linux: ~/.config/file-organizer/ and ~/.local/share/file-organizer/
    - Windows: %APPDATA%/file-organizer/

    XDG environment variables are respected on Linux/macOS.

    Returns:
        Dictionary with keys: config, data, state, cache, history, metadata, logs
    """
    config_root = get_config_dir()
    data_root = get_data_dir()
    state_root = get_state_dir()

    return {
        "config": config_root,
        "data": data_root,
        "state": state_root,
        "cache": get_cache_dir(),
        "history": data_root / "history",
        "metadata": data_root / "metadata",
        "logs": state_root / "logs",
    }


class PathManager:
    """Manages all application paths with automatic directory creation."""

    def __init__(self) -> None:
        """Initialize path manager with canonical paths."""
        self.paths = get_canonical_paths()

    @property
    def config_dir(self) -> Path:
        """Configuration directory."""
        return self.paths["config"]

    @property
    def data_dir(self) -> Path:
        """Data directory."""
        return self.paths["data"]

    @property
    def state_dir(self) -> Path:
        """State directory."""
        return self.paths["state"]

    @property
    def config_file(self) -> Path:
        """Main configuration file path."""
        return self.config_dir / "config.json"

    @property
    def preferences_file(self) -> Path:
        """User preferences file path."""
        return self.config_dir / "preferences.json"

    @property
    def history_db(self) -> Path:
        """History database path."""
        return self.paths["history"] / "operations.db"

    @property
    def undo_redo_db(self) -> Path:
        """Undo/redo state database path."""
        return self.state_dir / "undo-redo.db"

    @property
    def cache_dir(self) -> Path:
        """Cache directory."""
        return self.paths["cache"]

    @property
    def metadata_dir(self) -> Path:
        """Metadata directory."""
        return self.paths["metadata"]

    def ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        for directory in [
            self.config_dir,
            self.data_dir,
            self.state_dir,
            self.cache_dir,
            self.metadata_dir,
            self.paths["history"],
            self.paths["logs"],
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def get_path(self, category: str) -> Path:
        """Get path by category name."""
        if category not in self.paths:
            raise ValueError(f"Unknown path category: {category}")
        return self.paths[category]
