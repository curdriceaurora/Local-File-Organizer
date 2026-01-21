"""
Folder preference learning module.

Learns user folder preferences based on file type, naming patterns, and user corrections.
Maps file types to preferred folders and detects organization workflows.
"""

from pathlib import Path
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class FolderPreferenceLearner:
    """
    Learns and tracks user folder preferences for file organization.

    Tracks:
    - File type to folder mappings
    - Workflow-based organization patterns
    - Project structure adaptations
    - Context-aware folder suggestions
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the folder preference learner.

        Args:
            storage_path: Path to store learned preferences (default: ~/.file_organizer/folder_prefs.json)
        """
        if storage_path is None:
            storage_path = Path.home() / ".file_organizer" / "folder_prefs.json"

        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Structure: {file_type: {folder: count}}
        self.type_folder_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Structure: {pattern: {folder: count}}
        self.pattern_folder_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Structure: {folder: {metadata}}
        self.folder_metadata: Dict[str, Dict] = {}

        # Total choices tracked
        self.total_choices: int = 0

        self._load_preferences()

    def track_folder_choice(
        self,
        file_type: str,
        folder: Path,
        context: Optional[Dict] = None
    ) -> None:
        """
        Track a user's folder choice for a file type.

        Args:
            file_type: File extension (e.g., 'pdf', 'jpg')
            folder: Chosen folder path
            context: Optional context (filename pattern, project, etc.)
        """
        folder_str = str(folder.resolve())

        # Track type -> folder mapping
        self.type_folder_map[file_type.lower()][folder_str] += 1

        # Track pattern-based mapping if context provided
        if context and 'pattern' in context:
            pattern = context['pattern']
            self.pattern_folder_map[pattern][folder_str] += 1

        # Update folder metadata
        if folder_str not in self.folder_metadata:
            self.folder_metadata[folder_str] = {
                'created': datetime.utcnow().isoformat(),
                'file_types': set(),
                'last_used': None,
                'usage_count': 0
            }

        self.folder_metadata[folder_str]['file_types'].add(file_type.lower())
        self.folder_metadata[folder_str]['last_used'] = datetime.utcnow().isoformat()
        self.folder_metadata[folder_str]['usage_count'] += 1

        self.total_choices += 1

        # Persist changes
        self._save_preferences()

        logger.info(f"Tracked folder choice: {file_type} -> {folder_str}")

    def get_preferred_folder(
        self,
        file_type: str,
        confidence_threshold: float = 0.6
    ) -> Optional[Path]:
        """
        Get the preferred folder for a file type.

        Args:
            file_type: File extension
            confidence_threshold: Minimum confidence required (0-1)

        Returns:
            Preferred folder path if confidence meets threshold, None otherwise
        """
        file_type = file_type.lower()

        if file_type not in self.type_folder_map:
            return None

        folder_counts = self.type_folder_map[file_type]
        if not folder_counts:
            return None

        # Find folder with highest count
        total_for_type = sum(folder_counts.values())
        best_folder = max(folder_counts.items(), key=lambda x: x[1])

        confidence = best_folder[1] / total_for_type

        if confidence >= confidence_threshold:
            logger.info(f"Preferred folder for {file_type}: {best_folder[0]} (confidence: {confidence:.2f})")
            return Path(best_folder[0])

        logger.debug(f"No confident preference for {file_type} (confidence: {confidence:.2f} < {confidence_threshold})")
        return None

    def get_folder_confidence(self, file_type: str, folder: Path) -> float:
        """
        Get confidence score for a specific file type -> folder mapping.

        Args:
            file_type: File extension
            folder: Folder path

        Returns:
            Confidence score (0-1)
        """
        file_type = file_type.lower()
        folder_str = str(folder.resolve())

        if file_type not in self.type_folder_map:
            return 0.0

        folder_counts = self.type_folder_map[file_type]
        total_for_type = sum(folder_counts.values())

        if total_for_type == 0:
            return 0.0

        return folder_counts.get(folder_str, 0) / total_for_type

    def analyze_organization_patterns(self) -> Dict:
        """
        Analyze overall organization patterns.

        Returns:
            Dictionary with pattern analysis
        """
        analysis = {
            'total_choices': self.total_choices,
            'file_types_tracked': len(self.type_folder_map),
            'folders_used': len(self.folder_metadata),
            'top_folders': [],
            'type_preferences': {}
        }

        # Find most used folders
        folder_usage = [
            (folder, meta['usage_count'])
            for folder, meta in self.folder_metadata.items()
        ]
        folder_usage.sort(key=lambda x: x[1], reverse=True)
        analysis['top_folders'] = [
            {'folder': f, 'count': c}
            for f, c in folder_usage[:10]
        ]

        # Find strong type preferences (>70% confidence)
        for file_type, folders in self.type_folder_map.items():
            total = sum(folders.values())
            best = max(folders.items(), key=lambda x: x[1])
            confidence = best[1] / total if total > 0 else 0

            if confidence > 0.7:
                analysis['type_preferences'][file_type] = {
                    'folder': best[0],
                    'confidence': confidence,
                    'count': best[1]
                }

        return analysis

    def suggest_folder_structure(
        self,
        file_info: Dict,
        min_confidence: float = 0.5
    ) -> Optional[Path]:
        """
        Suggest a folder based on file information and learned patterns.

        Args:
            file_info: Dictionary with file metadata (type, name, etc.)
            min_confidence: Minimum confidence threshold

        Returns:
            Suggested folder path or None
        """
        file_type = file_info.get('type', '').lower()

        # First, try type-based preference
        preferred = self.get_preferred_folder(file_type, min_confidence)
        if preferred:
            return preferred

        # Try pattern-based if filename provided
        if 'name' in file_info:
            filename = file_info['name']
            for pattern, folders in self.pattern_folder_map.items():
                if pattern in filename.lower():
                    total = sum(folders.values())
                    if total > 0:
                        best = max(folders.items(), key=lambda x: x[1])
                        confidence = best[1] / total
                        if confidence >= min_confidence:
                            return Path(best[0])

        return None

    def get_folder_stats(self, folder: Path) -> Dict:
        """
        Get statistics for a specific folder.

        Args:
            folder: Folder path

        Returns:
            Statistics dictionary
        """
        folder_str = str(folder.resolve())

        if folder_str not in self.folder_metadata:
            return {
                'exists': False,
                'usage_count': 0,
                'file_types': []
            }

        meta = self.folder_metadata[folder_str]
        return {
            'exists': True,
            'usage_count': meta['usage_count'],
            'file_types': list(meta['file_types']),
            'created': meta['created'],
            'last_used': meta['last_used']
        }

    def clear_old_preferences(self, days: int = 90) -> int:
        """
        Clear preferences older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of preferences cleared
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        cleared = 0

        # Clear folder metadata for old folders
        folders_to_remove = []
        for folder, meta in self.folder_metadata.items():
            last_used = datetime.fromisoformat(meta['last_used'])
            if last_used < cutoff:
                folders_to_remove.append(folder)
                cleared += 1

        for folder in folders_to_remove:
            del self.folder_metadata[folder]

            # Remove from mappings
            for file_type in self.type_folder_map:
                if folder in self.type_folder_map[file_type]:
                    del self.type_folder_map[file_type][folder]

        self._save_preferences()
        logger.info(f"Cleared {cleared} old folder preferences")

        return cleared

    def _save_preferences(self) -> None:
        """Save preferences to disk."""
        data = {
            'type_folder_map': {
                k: dict(v) for k, v in self.type_folder_map.items()
            },
            'pattern_folder_map': {
                k: dict(v) for k, v in self.pattern_folder_map.items()
            },
            'folder_metadata': {
                k: {**v, 'file_types': list(v['file_types'])}
                for k, v in self.folder_metadata.items()
            },
            'total_choices': self.total_choices
        }

        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_preferences(self) -> None:
        """Load preferences from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            # Load type_folder_map
            for file_type, folders in data.get('type_folder_map', {}).items():
                self.type_folder_map[file_type] = defaultdict(int, folders)

            # Load pattern_folder_map
            for pattern, folders in data.get('pattern_folder_map', {}).items():
                self.pattern_folder_map[pattern] = defaultdict(int, folders)

            # Load folder_metadata
            for folder, meta in data.get('folder_metadata', {}).items():
                self.folder_metadata[folder] = {
                    **meta,
                    'file_types': set(meta['file_types'])
                }

            self.total_choices = data.get('total_choices', 0)

            logger.info(f"Loaded {len(self.type_folder_map)} folder preferences")
        except Exception as e:
            logger.error(f"Error loading preferences: {e}")
