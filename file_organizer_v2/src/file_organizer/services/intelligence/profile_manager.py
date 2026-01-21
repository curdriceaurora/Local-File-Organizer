"""
Profile Management System - Core Module

Provides comprehensive profile management with CRUD operations, activation,
and atomic profile switching capabilities.

Features:
- Create, activate, list, delete profile operations
- Atomic profile switching with rollback support
- Profile validation and sanitization
- Thread-safe operations
- JSON-based profile storage with versioning
"""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class Profile:
    """Represents a user preference profile."""
    profile_name: str
    description: str
    profile_version: str = "1.0"
    created: Optional[str] = None
    updated: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    learned_patterns: Optional[Dict[str, Any]] = None
    confidence_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values after dataclass initialization."""
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        if self.created is None:
            self.created = now
        if self.updated is None:
            self.updated = now
        if self.preferences is None:
            self.preferences = {
                "global": {},
                "directory_specific": {}
            }
        if self.learned_patterns is None:
            self.learned_patterns = {}
        if self.confidence_data is None:
            self.confidence_data = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Profile':
        """Create profile from dictionary."""
        return cls(
            profile_name=data.get('profile_name', 'default'),
            description=data.get('description', ''),
            profile_version=data.get('profile_version', '1.0'),
            created=data.get('created'),
            updated=data.get('updated'),
            preferences=data.get('preferences'),
            learned_patterns=data.get('learned_patterns'),
            confidence_data=data.get('confidence_data')
        )

    def validate(self) -> bool:
        """
        Validate profile structure and data.

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check required fields
            if not self.profile_name or not isinstance(self.profile_name, str):
                return False
            if not self.description or not isinstance(self.description, str):
                return False

            # Validate timestamps
            if self.created:
                datetime.fromisoformat(self.created.replace('Z', '+00:00'))
            if self.updated:
                datetime.fromisoformat(self.updated.replace('Z', '+00:00'))

            # Validate preferences structure
            if not isinstance(self.preferences, dict):
                return False
            if 'global' not in self.preferences or 'directory_specific' not in self.preferences:
                return False

            return True

        except (ValueError, TypeError, AttributeError):
            return False


class ProfileManager:
    """
    Core profile management system with CRUD operations and atomic switching.

    Features:
    - Create and manage multiple preference profiles
    - Atomic profile activation with rollback
    - Profile validation and error recovery
    - Thread-safe operations
    - Profile directory management
    """

    PROFILE_VERSION = "1.0"
    ACTIVE_PROFILE_FILE = "active_profile.txt"
    PROFILE_EXTENSION = ".json"

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize profile manager.

        Args:
            storage_path: Path to store profiles. If None, uses default location.
        """
        if storage_path is None:
            storage_path = Path.home() / ".file_organizer" / "profiles"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.active_profile_file = self.storage_path.parent / self.ACTIVE_PROFILE_FILE

        # Thread safety
        self._lock = threading.RLock()

        # Ensure default profile exists
        self._ensure_default_profile()

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def _sanitize_profile_name(self, name: str) -> str:
        """
        Sanitize profile name to be filesystem-safe.

        Args:
            name: Profile name to sanitize

        Returns:
            Sanitized profile name
        """
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        sanitized = name
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')

        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip('. ')

        # Ensure not empty
        if not sanitized:
            sanitized = "profile"

        return sanitized

    def _get_profile_path(self, profile_name: str) -> Path:
        """Get file path for a profile."""
        sanitized_name = self._sanitize_profile_name(profile_name)
        return self.storage_path / f"{sanitized_name}{self.PROFILE_EXTENSION}"

    def _ensure_default_profile(self) -> None:
        """Ensure default profile exists."""
        default_profile_path = self._get_profile_path("default")

        if not default_profile_path.exists():
            default_profile = Profile(
                profile_name="default",
                description="Default preference profile"
            )
            self._save_profile_to_disk(default_profile)

        # Set as active if no active profile
        if not self.active_profile_file.exists():
            self._set_active_profile_name("default")

    def _save_profile_to_disk(self, profile: Profile) -> bool:
        """
        Save profile to disk using atomic writes.

        Args:
            profile: Profile to save

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            profile_path = self._get_profile_path(profile.profile_name)

            # Write to temporary file first (atomic write)
            temp_file = profile_path.parent / f"{profile_path.name}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_file.replace(profile_path)

            return True

        except Exception as e:
            print(f"Error saving profile to disk: {e}")
            return False

    def _load_profile_from_disk(self, profile_name: str) -> Optional[Profile]:
        """
        Load profile from disk.

        Args:
            profile_name: Name of profile to load

        Returns:
            Profile object or None if not found
        """
        try:
            profile_path = self._get_profile_path(profile_name)

            if not profile_path.exists():
                return None

            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            profile = Profile.from_dict(data)

            if not profile.validate():
                print(f"Warning: Invalid profile structure: {profile_name}")
                return None

            return profile

        except json.JSONDecodeError as e:
            print(f"Error: Corrupted profile file: {profile_name} - {e}")
            return None

        except Exception as e:
            print(f"Error loading profile: {profile_name} - {e}")
            return None

    def _get_active_profile_name(self) -> str:
        """Get name of currently active profile."""
        try:
            if self.active_profile_file.exists():
                with open(self.active_profile_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except Exception as e:
            print(f"Error reading active profile: {e}")

        return "default"

    def _set_active_profile_name(self, profile_name: str) -> bool:
        """
        Set active profile name.

        Args:
            profile_name: Name of profile to activate

        Returns:
            True if set successfully, False otherwise
        """
        try:
            # Write to temporary file first (atomic write)
            temp_file = self.active_profile_file.parent / f"{self.active_profile_file.name}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(profile_name)

            # Atomic rename
            temp_file.replace(self.active_profile_file)

            return True

        except Exception as e:
            print(f"Error setting active profile: {e}")
            return False

    def create_profile(self, name: str, description: str) -> Optional[Profile]:
        """
        Create a new profile.

        Args:
            name: Profile name (must be unique)
            description: Profile description

        Returns:
            Created Profile object or None on failure
        """
        with self._lock:
            # Check if profile already exists
            if self._get_profile_path(name).exists():
                print(f"Error: Profile '{name}' already exists")
                return None

            # Create new profile
            profile = Profile(
                profile_name=name,
                description=description
            )

            # Validate
            if not profile.validate():
                print(f"Error: Invalid profile data")
                return None

            # Save to disk
            if not self._save_profile_to_disk(profile):
                return None

            return profile

    def activate_profile(self, profile_name: str) -> bool:
        """
        Activate a profile (make it the current active profile).

        Args:
            profile_name: Name of profile to activate

        Returns:
            True if activated successfully, False otherwise
        """
        with self._lock:
            # Check if profile exists
            profile = self._load_profile_from_disk(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Get current active profile for rollback
            current_active = self._get_active_profile_name()

            # Set as active
            if not self._set_active_profile_name(profile_name):
                return False

            # Verify activation
            if self._get_active_profile_name() != profile_name:
                print(f"Error: Profile activation verification failed")
                # Rollback
                self._set_active_profile_name(current_active)
                return False

            return True

    def list_profiles(self) -> List[Profile]:
        """
        List all available profiles.

        Returns:
            List of Profile objects
        """
        with self._lock:
            profiles = []

            for profile_file in self.storage_path.glob(f"*{self.PROFILE_EXTENSION}"):
                profile_name = profile_file.stem
                profile = self._load_profile_from_disk(profile_name)
                if profile:
                    profiles.append(profile)

            # Sort by name
            profiles.sort(key=lambda p: p.profile_name)

            return profiles

    def delete_profile(self, profile_name: str, force: bool = False) -> bool:
        """
        Delete a profile.

        Args:
            profile_name: Name of profile to delete
            force: If True, allow deleting active profile (will switch to default)

        Returns:
            True if deleted successfully, False otherwise
        """
        with self._lock:
            # Don't allow deleting default profile
            if profile_name == "default":
                print(f"Error: Cannot delete default profile")
                return False

            # Check if profile exists
            profile_path = self._get_profile_path(profile_name)
            if not profile_path.exists():
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Check if this is the active profile
            active_profile = self._get_active_profile_name()
            if profile_name == active_profile:
                if not force:
                    print(f"Error: Cannot delete active profile. Switch to another profile first or use force=True")
                    return False
                else:
                    # Switch to default before deleting
                    if not self.activate_profile("default"):
                        print(f"Error: Failed to switch to default profile")
                        return False

            # Create backup before deleting
            backup_path = profile_path.parent / f"{profile_path.name}.deleted.backup"
            try:
                shutil.copy2(profile_path, backup_path)
            except Exception as e:
                print(f"Warning: Failed to create backup: {e}")

            # Delete profile file
            try:
                profile_path.unlink()
                return True
            except Exception as e:
                print(f"Error deleting profile: {e}")
                return False

    def get_active_profile(self) -> Optional[Profile]:
        """
        Get currently active profile.

        Returns:
            Active Profile object or None on failure
        """
        with self._lock:
            active_name = self._get_active_profile_name()
            return self._load_profile_from_disk(active_name)

    def update_profile(self, profile_name: str, **updates) -> bool:
        """
        Update profile fields.

        Args:
            profile_name: Name of profile to update
            **updates: Fields to update (description, preferences, etc.)

        Returns:
            True if updated successfully, False otherwise
        """
        with self._lock:
            # Load profile
            profile = self._load_profile_from_disk(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Update fields
            if 'description' in updates:
                profile.description = updates['description']
            if 'preferences' in updates:
                profile.preferences = updates['preferences']
            if 'learned_patterns' in updates:
                profile.learned_patterns = updates['learned_patterns']
            if 'confidence_data' in updates:
                profile.confidence_data = updates['confidence_data']

            # Update timestamp
            profile.updated = self._get_current_timestamp()

            # Validate
            if not profile.validate():
                print(f"Error: Invalid profile data after update")
                return False

            # Save
            return self._save_profile_to_disk(profile)

    def get_profile(self, profile_name: str) -> Optional[Profile]:
        """
        Get a specific profile by name.

        Args:
            profile_name: Name of profile to retrieve

        Returns:
            Profile object or None if not found
        """
        with self._lock:
            return self._load_profile_from_disk(profile_name)

    def profile_exists(self, profile_name: str) -> bool:
        """
        Check if a profile exists.

        Args:
            profile_name: Name of profile to check

        Returns:
            True if profile exists, False otherwise
        """
        return self._get_profile_path(profile_name).exists()

    def get_profile_count(self) -> int:
        """
        Get total number of profiles.

        Returns:
            Count of profiles
        """
        return len(list(self.storage_path.glob(f"*{self.PROFILE_EXTENSION}")))
