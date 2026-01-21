"""
Profile Import Module

Provides comprehensive profile import functionality with validation,
selective import, and preview capabilities.

Features:
- Import profiles from JSON files
- Selective preference import
- Schema validation
- Import preview
- Conflict detection and resolution
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager


@dataclass
class ValidationResult:
    """Result of import validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    profile_data: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        """String representation."""
        lines = [f"Valid: {self.valid}"]
        if self.errors:
            lines.append(f"Errors: {', '.join(self.errors)}")
        if self.warnings:
            lines.append(f"Warnings: {', '.join(self.warnings)}")
        return "\n".join(lines)


class ProfileImporter:
    """
    Profile import system with validation and selective import capabilities.

    Features:
    - Import profiles from JSON files
    - Selective preference import
    - Schema and data validation
    - Import preview before committing
    - Backup existing profiles before overwrite
    - Conflict detection
    """

    def __init__(self, profile_manager: ProfileManager):
        """
        Initialize profile importer.

        Args:
            profile_manager: ProfileManager instance to import into
        """
        self.profile_manager = profile_manager

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def validate_import_file(self, file_path: Path) -> ValidationResult:
        """
        Validate an import file before importing.

        Args:
            file_path: Path to import file

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        profile_data = None

        try:
            file_path = Path(file_path)

            # Check file exists
            if not file_path.exists():
                errors.append(f"File not found: {file_path}")
                return ValidationResult(False, errors, warnings)

            # Check file size (warn if > 10MB)
            file_size = file_path.stat().st_size
            if file_size > 10 * 1024 * 1024:
                warnings.append(f"Large file size: {file_size / (1024*1024):.1f} MB")

            # Load and parse JSON
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON format: {e}")
                return ValidationResult(False, errors, warnings)

            # Check required fields
            required_fields = ['profile_name', 'profile_version']
            missing_fields = [f for f in required_fields if f not in profile_data]
            if missing_fields:
                errors.append(f"Missing required fields: {', '.join(missing_fields)}")

            # Validate profile name
            if 'profile_name' in profile_data:
                name = profile_data['profile_name']
                if not name or not isinstance(name, str):
                    errors.append("Invalid profile name")
                elif len(name) > 100:
                    errors.append("Profile name too long (max 100 characters)")

            # Check version compatibility
            if 'profile_version' in profile_data:
                version = profile_data['profile_version']
                if version not in ['1.0']:
                    warnings.append(f"Unknown profile version: {version} (will attempt migration)")

            # Check export type
            export_type = profile_data.get('export_type', 'full')

            if export_type == 'full':
                # Validate full export structure
                if 'preferences' not in profile_data:
                    errors.append("Missing 'preferences' field for full export")
                else:
                    prefs = profile_data['preferences']
                    if not isinstance(prefs, dict):
                        errors.append("Invalid preferences structure")
                    else:
                        # Check required preference keys
                        if 'global' not in prefs:
                            warnings.append("Missing 'global' preferences")
                        if 'directory_specific' not in prefs:
                            warnings.append("Missing 'directory_specific' preferences")

            elif export_type == 'selective':
                # Validate selective export
                if 'included_preferences' not in profile_data:
                    errors.append("Selective export missing 'included_preferences'")
                if 'preferences' not in profile_data:
                    errors.append("Missing 'preferences' field")

            # Validate timestamps if present
            for timestamp_field in ['created', 'updated', 'exported_at']:
                if timestamp_field in profile_data:
                    try:
                        datetime.fromisoformat(
                            profile_data[timestamp_field].replace('Z', '+00:00')
                        )
                    except (ValueError, AttributeError):
                        warnings.append(f"Invalid timestamp format: {timestamp_field}")

            # Check if profile already exists
            if 'profile_name' in profile_data:
                if self.profile_manager.profile_exists(profile_data['profile_name']):
                    warnings.append(f"Profile '{profile_data['profile_name']}' already exists (will be overwritten)")

            valid = len(errors) == 0
            return ValidationResult(valid, errors, warnings, profile_data)

        except Exception as e:
            errors.append(f"Validation error: {e}")
            return ValidationResult(False, errors, warnings)

    def preview_import(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Preview what would be imported from a file.

        Args:
            file_path: Path to import file

        Returns:
            Dictionary with import preview or None on error
        """
        try:
            # Validate first
            validation = self.validate_import_file(file_path)

            if not validation.valid:
                print(f"Cannot preview invalid import file:")
                print(validation)
                return None

            data = validation.profile_data
            if not data:
                return None

            # Build preview
            preview = {
                'profile_name': data.get('profile_name', 'Unknown'),
                'description': data.get('description', ''),
                'profile_version': data.get('profile_version', 'Unknown'),
                'export_type': data.get('export_type', 'full'),
                'exported_at': data.get('exported_at', 'Unknown'),
                'validation': {
                    'valid': validation.valid,
                    'errors': validation.errors,
                    'warnings': validation.warnings
                }
            }

            # Count preferences
            if 'preferences' in data:
                prefs = data['preferences']
                preview['preferences_count'] = {
                    'global': len(prefs.get('global', {})),
                    'directory_specific': len(prefs.get('directory_specific', {}))
                }

            # Count learned patterns and confidence data
            preview['learned_patterns_count'] = len(data.get('learned_patterns', {}))
            preview['confidence_data_count'] = len(data.get('confidence_data', {}))

            # Check conflicts
            if self.profile_manager.profile_exists(data.get('profile_name', '')):
                preview['conflicts'] = {
                    'existing_profile': True,
                    'message': 'Will overwrite existing profile'
                }

            return preview

        except Exception as e:
            print(f"Error creating import preview: {e}")
            return None

    def import_profile(self, file_path: Path, new_name: Optional[str] = None) -> Optional[Profile]:
        """
        Import a profile from a JSON file.

        Args:
            file_path: Path to import file
            new_name: Optional new name for imported profile (defaults to original name)

        Returns:
            Imported Profile object or None on failure
        """
        try:
            # Validate import file
            validation = self.validate_import_file(file_path)

            if not validation.valid:
                print(f"Cannot import invalid file:")
                print(validation)
                return None

            data = validation.profile_data
            if not data:
                return None

            # Determine profile name
            profile_name = new_name if new_name else data['profile_name']

            # Create backup if profile exists
            if self.profile_manager.profile_exists(profile_name):
                existing_profile = self.profile_manager.get_profile(profile_name)
                if existing_profile:
                    self._backup_profile(existing_profile)

            # Build profile from import data
            export_type = data.get('export_type', 'full')

            if export_type == 'selective':
                # For selective import, need to merge with existing or create new
                return self._import_selective_profile(data, profile_name)
            else:
                # Full import
                profile = Profile(
                    profile_name=profile_name,
                    description=data.get('description', ''),
                    profile_version=data.get('profile_version', '1.0'),
                    created=data.get('created'),
                    updated=self._get_current_timestamp(),
                    preferences=data.get('preferences', {'global': {}, 'directory_specific': {}}),
                    learned_patterns=data.get('learned_patterns', {}),
                    confidence_data=data.get('confidence_data', {})
                )

            # Validate profile
            if not profile.validate():
                print(f"Error: Imported profile failed validation")
                return None

            # Save profile using profile manager
            # If profile exists, update it; otherwise create it
            if self.profile_manager.profile_exists(profile_name):
                success = self.profile_manager.update_profile(
                    profile_name,
                    description=profile.description,
                    preferences=profile.preferences,
                    learned_patterns=profile.learned_patterns,
                    confidence_data=profile.confidence_data
                )
                if not success:
                    return None
            else:
                # Create new profile
                created_profile = self.profile_manager.create_profile(
                    profile_name,
                    profile.description
                )
                if not created_profile:
                    return None

                # Update with imported data
                success = self.profile_manager.update_profile(
                    profile_name,
                    preferences=profile.preferences,
                    learned_patterns=profile.learned_patterns,
                    confidence_data=profile.confidence_data
                )
                if not success:
                    return None

            # Return the imported profile
            return self.profile_manager.get_profile(profile_name)

        except Exception as e:
            print(f"Error importing profile: {e}")
            return None

    def _import_selective_profile(self, data: Dict[str, Any], profile_name: str) -> Optional[Profile]:
        """
        Import selective preferences and merge with existing profile.

        Args:
            data: Import data with selective preferences
            profile_name: Name of profile to import into

        Returns:
            Updated Profile or None on failure
        """
        # Get existing profile or create new one
        existing_profile = self.profile_manager.get_profile(profile_name)

        if not existing_profile:
            # Create new profile
            existing_profile = self.profile_manager.create_profile(
                profile_name,
                data.get('description', '')
            )
            if not existing_profile:
                return None

        # Merge selective preferences
        imported_prefs = data.get('preferences', {})
        current_prefs = existing_profile.preferences

        # Merge global preferences
        if 'global' in imported_prefs:
            current_prefs['global'].update(imported_prefs['global'])

        # Merge directory-specific preferences
        if 'directory_specific' in imported_prefs:
            current_prefs['directory_specific'].update(imported_prefs['directory_specific'])

        # Update learned patterns if included
        if 'learned_patterns' in data:
            existing_profile.learned_patterns.update(data['learned_patterns'])

        # Update confidence data if included
        if 'confidence_data' in data:
            existing_profile.confidence_data.update(data['confidence_data'])

        # Save updated profile
        success = self.profile_manager.update_profile(
            profile_name,
            preferences=current_prefs,
            learned_patterns=existing_profile.learned_patterns,
            confidence_data=existing_profile.confidence_data
        )

        if not success:
            return None

        return self.profile_manager.get_profile(profile_name)

    def _backup_profile(self, profile: Profile) -> None:
        """
        Create backup of a profile before overwriting.

        Args:
            profile: Profile to backup
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"{profile.profile_name}.{timestamp}.backup"

            # Export profile to backup
            from file_organizer.services.intelligence.profile_exporter import ProfileExporter
            exporter = ProfileExporter(self.profile_manager)

            backup_dir = self.profile_manager.storage_path / "backups"
            backup_dir.mkdir(exist_ok=True)

            backup_path = backup_dir / f"{backup_name}.json"
            exporter.export_profile(profile.profile_name, backup_path)

            print(f"Created backup: {backup_path}")

        except Exception as e:
            print(f"Warning: Failed to create backup: {e}")

    def import_selective(
        self,
        file_path: Path,
        preferences_list: List[str],
        target_profile: Optional[str] = None
    ) -> Optional[Profile]:
        """
        Import only selected preferences from a file.

        Args:
            file_path: Path to import file
            preferences_list: List of preference types to import
            target_profile: Target profile name (defaults to imported profile name)

        Returns:
            Updated Profile or None on failure
        """
        try:
            # Validate and load import file
            validation = self.validate_import_file(file_path)

            if not validation.valid:
                print(f"Cannot import from invalid file:")
                print(validation)
                return None

            data = validation.profile_data
            if not data:
                return None

            # Filter import data to only include selected preferences
            filtered_data = {
                'profile_name': target_profile if target_profile else data['profile_name'],
                'description': data.get('description', ''),
                'profile_version': data.get('profile_version', '1.0'),
                'export_type': 'selective',
                'included_preferences': preferences_list,
                'preferences': {}
            }

            # Extract selected preferences
            source_prefs = data.get('preferences', {})

            for pref_type in preferences_list:
                if pref_type in ['global', 'directory_specific']:
                    if pref_type in source_prefs:
                        filtered_data['preferences'][pref_type] = source_prefs[pref_type]
                elif pref_type == 'learned_patterns' and 'learned_patterns' in data:
                    filtered_data['learned_patterns'] = data['learned_patterns']
                elif pref_type == 'confidence_data' and 'confidence_data' in data:
                    filtered_data['confidence_data'] = data['confidence_data']

            # Import filtered data
            return self._import_selective_profile(
                filtered_data,
                filtered_data['profile_name']
            )

        except Exception as e:
            print(f"Error importing selective preferences: {e}")
            return None
