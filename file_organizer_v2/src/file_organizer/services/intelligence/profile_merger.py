"""
Profile Merger Module

Provides profile merging capabilities with conflict resolution strategies.

Features:
- Merge multiple profiles into one
- Multiple merge strategies (recent, frequent, confident)
- Conflict detection and resolution
- Preserve high-confidence preferences
- Validation of merged results
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager


class MergeStrategy(Enum):
    """Strategies for resolving conflicts during merge."""
    RECENT = "recent"  # Prefer most recently updated
    FREQUENT = "frequent"  # Prefer most frequently used
    CONFIDENT = "confident"  # Prefer highest confidence
    FIRST = "first"  # Keep first profile's value
    LAST = "last"  # Keep last profile's value


class ProfileMerger:
    """
    Profile merging system with conflict resolution.

    Features:
    - Merge multiple profiles into a single profile
    - Configurable merge strategies
    - Conflict detection and resolution
    - Preserve high-confidence data
    - Validation of merged results
    """

    def __init__(self, profile_manager: ProfileManager):
        """
        Initialize profile merger.

        Args:
            profile_manager: ProfileManager instance
        """
        self.profile_manager = profile_manager

    def _get_current_timestamp(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def merge_profiles(
        self,
        profile_list: List[str],
        merge_strategy: str = "confident",
        output_name: Optional[str] = None
    ) -> Optional[Profile]:
        """
        Merge multiple profiles into a single profile.

        Args:
            profile_list: List of profile names to merge
            merge_strategy: Strategy for conflict resolution
            output_name: Name for merged profile (defaults to "merged_profile")

        Returns:
            Merged Profile object or None on failure
        """
        try:
            if len(profile_list) < 2:
                print("Error: Need at least 2 profiles to merge")
                return None

            # Validate strategy
            try:
                strategy = MergeStrategy(merge_strategy.lower())
            except ValueError:
                print(f"Error: Invalid merge strategy: {merge_strategy}")
                print(f"Valid strategies: {', '.join(s.value for s in MergeStrategy)}")
                return None

            # Load all profiles
            profiles = []
            for profile_name in profile_list:
                profile = self.profile_manager.get_profile(profile_name)
                if profile is None:
                    print(f"Error: Profile '{profile_name}' not found")
                    return None
                profiles.append(profile)

            # Determine output name
            if output_name is None:
                output_name = "merged_profile"

            # Merge preferences
            merged_preferences = self._merge_preferences(profiles, strategy)

            # Merge learned patterns
            merged_patterns = self._merge_learned_patterns(profiles, strategy)

            # Merge confidence data
            merged_confidence = self._merge_confidence_data(profiles, strategy)

            # Create merged profile
            merged_description = f"Merged from: {', '.join(profile_list)}"

            # Create profile
            merged_profile = self.profile_manager.create_profile(
                output_name,
                merged_description
            )

            if merged_profile is None:
                # Profile might already exist, try updating
                success = self.profile_manager.update_profile(
                    output_name,
                    description=merged_description,
                    preferences=merged_preferences,
                    learned_patterns=merged_patterns,
                    confidence_data=merged_confidence
                )
                if not success:
                    return None
                merged_profile = self.profile_manager.get_profile(output_name)
            else:
                # Update with merged data
                success = self.profile_manager.update_profile(
                    output_name,
                    preferences=merged_preferences,
                    learned_patterns=merged_patterns,
                    confidence_data=merged_confidence
                )
                if not success:
                    return None
                merged_profile = self.profile_manager.get_profile(output_name)

            return merged_profile

        except Exception as e:
            print(f"Error merging profiles: {e}")
            return None

    def _merge_preferences(
        self,
        profiles: List[Profile],
        strategy: MergeStrategy
    ) -> Dict[str, Any]:
        """
        Merge preferences from multiple profiles.

        Args:
            profiles: List of Profile objects
            strategy: Merge strategy to use

        Returns:
            Merged preferences dictionary
        """
        merged = {
            'global': {},
            'directory_specific': {}
        }

        # Merge global preferences
        all_global_keys = set()
        for profile in profiles:
            all_global_keys.update(profile.preferences.get('global', {}).keys())

        for key in all_global_keys:
            values = []
            for profile in profiles:
                if key in profile.preferences.get('global', {}):
                    values.append({
                        'value': profile.preferences['global'][key],
                        'profile': profile,
                        'metadata': {
                            'updated': profile.updated,
                            'confidence': profile.confidence_data.get(key, 0.5)
                        }
                    })

            if values:
                resolved_value = self.resolve_conflicts(values, strategy)
                merged['global'][key] = resolved_value

        # Merge directory-specific preferences
        all_dir_keys = set()
        for profile in profiles:
            all_dir_keys.update(profile.preferences.get('directory_specific', {}).keys())

        for dir_key in all_dir_keys:
            values = []
            for profile in profiles:
                if dir_key in profile.preferences.get('directory_specific', {}):
                    values.append({
                        'value': profile.preferences['directory_specific'][dir_key],
                        'profile': profile,
                        'metadata': {
                            'updated': profile.updated,
                            'confidence': profile.confidence_data.get(dir_key, 0.5)
                        }
                    })

            if values:
                resolved_value = self.resolve_conflicts(values, strategy)
                merged['directory_specific'][dir_key] = resolved_value

        return merged

    def _merge_learned_patterns(
        self,
        profiles: List[Profile],
        strategy: MergeStrategy
    ) -> Dict[str, Any]:
        """
        Merge learned patterns from multiple profiles.

        Args:
            profiles: List of Profile objects
            strategy: Merge strategy to use

        Returns:
            Merged learned patterns dictionary
        """
        merged = {}

        # Collect all pattern keys
        all_pattern_keys = set()
        for profile in profiles:
            all_pattern_keys.update(profile.learned_patterns.keys())

        for key in all_pattern_keys:
            values = []
            for profile in profiles:
                if key in profile.learned_patterns:
                    values.append({
                        'value': profile.learned_patterns[key],
                        'profile': profile,
                        'metadata': {
                            'updated': profile.updated,
                            'confidence': profile.confidence_data.get(key, 0.5)
                        }
                    })

            if values:
                resolved_value = self.resolve_conflicts(values, strategy)
                merged[key] = resolved_value

        return merged

    def _merge_confidence_data(
        self,
        profiles: List[Profile],
        strategy: MergeStrategy
    ) -> Dict[str, Any]:
        """
        Merge confidence data from multiple profiles.

        Args:
            profiles: List of Profile objects
            strategy: Merge strategy to use

        Returns:
            Merged confidence data dictionary
        """
        merged = {}

        # Collect all confidence keys
        all_conf_keys = set()
        for profile in profiles:
            all_conf_keys.update(profile.confidence_data.keys())

        for key in all_conf_keys:
            # For confidence scores, we can use different strategies
            confidence_values = []
            for profile in profiles:
                if key in profile.confidence_data:
                    confidence_values.append(profile.confidence_data[key])

            if confidence_values:
                if strategy == MergeStrategy.CONFIDENT:
                    # Use highest confidence
                    merged[key] = max(confidence_values)
                elif strategy == MergeStrategy.RECENT:
                    # Use last (most recent) confidence
                    merged[key] = confidence_values[-1]
                else:
                    # Use average confidence
                    merged[key] = sum(confidence_values) / len(confidence_values)

        return merged

    def resolve_conflicts(
        self,
        conflicting_prefs: List[Dict[str, Any]],
        strategy: MergeStrategy
    ) -> Any:
        """
        Resolve conflicts between preferences using specified strategy.

        Args:
            conflicting_prefs: List of conflicting preference values with metadata
            strategy: Strategy to use for resolution

        Returns:
            Resolved preference value
        """
        if not conflicting_prefs:
            return None

        if len(conflicting_prefs) == 1:
            return conflicting_prefs[0]['value']

        if strategy == MergeStrategy.RECENT:
            # Prefer most recently updated
            sorted_prefs = sorted(
                conflicting_prefs,
                key=lambda p: p['metadata'].get('updated', ''),
                reverse=True
            )
            return sorted_prefs[0]['value']

        elif strategy == MergeStrategy.CONFIDENT:
            # Prefer highest confidence
            sorted_prefs = sorted(
                conflicting_prefs,
                key=lambda p: p['metadata'].get('confidence', 0.0),
                reverse=True
            )
            return sorted_prefs[0]['value']

        elif strategy == MergeStrategy.FIRST:
            # Keep first
            return conflicting_prefs[0]['value']

        elif strategy == MergeStrategy.LAST:
            # Keep last
            return conflicting_prefs[-1]['value']

        elif strategy == MergeStrategy.FREQUENT:
            # Count frequency of each value and pick most common
            value_counts = {}
            for pref in conflicting_prefs:
                value_str = str(pref['value'])
                value_counts[value_str] = value_counts.get(value_str, 0) + 1

            most_frequent = max(value_counts.items(), key=lambda x: x[1])
            # Find first preference with this value
            for pref in conflicting_prefs:
                if str(pref['value']) == most_frequent[0]:
                    return pref['value']

        # Default: return first value
        return conflicting_prefs[0]['value']

    def preserve_high_confidence(
        self,
        merged_profile: Profile,
        source_profiles: List[Profile],
        confidence_threshold: float = 0.8
    ) -> None:
        """
        Ensure high-confidence preferences from source profiles are preserved.

        Args:
            merged_profile: The merged profile to update
            source_profiles: List of source profiles
            confidence_threshold: Minimum confidence to preserve (default 0.8)
        """
        # Collect high-confidence preferences from all sources
        high_confidence_prefs = {}

        for source in source_profiles:
            for key, confidence in source.confidence_data.items():
                if confidence >= confidence_threshold:
                    if key not in high_confidence_prefs or \
                       confidence > high_confidence_prefs[key]['confidence']:
                        high_confidence_prefs[key] = {
                            'confidence': confidence,
                            'profile': source
                        }

        # Update merged profile with high-confidence preferences
        for key, data in high_confidence_prefs.items():
            source = data['profile']

            # Check if it's in global preferences
            if key in source.preferences.get('global', {}):
                merged_profile.preferences['global'][key] = source.preferences['global'][key]
                merged_profile.confidence_data[key] = data['confidence']

            # Check if it's in directory-specific preferences
            elif key in source.preferences.get('directory_specific', {}):
                merged_profile.preferences['directory_specific'][key] = \
                    source.preferences['directory_specific'][key]
                merged_profile.confidence_data[key] = data['confidence']

            # Check if it's a learned pattern
            elif key in source.learned_patterns:
                merged_profile.learned_patterns[key] = source.learned_patterns[key]
                merged_profile.confidence_data[key] = data['confidence']

    def create_merged_profile(
        self,
        name: str,
        merged_data: Dict[str, Any]
    ) -> Optional[Profile]:
        """
        Create a new profile from merged data.

        Args:
            name: Name for the merged profile
            merged_data: Dictionary containing merged preferences and data

        Returns:
            Created Profile object or None on failure
        """
        try:
            # Create profile
            profile = self.profile_manager.create_profile(
                name,
                merged_data.get('description', 'Merged profile')
            )

            if profile is None:
                return None

            # Update with merged data
            success = self.profile_manager.update_profile(
                name,
                preferences=merged_data.get('preferences', {}),
                learned_patterns=merged_data.get('learned_patterns', {}),
                confidence_data=merged_data.get('confidence_data', {})
            )

            if not success:
                return None

            return self.profile_manager.get_profile(name)

        except Exception as e:
            print(f"Error creating merged profile: {e}")
            return None

    def get_merge_conflicts(
        self,
        profile_list: List[str]
    ) -> Dict[str, List[Any]]:
        """
        Identify conflicts between profiles before merging.

        Args:
            profile_list: List of profile names to check

        Returns:
            Dictionary mapping keys to conflicting values
        """
        conflicts = {}

        try:
            # Load all profiles
            profiles = []
            for profile_name in profile_list:
                profile = self.profile_manager.get_profile(profile_name)
                if profile:
                    profiles.append(profile)

            if len(profiles) < 2:
                return conflicts

            # Check global preferences
            all_global_keys = set()
            for profile in profiles:
                all_global_keys.update(profile.preferences.get('global', {}).keys())

            for key in all_global_keys:
                values = []
                for profile in profiles:
                    if key in profile.preferences.get('global', {}):
                        value = profile.preferences['global'][key]
                        if value not in values:
                            values.append(value)

                if len(values) > 1:
                    conflicts[f"global.{key}"] = values

            # Check directory-specific preferences
            all_dir_keys = set()
            for profile in profiles:
                all_dir_keys.update(profile.preferences.get('directory_specific', {}).keys())

            for key in all_dir_keys:
                values = []
                for profile in profiles:
                    if key in profile.preferences.get('directory_specific', {}):
                        value = profile.preferences['directory_specific'][key]
                        if value not in values:
                            values.append(value)

                if len(values) > 1:
                    conflicts[f"directory_specific.{key}"] = values

            return conflicts

        except Exception as e:
            print(f"Error detecting conflicts: {e}")
            return conflicts
