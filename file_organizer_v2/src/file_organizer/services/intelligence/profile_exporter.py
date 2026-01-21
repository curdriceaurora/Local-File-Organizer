"""
Profile Export Module

Provides comprehensive profile export functionality with validation,
selective export, and optional compression.

Features:
- Full profile export to JSON
- Selective preference export
- Export validation
- Pretty-printed JSON output
- Error handling and recovery
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager


class ProfileExporter:
    """
    Profile export system with validation and selective export capabilities.

    Features:
    - Export full profile to JSON file
    - Export selective preferences
    - Validate export data before writing
    - Pretty-printed output for human readability
    - Atomic file writes
    """

    def __init__(self, profile_manager: ProfileManager):
        """
        Initialize profile exporter.

        Args:
            profile_manager: ProfileManager instance to export from
        """
        self.profile_manager = profile_manager

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def export_profile(self, profile_name: str, file_path: Path) -> bool:
        """
        Export a complete profile to JSON file.

        Args:
            profile_name: Name of profile to export
            file_path: Path where to save the export

        Returns:
            True if exported successfully, False otherwise
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Validate profile before export
            if not profile.validate():
                print(f"Error: Profile '{profile_name}' failed validation")
                return False

            # Prepare export data
            export_data = profile.to_dict()
            export_data['exported_at'] = self._get_current_timestamp()
            export_data['export_version'] = '1.0'

            # Create parent directory if needed
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first (atomic write)
            temp_file = file_path.parent / f"{file_path.name}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            # Validate export file
            if not self.validate_export(temp_file):
                print(f"Error: Export file validation failed")
                temp_file.unlink()
                return False

            # Atomic rename
            temp_file.replace(file_path)

            return True

        except Exception as e:
            print(f"Error exporting profile: {e}")
            return False

    def export_selective(
        self,
        profile_name: str,
        file_path: Path,
        preferences_list: List[str]
    ) -> bool:
        """
        Export selected preferences from a profile.

        Args:
            profile_name: Name of profile to export from
            file_path: Path where to save the export
            preferences_list: List of preference types to export
                             (e.g., ['global', 'naming', 'folders'])

        Returns:
            True if exported successfully, False otherwise
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return False

            # Build selective export data
            export_data = {
                'profile_name': profile.profile_name,
                'description': f"Selective export: {', '.join(preferences_list)}",
                'profile_version': profile.profile_version,
                'exported_at': self._get_current_timestamp(),
                'export_version': '1.0',
                'export_type': 'selective',
                'included_preferences': preferences_list
            }

            # Include requested preferences
            preferences = {}

            for pref_type in preferences_list:
                if pref_type == 'global':
                    preferences['global'] = profile.preferences.get('global', {})
                elif pref_type == 'directory_specific':
                    preferences['directory_specific'] = profile.preferences.get('directory_specific', {})
                elif pref_type == 'naming':
                    # Extract naming-related preferences
                    global_prefs = profile.preferences.get('global', {})
                    preferences['global'] = preferences.get('global', {})
                    preferences['global']['naming_patterns'] = global_prefs.get('naming_patterns', {})
                elif pref_type == 'folders':
                    # Extract folder-related preferences
                    global_prefs = profile.preferences.get('global', {})
                    preferences['global'] = preferences.get('global', {})
                    preferences['global']['folder_mappings'] = global_prefs.get('folder_mappings', {})
                elif pref_type == 'learned_patterns':
                    export_data['learned_patterns'] = profile.learned_patterns
                elif pref_type == 'confidence_data':
                    export_data['confidence_data'] = profile.confidence_data

            export_data['preferences'] = preferences

            # Create parent directory if needed
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first (atomic write)
            temp_file = file_path.parent / f"{file_path.name}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_file.replace(file_path)

            return True

        except Exception as e:
            print(f"Error exporting selective preferences: {e}")
            return False

    def validate_export(self, file_path: Path) -> bool:
        """
        Validate an exported profile file.

        Args:
            file_path: Path to export file to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                print(f"Error: Export file not found: {file_path}")
                return False

            # Load and parse JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check required fields
            required_fields = ['profile_name', 'profile_version', 'exported_at']
            if not all(field in data for field in required_fields):
                print(f"Error: Missing required fields in export file")
                return False

            # Check export type
            export_type = data.get('export_type', 'full')

            if export_type == 'full':
                # Validate full export structure
                if 'preferences' not in data:
                    print(f"Error: Full export missing preferences")
                    return False

                prefs = data['preferences']
                if not isinstance(prefs, dict):
                    print(f"Error: Invalid preferences structure")
                    return False

                # Check preferences have required keys
                if 'global' not in prefs or 'directory_specific' not in prefs:
                    print(f"Error: Invalid preferences structure")
                    return False

            elif export_type == 'selective':
                # Validate selective export
                if 'included_preferences' not in data:
                    print(f"Error: Selective export missing included_preferences")
                    return False

            # Validate timestamps
            try:
                datetime.fromisoformat(data['exported_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                print(f"Error: Invalid timestamp format")
                return False

            return True

        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in export file: {e}")
            return False

        except Exception as e:
            print(f"Error validating export: {e}")
            return False

    def preview_export(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """
        Preview what would be exported for a profile.

        Args:
            profile_name: Name of profile to preview

        Returns:
            Dictionary with export preview or None on error
        """
        try:
            # Load profile
            profile = self.profile_manager.get_profile(profile_name)
            if profile is None:
                print(f"Error: Profile '{profile_name}' not found")
                return None

            # Calculate export statistics
            preview = {
                'profile_name': profile.profile_name,
                'description': profile.description,
                'created': profile.created,
                'updated': profile.updated,
                'statistics': {
                    'global_preferences_count': len(profile.preferences.get('global', {})),
                    'directory_specific_count': len(profile.preferences.get('directory_specific', {})),
                    'learned_patterns_count': len(profile.learned_patterns),
                    'confidence_data_count': len(profile.confidence_data)
                },
                'export_size_estimate': self._estimate_export_size(profile)
            }

            return preview

        except Exception as e:
            print(f"Error creating export preview: {e}")
            return None

    def _estimate_export_size(self, profile: Profile) -> str:
        """
        Estimate export file size.

        Args:
            profile: Profile to estimate size for

        Returns:
            Size estimate as string (e.g., "2.5 KB")
        """
        try:
            # Serialize to JSON to get size
            json_data = json.dumps(profile.to_dict(), indent=2)
            size_bytes = len(json_data.encode('utf-8'))

            # Format size
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"

        except Exception:
            return "Unknown"

    def export_multiple(
        self,
        profile_names: List[str],
        output_dir: Path
    ) -> Dict[str, bool]:
        """
        Export multiple profiles to a directory.

        Args:
            profile_names: List of profile names to export
            output_dir: Directory where to save exports

        Returns:
            Dictionary mapping profile names to export success status
        """
        results = {}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for profile_name in profile_names:
            output_file = output_dir / f"{profile_name}.json"
            success = self.export_profile(profile_name, output_file)
            results[profile_name] = success

        return results
