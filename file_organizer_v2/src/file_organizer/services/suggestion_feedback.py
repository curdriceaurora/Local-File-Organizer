"""
Suggestion Feedback System

Tracks user actions on suggestions and provides continuous learning
through pattern refinement.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

from ..models.suggestion_types import Suggestion, SuggestionType

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEntry:
    """Single feedback entry for a suggestion."""
    suggestion_id: str
    suggestion_type: SuggestionType
    action: str  # 'accepted', 'rejected', 'ignored', 'modified'
    file_path: str
    target_path: Optional[str]
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'suggestion_id': self.suggestion_id,
            'suggestion_type': self.suggestion_type.value if isinstance(self.suggestion_type, SuggestionType) else self.suggestion_type,
            'action': self.action,
            'file_path': self.file_path,
            'target_path': self.target_path,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'FeedbackEntry':
        """Create from dictionary."""
        return cls(
            suggestion_id=data['suggestion_id'],
            suggestion_type=SuggestionType(data['suggestion_type']),
            action=data['action'],
            file_path=data['file_path'],
            target_path=data.get('target_path'),
            confidence=data['confidence'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            metadata=data.get('metadata', {})
        )


@dataclass
class LearningStats:
    """Statistics from feedback learning."""
    total_suggestions: int = 0
    accepted: int = 0
    rejected: int = 0
    ignored: int = 0
    modified: int = 0
    acceptance_rate: float = 0.0
    rejection_rate: float = 0.0
    avg_accepted_confidence: float = 0.0
    avg_rejected_confidence: float = 0.0
    by_type: Dict[str, Dict] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class SuggestionFeedback:
    """
    Manages feedback collection and learning from user actions.
    """

    def __init__(self, feedback_file: Optional[Path] = None):
        """
        Initialize the feedback system.

        Args:
            feedback_file: Path to store feedback data
        """
        self.feedback_file = feedback_file or Path.home() / '.file_organizer' / 'suggestion_feedback.json'
        self.feedback_entries: List[FeedbackEntry] = []
        self.pattern_adjustments: Dict[str, float] = {}

        # Ensure directory exists
        self.feedback_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing feedback
        self._load_feedback()

    def record_action(
        self,
        suggestion: Suggestion,
        action: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Record user action on a suggestion.

        Args:
            suggestion: The suggestion acted upon
            action: Action taken ('accepted', 'rejected', 'ignored', 'modified')
            metadata: Additional metadata about the action
        """
        logger.info(f"Recording {action} for suggestion {suggestion.suggestion_id}")

        entry = FeedbackEntry(
            suggestion_id=suggestion.suggestion_id,
            suggestion_type=suggestion.suggestion_type,
            action=action,
            file_path=str(suggestion.file_path),
            target_path=str(suggestion.target_path) if suggestion.target_path else None,
            confidence=suggestion.confidence,
            metadata=metadata or {}
        )

        self.feedback_entries.append(entry)
        self._save_feedback()

        # Update pattern adjustments
        self._update_patterns(entry)

    def get_acceptance_rate(self, suggestion_type: Optional[str] = None) -> float:
        """
        Get acceptance rate for suggestions.

        Args:
            suggestion_type: Optional filter by suggestion type

        Returns:
            Acceptance rate (0-100)
        """
        entries = self.feedback_entries

        if suggestion_type:
            entries = [
                e for e in entries
                if e.suggestion_type.value == suggestion_type
            ]

        if not entries:
            return 0.0

        accepted = sum(1 for e in entries if e.action == 'accepted')
        return (accepted / len(entries)) * 100

    def get_rejection_rate(self, suggestion_type: Optional[str] = None) -> float:
        """
        Get rejection rate for suggestions.

        Args:
            suggestion_type: Optional filter by suggestion type

        Returns:
            Rejection rate (0-100)
        """
        entries = self.feedback_entries

        if suggestion_type:
            entries = [
                e for e in entries
                if e.suggestion_type.value == suggestion_type
            ]

        if not entries:
            return 0.0

        rejected = sum(1 for e in entries if e.action == 'rejected')
        return (rejected / len(entries)) * 100

    def get_learning_stats(self) -> LearningStats:
        """
        Get comprehensive learning statistics.

        Returns:
            LearningStats with all metrics
        """
        stats = LearningStats()
        stats.total_suggestions = len(self.feedback_entries)

        if not self.feedback_entries:
            return stats

        # Count actions
        stats.accepted = sum(1 for e in self.feedback_entries if e.action == 'accepted')
        stats.rejected = sum(1 for e in self.feedback_entries if e.action == 'rejected')
        stats.ignored = sum(1 for e in self.feedback_entries if e.action == 'ignored')
        stats.modified = sum(1 for e in self.feedback_entries if e.action == 'modified')

        # Calculate rates
        stats.acceptance_rate = (stats.accepted / stats.total_suggestions) * 100
        stats.rejection_rate = (stats.rejected / stats.total_suggestions) * 100

        # Average confidences
        accepted_entries = [e for e in self.feedback_entries if e.action == 'accepted']
        rejected_entries = [e for e in self.feedback_entries if e.action == 'rejected']

        if accepted_entries:
            stats.avg_accepted_confidence = sum(e.confidence for e in accepted_entries) / len(accepted_entries)

        if rejected_entries:
            stats.avg_rejected_confidence = sum(e.confidence for e in rejected_entries) / len(rejected_entries)

        # Stats by type
        by_type = defaultdict(lambda: {
            'total': 0,
            'accepted': 0,
            'rejected': 0,
            'acceptance_rate': 0.0
        })

        for entry in self.feedback_entries:
            type_key = entry.suggestion_type.value
            by_type[type_key]['total'] += 1
            if entry.action == 'accepted':
                by_type[type_key]['accepted'] += 1
            elif entry.action == 'rejected':
                by_type[type_key]['rejected'] += 1

        # Calculate acceptance rates by type
        for type_key, type_stats in by_type.items():
            if type_stats['total'] > 0:
                type_stats['acceptance_rate'] = (
                    type_stats['accepted'] / type_stats['total']
                ) * 100

        stats.by_type = dict(by_type)

        return stats

    def update_patterns(self, feedback: List[FeedbackEntry]) -> None:
        """
        Update patterns based on feedback.

        Args:
            feedback: List of feedback entries to learn from
        """
        logger.info(f"Updating patterns from {len(feedback)} feedback entries")

        for entry in feedback:
            self._update_patterns(entry)

    def get_confidence_adjustment(
        self,
        suggestion_type: SuggestionType,
        file_type: str
    ) -> float:
        """
        Get confidence adjustment factor based on learning.

        Args:
            suggestion_type: Type of suggestion
            file_type: File extension

        Returns:
            Adjustment factor (-20 to +20)
        """
        key = f"{suggestion_type.value}:{file_type}"

        if key in self.pattern_adjustments:
            return self.pattern_adjustments[key]

        # Default: no adjustment
        return 0.0

    def get_user_history(self) -> Dict:
        """
        Get user action history for pattern matching.

        Returns:
            Dictionary with move history and preferences
        """
        history = {
            'move_history': defaultdict(lambda: defaultdict(int)),
            'rename_patterns': [],
            'preferred_locations': defaultdict(int)
        }

        for entry in self.feedback_entries:
            if entry.action != 'accepted':
                continue

            # Track move history
            if entry.suggestion_type == SuggestionType.MOVE and entry.target_path:
                file_type = Path(entry.file_path).suffix.lower()
                target_dir = str(Path(entry.target_path).parent)
                history['move_history'][file_type][target_dir] += 1
                history['preferred_locations'][target_dir] += 1

        return dict(history)

    def clear_old_feedback(self, days: int = 90) -> int:
        """
        Clear feedback older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of entries removed
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        initial_count = len(self.feedback_entries)

        self.feedback_entries = [
            e for e in self.feedback_entries
            if e.timestamp.timestamp() > cutoff
        ]

        removed = initial_count - len(self.feedback_entries)

        if removed > 0:
            self._save_feedback()
            logger.info(f"Removed {removed} old feedback entries")

        return removed

    def _update_patterns(self, entry: FeedbackEntry) -> None:
        """Update pattern adjustments based on feedback entry."""
        file_type = Path(entry.file_path).suffix.lower()
        key = f"{entry.suggestion_type.value}:{file_type}"

        # Initialize if needed
        if key not in self.pattern_adjustments:
            self.pattern_adjustments[key] = 0.0

        # Adjust based on action
        if entry.action == 'accepted':
            # Increase confidence for this pattern
            adjustment = (100 - entry.confidence) * 0.1
            self.pattern_adjustments[key] = min(
                self.pattern_adjustments[key] + adjustment,
                20.0
            )
        elif entry.action == 'rejected':
            # Decrease confidence for this pattern
            adjustment = entry.confidence * 0.1
            self.pattern_adjustments[key] = max(
                self.pattern_adjustments[key] - adjustment,
                -20.0
            )

    def _load_feedback(self) -> None:
        """Load feedback from file."""
        if not self.feedback_file.exists():
            logger.info("No existing feedback file found")
            return

        try:
            with open(self.feedback_file, 'r') as f:
                data = json.load(f)

            self.feedback_entries = [
                FeedbackEntry.from_dict(entry)
                for entry in data.get('entries', [])
            ]

            self.pattern_adjustments = data.get('pattern_adjustments', {})

            logger.info(f"Loaded {len(self.feedback_entries)} feedback entries")

        except Exception as e:
            logger.error(f"Failed to load feedback: {e}")
            self.feedback_entries = []
            self.pattern_adjustments = {}

    def _save_feedback(self) -> None:
        """Save feedback to file."""
        try:
            data = {
                'entries': [entry.to_dict() for entry in self.feedback_entries],
                'pattern_adjustments': self.pattern_adjustments,
                'last_updated': datetime.now().isoformat()
            }

            with open(self.feedback_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self.feedback_entries)} feedback entries")

        except Exception as e:
            logger.error(f"Failed to save feedback: {e}")

    def export_feedback(self, output_file: Path) -> None:
        """
        Export feedback to a file for analysis.

        Args:
            output_file: Path to export file
        """
        data = {
            'entries': [entry.to_dict() for entry in self.feedback_entries],
            'stats': self.get_learning_stats().to_dict(),
            'pattern_adjustments': self.pattern_adjustments,
            'exported_at': datetime.now().isoformat()
        }

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported feedback to {output_file}")
