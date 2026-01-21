"""
Directory-level preference management with hierarchical inheritance.

This module provides directory-scoped preferences with parent directory
inheritance, allowing fine-grained control over file organization behavior
at different levels of the directory tree.
"""

from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DirectoryPrefs:
    """
    Manages directory-level preferences with hierarchical inheritance.

    Supports:
    - Per-directory preference scoping
    - Parent directory inheritance
    - Override capabilities for subdirectories
    - Efficient lookup with path resolution
    """

    def __init__(self):
        """Initialize the directory preference manager."""
        self._preferences: Dict[str, dict] = {}
        logger.debug("DirectoryPrefs initialized")

    def set_preference(
        self,
        path: Path,
        pref: dict,
        override_parent: bool = False
    ) -> None:
        """
        Set a preference for a specific directory.

        Args:
            path: Directory path for the preference
            pref: Preference dictionary containing preference data
            override_parent: If True, this preference will not inherit from parent

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(
            ...     Path("/home/user/documents"),
            ...     {"folder_mappings": {"pdf": "PDFs"}},
            ...     override_parent=False
            ... )
        """
        normalized_path = str(path.resolve())

        # Add metadata to preference
        pref_with_meta = {
            **pref,
            "_override_parent": override_parent,
            "_path": normalized_path
        }

        self._preferences[normalized_path] = pref_with_meta
        logger.debug(
            f"Set preference for {normalized_path}, override_parent={override_parent}"
        )

    def get_preference_with_inheritance(
        self,
        path: Path
    ) -> Optional[dict]:
        """
        Get preference for a path, with inheritance from parent directories.

        Walks up the directory tree and merges preferences from parent
        directories, with child preferences taking precedence. If a
        directory has override_parent=True, inheritance stops there.

        Args:
            path: Path to get preference for

        Returns:
            Merged preference dictionary, or None if no preferences found

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(Path("/home/user"), {"global": "setting"})
            >>> dp.set_preference(
            ...     Path("/home/user/docs"),
            ...     {"folder_mappings": {"pdf": "PDFs"}}
            ... )
            >>> pref = dp.get_preference_with_inheritance(Path("/home/user/docs"))
            >>> pref["global"]
            'setting'
            >>> pref["folder_mappings"]["pdf"]
            'PDFs'
        """
        normalized_path = path.resolve()

        # Collect all preferences from root to current path
        preferences_chain: List[dict] = []
        current_path = normalized_path

        while True:
            current_str = str(current_path)

            if current_str in self._preferences:
                pref = self._preferences[current_str]
                preferences_chain.insert(0, pref)  # Add to front for bottom-up merge

                # Stop if this preference overrides parent
                if pref.get("_override_parent", False):
                    logger.debug(
                        f"Stopping inheritance at {current_str} (override_parent=True)"
                    )
                    break

            # Move to parent directory
            parent = current_path.parent
            if parent == current_path:  # Reached root
                break
            current_path = parent

        if not preferences_chain:
            logger.debug(f"No preferences found for {normalized_path}")
            return None

        # Merge preferences from parent to child (child overrides parent)
        merged = self._merge_preferences(preferences_chain)

        # Remove internal metadata from result
        result = {
            k: v for k, v in merged.items()
            if not k.startswith("_")
        }

        logger.debug(
            f"Resolved preference for {normalized_path} "
            f"(merged {len(preferences_chain)} levels)"
        )
        return result

    def _merge_preferences(self, preferences_chain: List[dict]) -> dict:
        """
        Merge a chain of preferences from parent to child.

        Args:
            preferences_chain: List of preference dicts, ordered from parent to child

        Returns:
            Merged preference dictionary
        """
        if not preferences_chain:
            return {}

        merged = {}

        for pref in preferences_chain:
            merged = self._deep_merge(merged, pref)

        return merged

    def _deep_merge(self, base: dict, overlay: dict) -> dict:
        """
        Deep merge two dictionaries, with overlay taking precedence.

        Args:
            base: Base dictionary
            overlay: Dictionary to merge on top

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override with new value
                result[key] = value

        return result

    def list_directory_preferences(self) -> List[Tuple[Path, dict]]:
        """
        List all directory preferences without inheritance resolution.

        Returns:
            List of (path, preference) tuples

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(Path("/home/user"), {"setting": "value"})
            >>> prefs = dp.list_directory_preferences()
            >>> len(prefs)
            1
            >>> prefs[0][0]
            PosixPath('/home/user')
        """
        result = []

        for path_str, pref in self._preferences.items():
            # Remove internal metadata
            clean_pref = {
                k: v for k, v in pref.items()
                if not k.startswith("_")
            }
            result.append((Path(path_str), clean_pref))

        logger.debug(f"Listed {len(result)} directory preferences")
        return result

    def remove_preference(self, path: Path) -> bool:
        """
        Remove preference for a specific directory.

        Args:
            path: Directory path to remove preference for

        Returns:
            True if preference was removed, False if not found

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(Path("/home/user"), {"setting": "value"})
            >>> dp.remove_preference(Path("/home/user"))
            True
            >>> dp.remove_preference(Path("/home/user"))
            False
        """
        normalized_path = str(path.resolve())

        if normalized_path in self._preferences:
            del self._preferences[normalized_path]
            logger.debug(f"Removed preference for {normalized_path}")
            return True

        logger.debug(f"No preference found to remove for {normalized_path}")
        return False

    def clear_all(self) -> None:
        """
        Clear all directory preferences.

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(Path("/home/user"), {"setting": "value"})
            >>> dp.clear_all()
            >>> len(dp.list_directory_preferences())
            0
        """
        count = len(self._preferences)
        self._preferences.clear()
        logger.info(f"Cleared all directory preferences ({count} entries)")

    def get_statistics(self) -> dict:
        """
        Get statistics about stored preferences.

        Returns:
            Dictionary containing statistics

        Example:
            >>> dp = DirectoryPrefs()
            >>> dp.set_preference(Path("/home/user"), {"setting": "value"})
            >>> stats = dp.get_statistics()
            >>> stats["total_directories"]
            1
        """
        override_count = sum(
            1 for pref in self._preferences.values()
            if pref.get("_override_parent", False)
        )

        return {
            "total_directories": len(self._preferences),
            "override_parent_count": override_count,
            "inheritance_enabled_count": len(self._preferences) - override_count
        }
