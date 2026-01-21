"""
Profile Migration Module

Provides profile version migration with backup and rollback capabilities.

Features:
- Migrate profiles between versions
- Automatic backup before migration
- Rollback on migration failure
- Schema transformation
- Data integrity validation
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any, Callable

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager


class ProfileMigrator:
    """
    Profile migration system with backup and rollback support.

    Features:
    - Migrate profiles from older versions to current
    - Automatic backup before migration
    - Rollback capability on failure
    - Schema transformation and validation
    - Migration path discovery
    """

    SUPPORTED_VERSIONS = ['1.0']
    CURRENT_VERSION = '1.0'

    def __init__(self, profile_manager: ProfileManager):
        """
        Initialize profile migrator.

        Args:
            profile_manager: ProfileManager instance
        """
        self.profile_manager = profile_manager
        self._migration_functions: Dict[str, Callable] = {
            # Future migrations will be registered here
            # e.g., '1.0->2.0': self._migrate_v1_to_v2
        }

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def migrate_version(
        self,
        profile_name: str,
        target_version: str,
        backup: bool = True
    ) -> bool:
        """
        Migrate a profile to a target version.

        Args:
            profile_name: Name of profile to migrate
            target_version: Target version to migrate to
            backup: If True, create backup before migration

        Returns:
            True if migrated successfully, False otherwise
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            current_version = profile.profile_version

            # Check if migration needed
            if current_version == target_version:
                print(f"Profile already at version {target_version}")
                return True

            # Check if target version is supported
            if target_version not in self.SUPPORTED_VERSIONS:
                print(f"Error: Unsupported target version: {target_version}")
                return False

            # Create backup if requested
            backup_path = None
            if backup:
                backup_path = self.backup_before_migration(profile)
                if backup_path is None:
                    print(f"Error: Failed to create backup")
                    return False

            # Find and execute migration path
            migration_path = self._find_migration_path(current_version, target_version)
            if migration_path is None:
                print(f"Error: No migration path from {current_version} to {target_version}")
                return False

            # Execute migration steps
            migrated_data = profile.to_dict()

            for step in migration_path:
                migration_func = self._migration_functions.get(step)
                if migration_func is None:
                    print(f"Error: Migration function not found for step: {step}")
                    if backup_path:
                        self.rollback_migration(profile_name, backup_path)
                    return False

                try:
                    migrated_data = migration_func(migrated_data)
                except Exception as e:
                    print(f"Error during migration step {step}: {e}")
                    if backup_path:
                        self.rollback_migration(profile_name, backup_path)
                    return False

            # Update profile with migrated data
            migrated_data['profile_version'] = target_version
            migrated_data['updated'] = self._get_current_timestamp()
            migrated_data['migration_history'] = migrated_data.get('migration_history', [])
            migrated_data['migration_history'].append({
                'from_version': current_version,
                'to_version': target_version,
                'migrated_at': self._get_current_timestamp()
            })

            # Validate migrated profile
            migrated_profile = Profile.from_dict(migrated_data)
            if not migrated_profile.validate():
                print(f"Error: Migrated profile failed validation")
                if backup_path:
                    self.rollback_migration(profile_name, backup_path)
                return False

            # Save migrated profile
            success = self.profile_manager.update_profile(
                profile_name,
                description=migrated_profile.description,
                preferences=migrated_profile.preferences,
                learned_patterns=migrated_profile.learned_patterns,
                confidence_data=migrated_profile.confidence_data
            )

            if not success:
                print(f"Error: Failed to save migrated profile")
                if backup_path:
                    self.rollback_migration(profile_name, backup_path)
                return False

            print(f"Successfully migrated profile from {current_version} to {target_version}")
            return True

        except Exception as e:
            print(f"Error migrating profile: {e}")
            return False

    def _find_migration_path(
        self,
        from_version: str,
        to_version: str
    ) -> Optional[list]:
        """
        Find migration path between versions.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            List of migration steps or None if no path exists
        """
        # Currently only v1.0 exists, so no migration paths yet
        # Future implementation would use graph traversal to find path

        if from_version == to_version:
            return []

        # Example for future versions:
        # if from_version == '1.0' and to_version == '2.0':
        #     return ['1.0->2.0']
        # if from_version == '1.0' and to_version == '3.0':
        #     return ['1.0->2.0', '2.0->3.0']

        return None  # No migration path available yet

    def backup_before_migration(self, profile: Profile) -> Optional[Path]:
        """
        Create backup of profile before migration.

        Args:
            profile: Profile to backup

        Returns:
            Path to backup file or None on failure
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"{profile.profile_name}.{timestamp}.migration_backup"

            backup_dir = self.profile_manager.storage_path / "migration_backups"
            backup_dir.mkdir(exist_ok=True)

            backup_path = backup_dir / f"{backup_name}.json"

            # Write backup
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)

            print(f"Created migration backup: {backup_path}")
            return backup_path

        except Exception as e:
            print(f"Error creating migration backup: {e}")
            return None

    def rollback_migration(self, profile_name: str, backup_path: Path) -> bool:
        """
        Rollback a failed migration using backup.

        Args:
            profile_name: Name of profile to rollback
            backup_path: Path to backup file

        Returns:
            True if rolled back successfully, False otherwise
        """
        try:
            print(f"Rolling back migration for profile '{profile_name}'...")

            backup_path = Path(backup_path)

            if not backup_path.exists():
                print(f"Error: Backup file not found: {backup_path}")
                return False

            # Load backup data
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            # Restore profile
            restored_profile = Profile.from_dict(backup_data)

            if not restored_profile.validate():
                print(f"Error: Backup data is invalid")
                return False

            # Save restored profile
            success = self.profile_manager.update_profile(
                profile_name,
                description=restored_profile.description,
                preferences=restored_profile.preferences,
                learned_patterns=restored_profile.learned_patterns,
                confidence_data=restored_profile.confidence_data
            )

            if success:
                print(f"Successfully rolled back migration")
            else:
                print(f"Error: Failed to save rolled back profile")

            return success

        except Exception as e:
            print(f"Error rolling back migration: {e}")
            return False

    def validate_migration(self, profile_name: str) -> bool:
        """
        Validate that a profile is properly migrated and functional.

        Args:
            profile_name: Name of profile to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Validate profile structure
            if not profile.validate():
                print(f"Error: Profile validation failed")
                return False

            # Check version is supported
            if profile.profile_version not in self.SUPPORTED_VERSIONS:
                print(f"Error: Unsupported profile version: {profile.profile_version}")
                return False

            # Additional validation checks
            # Check preferences structure
            if not isinstance(profile.preferences, dict):
                print(f"Error: Invalid preferences structure")
                return False

            if 'global' not in profile.preferences or 'directory_specific' not in profile.preferences:
                print(f"Error: Missing required preference keys")
                return False

            print(f"Profile validation successful")
            return True

        except Exception as e:
            print(f"Error validating migration: {e}")
            return False

    def get_migration_history(self, profile_name: str) -> Optional[list]:
        """
        Get migration history for a profile.

        Args:
            profile_name: Name of profile

        Returns:
            List of migration records or None on error
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                return None

            # Get migration history from profile data
            profile_dict = profile.to_dict()
            return profile_dict.get('migration_history', [])

        except Exception as e:
            print(f"Error getting migration history: {e}")
            return None

    def list_backups(self, profile_name: Optional[str] = None) -> list:
        """
        List available migration backups.

        Args:
            profile_name: Optional profile name to filter by

        Returns:
            List of backup file paths
        """
        try:
            backup_dir = self.profile_manager.storage_path / "migration_backups"

            if not backup_dir.exists():
                return []

            backups = []

            for backup_file in backup_dir.glob("*.json"):
                if profile_name is None or backup_file.name.startswith(profile_name):
                    backups.append(backup_file)

            # Sort by modification time (newest first)
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            return backups

        except Exception as e:
            print(f"Error listing backups: {e}")
            return []

    # Migration functions for future versions

    def _migrate_v1_to_v2(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate profile from version 1.0 to 2.0.

        This is a placeholder for future migration.

        Args:
            data: Profile data at version 1.0

        Returns:
            Migrated profile data at version 2.0
        """
        # Future implementation
        # Example transformations:
        # - Restructure preferences
        # - Add new required fields
        # - Transform data formats
        pass

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        migration_func: Callable
    ) -> None:
        """
        Register a custom migration function.

        Args:
            from_version: Source version
            to_version: Target version
            migration_func: Function to perform migration
        """
        key = f"{from_version}->{to_version}"
        self._migration_functions[key] = migration_func
        print(f"Registered migration: {key}")
