"""
Preference Storage & Persistence Module

Provides JSON-based preference storage with atomic writes, schema validation,
backup/restore functionality, and migration support.

Schema Version: 1.0
"""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class SchemaVersion(Enum):
    """Supported schema versions"""
    V1_0 = "1.0"


@dataclass
class DirectoryPreference:
    """Preference data for a specific directory"""
    folder_mappings: Dict[str, str]
    naming_patterns: Dict[str, str]
    category_overrides: Dict[str, str]
    created: str
    updated: str
    confidence: float
    correction_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DirectoryPreference':
        """Create from dictionary"""
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        return cls(
            folder_mappings=data.get('folder_mappings', {}),
            naming_patterns=data.get('naming_patterns', {}),
            category_overrides=data.get('category_overrides', {}),
            created=data.get('created', now),
            updated=data.get('updated', now),
            confidence=data.get('confidence', 0.0),
            correction_count=data.get('correction_count', 0)
        )


class PreferenceStore:
    """
    JSON-based preference store with atomic writes and schema validation.

    Features:
    - Atomic file writes using temporary files
    - Schema versioning and validation
    - Backup/restore functionality
    - Error recovery with fallback to defaults
    - Thread-safe operations
    - Migration support for schema updates
    """

    SCHEMA_VERSION = SchemaVersion.V1_0.value
    DEFAULT_FILENAME = "preferences.json"
    BACKUP_EXTENSION = ".backup"

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize preference store.

        Args:
            storage_path: Path to store preferences. If None, uses default location.
        """
        if storage_path is None:
            storage_path = Path.home() / ".file_organizer" / "preferences"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.preference_file = self.storage_path / self.DEFAULT_FILENAME
        self.backup_file = self.storage_path / f"{self.DEFAULT_FILENAME}{self.BACKUP_EXTENSION}"

        # Thread safety
        self._lock = threading.RLock()

        # In-memory cache
        self._preferences: Dict[str, Any] = {}
        self._loaded = False

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format"""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def _create_empty_preferences(self) -> Dict[str, Any]:
        """Create empty preference structure"""
        return {
            "version": self.SCHEMA_VERSION,
            "user_id": "default",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {}
            },
            "directory_preferences": {}
        }

    def _validate_schema(self, data: Dict[str, Any]) -> bool:
        """
        Validate preference schema.

        Args:
            data: Preference data to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check required top-level fields
            required_fields = ["version", "user_id", "global_preferences", "directory_preferences"]
            if not all(field in data for field in required_fields):
                return False

            # Check version compatibility
            if data["version"] not in [v.value for v in SchemaVersion]:
                return False

            # Check global preferences structure
            global_prefs = data["global_preferences"]
            required_global = ["folder_mappings", "naming_patterns", "category_overrides"]
            if not all(field in global_prefs for field in required_global):
                return False

            # Check directory preferences structure
            dir_prefs = data["directory_preferences"]
            if not isinstance(dir_prefs, dict):
                return False

            # Validate each directory preference
            for path, pref in dir_prefs.items():
                if not isinstance(pref, dict):
                    return False
                required_dir_fields = ["folder_mappings", "naming_patterns", "category_overrides",
                                      "created", "updated", "confidence"]
                if not all(field in pref for field in required_dir_fields):
                    return False

            return True

        except (KeyError, TypeError, AttributeError):
            return False

    def _migrate_schema(self, data: Dict[str, Any], from_version: str) -> Dict[str, Any]:
        """
        Migrate preference data from older schema version.

        Args:
            data: Preference data to migrate
            from_version: Source schema version

        Returns:
            Migrated preference data
        """
        # Currently only v1.0 exists, but this provides migration framework
        if from_version == "1.0":
            return data

        # Future migrations would go here
        # Example:
        # if from_version == "1.0" and self.SCHEMA_VERSION == "2.0":
        #     data = self._migrate_v1_to_v2(data)

        return data

    def load_preferences(self) -> bool:
        """
        Load preferences from disk with error recovery.

        Returns:
            True if loaded successfully, False if using defaults
        """
        with self._lock:
            try:
                # Try loading primary file
                if self.preference_file.exists():
                    with open(self.preference_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Validate schema
                    if not self._validate_schema(data):
                        print(f"Warning: Invalid schema in {self.preference_file}, trying backup...")
                        return self._try_load_backup()

                    # Migrate if needed
                    if data["version"] != self.SCHEMA_VERSION:
                        data = self._migrate_schema(data, data["version"])

                    self._preferences = data
                    self._loaded = True
                    return True

                # No primary file, try backup
                if self.backup_file.exists():
                    print(f"Primary file not found, trying backup...")
                    return self._try_load_backup()

                # No files exist, use defaults
                print(f"No preference files found, using defaults...")
                self._preferences = self._create_empty_preferences()
                self._loaded = True
                return False

            except json.JSONDecodeError as e:
                print(f"Error: Corrupted JSON in {self.preference_file}: {e}")
                return self._try_load_backup()

            except Exception as e:
                print(f"Error loading preferences: {e}")
                self._preferences = self._create_empty_preferences()
                self._loaded = True
                return False

    def _try_load_backup(self) -> bool:
        """Try loading from backup file"""
        try:
            if not self.backup_file.exists():
                print("Backup file not found, using defaults...")
                self._preferences = self._create_empty_preferences()
                self._loaded = True
                return False

            with open(self.backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not self._validate_schema(data):
                print("Backup file is also invalid, using defaults...")
                self._preferences = self._create_empty_preferences()
                self._loaded = True
                return False

            print("Successfully loaded from backup")
            self._preferences = data
            self._loaded = True

            # Restore backup to primary
            self.save_preferences()
            return True

        except Exception as e:
            print(f"Error loading backup: {e}, using defaults...")
            self._preferences = self._create_empty_preferences()
            self._loaded = True
            return False

    def save_preferences(self) -> bool:
        """
        Save preferences to disk using atomic writes.

        Returns:
            True if saved successfully, False otherwise
        """
        with self._lock:
            try:
                # Ensure loaded
                if not self._loaded:
                    self.load_preferences()

                # Write to temporary file first (atomic write)
                temp_file = self.storage_path / f"{self.DEFAULT_FILENAME}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self._preferences, f, indent=2, ensure_ascii=False)

                # Create backup of existing file before overwriting
                if self.preference_file.exists():
                    shutil.copy2(self.preference_file, self.backup_file)

                # Atomic rename
                temp_file.replace(self.preference_file)

                # Also create backup after successful write (for recovery)
                shutil.copy2(self.preference_file, self.backup_file)

                return True

            except Exception as e:
                print(f"Error saving preferences: {e}")
                return False

    def add_preference(self, path: Path, preference_data: Dict[str, Any]) -> None:
        """
        Add or update preference for a directory.

        Args:
            path: Directory path
            preference_data: Preference data dictionary
        """
        with self._lock:
            # Ensure loaded
            if not self._loaded:
                self.load_preferences()

            path_str = str(path.resolve())

            # Create or update directory preference
            if path_str in self._preferences["directory_preferences"]:
                # Update existing
                existing = self._preferences["directory_preferences"][path_str]
                existing.update(preference_data)
                existing["updated"] = self._get_current_timestamp()

                # Increment correction count if provided
                if "correction_count" in preference_data:
                    existing["correction_count"] = existing.get("correction_count", 0) + 1
            else:
                # Create new
                dir_pref = DirectoryPreference(
                    folder_mappings=preference_data.get("folder_mappings", {}),
                    naming_patterns=preference_data.get("naming_patterns", {}),
                    category_overrides=preference_data.get("category_overrides", {}),
                    created=self._get_current_timestamp(),
                    updated=self._get_current_timestamp(),
                    confidence=preference_data.get("confidence", 0.5),
                    correction_count=preference_data.get("correction_count", 1)
                )
                self._preferences["directory_preferences"][path_str] = dir_pref.to_dict()

    def get_preference(self, path: Path, fallback_to_parent: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get preference for a directory with optional parent fallback.

        Args:
            path: Directory path
            fallback_to_parent: If True, check parent directories if not found

        Returns:
            Preference data or None if not found
        """
        with self._lock:
            # Ensure loaded
            if not self._loaded:
                self.load_preferences()

            path_str = str(path.resolve())

            # Check exact path
            if path_str in self._preferences["directory_preferences"]:
                return self._preferences["directory_preferences"][path_str].copy()

            # Fallback to parent directories
            if fallback_to_parent:
                current = path.resolve()
                while current.parent != current:  # Stop at root
                    current = current.parent
                    current_str = str(current)
                    if current_str in self._preferences["directory_preferences"]:
                        return self._preferences["directory_preferences"][current_str].copy()

            # Return global preferences as ultimate fallback
            return self._preferences["global_preferences"].copy()

    def update_confidence(self, path: Path, success: bool) -> None:
        """
        Update confidence score for a directory based on success/failure.

        Args:
            path: Directory path
            success: Whether the preference application was successful
        """
        with self._lock:
            # Ensure loaded
            if not self._loaded:
                self.load_preferences()

            path_str = str(path.resolve())

            if path_str in self._preferences["directory_preferences"]:
                pref = self._preferences["directory_preferences"][path_str]
                current_confidence = pref.get("confidence", 0.5)

                # Update confidence using exponential moving average
                # Success increases confidence, failure decreases it
                alpha = 0.1  # Learning rate
                target = 1.0 if success else 0.0
                new_confidence = current_confidence + alpha * (target - current_confidence)

                # Clamp to [0, 1]
                pref["confidence"] = max(0.0, min(1.0, new_confidence))
                pref["updated"] = self._get_current_timestamp()

    def resolve_conflicts(self, preference_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Resolve conflicting preferences using recency and frequency weighting.

        Args:
            preference_list: List of conflicting preference dictionaries

        Returns:
            Resolved preference dictionary
        """
        if not preference_list:
            return {}

        if len(preference_list) == 1:
            return preference_list[0].copy()

        # Score each preference
        scored_prefs = []
        for pref in preference_list:
            score = self._score_preference(pref)
            scored_prefs.append((score, pref))

        # Sort by score (highest first)
        scored_prefs.sort(key=lambda x: x[0], reverse=True)

        # Return highest scored preference
        return scored_prefs[0][1].copy()

    def _score_preference(self, pref: Dict[str, Any]) -> float:
        """
        Calculate score for a preference based on multiple factors.

        Args:
            pref: Preference dictionary

        Returns:
            Score value (higher is better)
        """
        # Factors: confidence, correction count, recency
        confidence = pref.get("confidence", 0.5)
        correction_count = pref.get("correction_count", 0)

        # Recency score (more recent = higher score)
        updated = pref.get("updated", "2000-01-01T00:00:00Z")
        try:
            # Parse ISO format and make timezone aware for comparison
            updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
            # Make now timezone aware as well
            now = datetime.now(timezone.utc)
            days_old = (now - updated_dt).days
            recency_score = 1.0 / (1.0 + days_old / 30.0)  # Decay over 30 days
        except (ValueError, AttributeError):
            recency_score = 0.0

        # Frequency score (more corrections = higher confidence)
        frequency_score = min(1.0, correction_count / 10.0)  # Cap at 10 corrections

        # Combined score (weighted average)
        score = (
            0.4 * confidence +
            0.3 * recency_score +
            0.3 * frequency_score
        )

        return score

    def export_json(self, output_path: Path) -> bool:
        """
        Export preferences to a JSON file.

        Args:
            output_path: Path to export file

        Returns:
            True if exported successfully, False otherwise
        """
        with self._lock:
            try:
                # Ensure loaded
                if not self._loaded:
                    self.load_preferences()

                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(self._preferences, f, indent=2, ensure_ascii=False)

                return True

            except Exception as e:
                print(f"Error exporting preferences: {e}")
                return False

    def import_json(self, input_path: Path) -> bool:
        """
        Import preferences from a JSON file.

        Args:
            input_path: Path to import file

        Returns:
            True if imported successfully, False otherwise
        """
        with self._lock:
            try:
                input_path = Path(input_path)

                if not input_path.exists():
                    print(f"Error: Import file not found: {input_path}")
                    return False

                with open(input_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Validate schema
                if not self._validate_schema(data):
                    print(f"Error: Invalid schema in import file")
                    return False

                # Migrate if needed
                if data["version"] != self.SCHEMA_VERSION:
                    data = self._migrate_schema(data, data["version"])

                # Create backup before importing
                if self.preference_file.exists():
                    backup_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    backup_path = self.storage_path / f"{self.DEFAULT_FILENAME}.{backup_timestamp}.backup"
                    shutil.copy2(self.preference_file, backup_path)

                # Update preferences
                self._preferences = data
                self._loaded = True

                # Save to disk
                return self.save_preferences()

            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in import file: {e}")
                return False

            except Exception as e:
                print(f"Error importing preferences: {e}")
                return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored preferences.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            # Ensure loaded
            if not self._loaded:
                self.load_preferences()

            dir_prefs = self._preferences["directory_preferences"]

            stats = {
                "total_directories": len(dir_prefs),
                "total_corrections": sum(p.get("correction_count", 0) for p in dir_prefs.values()),
                "average_confidence": sum(p.get("confidence", 0) for p in dir_prefs.values()) / len(dir_prefs) if dir_prefs else 0.0,
                "schema_version": self._preferences["version"],
                "user_id": self._preferences["user_id"]
            }

            return stats

    def clear_preferences(self) -> None:
        """Clear all preferences (reset to empty state)"""
        with self._lock:
            self._preferences = self._create_empty_preferences()
            self._loaded = True
            self.save_preferences()

    def list_directory_preferences(self) -> List[Tuple[str, Dict[str, Any]]]:
        """
        List all directory preferences.

        Returns:
            List of (path, preference) tuples
        """
        with self._lock:
            # Ensure loaded
            if not self._loaded:
                self.load_preferences()

            return list(self._preferences["directory_preferences"].items())
