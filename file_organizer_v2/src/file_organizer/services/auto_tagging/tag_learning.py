"""
Tag Learning Engine

Learns from user tagging patterns to improve tag suggestions over time.
Tracks tag usage, co-occurrences, and builds personalized tag models.
"""

import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import json
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class TagPattern:
    """Represents a learned tag pattern."""
    pattern_type: str  # co-occurrence, frequency, context
    tags: List[str]
    frequency: float
    confidence: float
    contexts: List[str] = field(default_factory=list)
    last_seen: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        data = asdict(self)
        if self.last_seen:
            data['last_seen'] = self.last_seen.isoformat()
        return data

    @staticmethod
    def from_dict(data: Dict) -> 'TagPattern':
        """Create from dictionary."""
        if 'last_seen' in data and data['last_seen']:
            data['last_seen'] = datetime.fromisoformat(data['last_seen'])
        return TagPattern(**data)


@dataclass
class TagUsage:
    """Tracks usage statistics for a tag."""
    tag: str
    count: int = 0
    first_used: Optional[datetime] = None
    last_used: Optional[datetime] = None
    file_types: Set[str] = field(default_factory=set)
    contexts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'tag': self.tag,
            'count': self.count,
            'first_used': self.first_used.isoformat() if self.first_used else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'file_types': list(self.file_types),
            'contexts': self.contexts[-10:]  # Keep last 10 contexts
        }

    @staticmethod
    def from_dict(data: Dict) -> 'TagUsage':
        """Create from dictionary."""
        return TagUsage(
            tag=data['tag'],
            count=data.get('count', 0),
            first_used=datetime.fromisoformat(data['first_used']) if data.get('first_used') else None,
            last_used=datetime.fromisoformat(data['last_used']) if data.get('last_used') else None,
            file_types=set(data.get('file_types', [])),
            contexts=data.get('contexts', [])
        )


class TagLearningEngine:
    """
    Learns from user tagging behavior to improve suggestions.

    Tracks:
    - Tag usage frequency
    - Tag co-occurrences
    - Tag usage context (file types, directories)
    - Temporal patterns
    - User preferences
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the tag learning engine.

        Args:
            storage_path: Path to store learning data
        """
        if storage_path is None:
            storage_path = Path.home() / ".file_organizer" / "tag_learning.json"

        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Learning data structures
        self.tag_usage: Dict[str, TagUsage] = {}
        self.tag_cooccurrence: Dict[str, Counter] = defaultdict(Counter)
        self.file_type_tags: Dict[str, Counter] = defaultdict(Counter)
        self.directory_tags: Dict[str, Counter] = defaultdict(Counter)

        # Load existing data
        self._load_data()

        logger.info("TagLearningEngine initialized")

    def record_tag_application(
        self,
        file_path: Path,
        tags: List[str],
        context: Optional[Dict] = None
    ) -> None:
        """
        Record when a user applies tags to a file.

        Args:
            file_path: Path to the tagged file
            tags: List of tags applied
            context: Additional context information
        """
        if not tags:
            return

        logger.debug(f"Recording tag application: {file_path.name} -> {tags}")

        now = datetime.now()
        file_ext = file_path.suffix.lower()
        directory = str(file_path.parent)

        # Update tag usage statistics
        for tag in tags:
            if tag not in self.tag_usage:
                self.tag_usage[tag] = TagUsage(
                    tag=tag,
                    first_used=now,
                    last_used=now,
                    count=1
                )
            else:
                usage = self.tag_usage[tag]
                usage.count += 1
                usage.last_used = now

            # Track file type associations
            if file_ext:
                self.tag_usage[tag].file_types.add(file_ext)
                self.file_type_tags[file_ext][tag] += 1

            # Track directory associations
            self.directory_tags[directory][tag] += 1

            # Track context
            if context:
                context_str = json.dumps(context, sort_keys=True)
                self.tag_usage[tag].contexts.append(context_str)

        # Track tag co-occurrences
        for i, tag1 in enumerate(tags):
            for tag2 in tags[i + 1:]:
                self.tag_cooccurrence[tag1][tag2] += 1
                self.tag_cooccurrence[tag2][tag1] += 1

        # Save data
        self._save_data()

    def get_tag_patterns(self, file_type: Optional[str] = None) -> List[TagPattern]:
        """
        Get learned tag patterns.

        Args:
            file_type: Optional filter by file type

        Returns:
            List of tag patterns
        """
        patterns = []

        # Frequency patterns
        for tag, usage in self.tag_usage.items():
            if file_type and file_type not in usage.file_types:
                continue

            # Calculate confidence based on frequency and recency
            confidence = self._calculate_tag_confidence(usage)

            patterns.append(TagPattern(
                pattern_type='frequency',
                tags=[tag],
                frequency=usage.count,
                confidence=confidence,
                contexts=usage.contexts[-5:],
                last_seen=usage.last_used
            ))

        # Co-occurrence patterns
        for tag1, cooccur_tags in self.tag_cooccurrence.items():
            for tag2, _count in cooccur_tags.most_common(5):
                if count < 2:  # Need at least 2 co-occurrences
                    continue

                # Calculate confidence
                total_tag1 = self.tag_usage[tag1].count
                confidence = (count / total_tag1) * 100 if total_tag1 > 0 else 0

                patterns.append(TagPattern(
                    pattern_type='co-occurrence',
                    tags=[tag1, tag2],
                    frequency=count,
                    confidence=confidence
                ))

        return patterns

    def predict_tags(
        self,
        file_path: Path,
        max_predictions: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Predict tags for a file based on learned patterns.

        Args:
            file_path: Path to the file
            max_predictions: Maximum number of predictions

        Returns:
            List of (tag, confidence) tuples
        """
        predictions = {}

        file_ext = file_path.suffix.lower()
        directory = str(file_path.parent)

        # Predict based on file type
        if file_ext in self.file_type_tags:
            for tag, _count in self.file_type_tags[file_ext].most_common(10):
                usage = self.tag_usage[tag]
                confidence = self._calculate_tag_confidence(usage)
                predictions[tag] = max(predictions.get(tag, 0), confidence)

        # Predict based on directory
        if directory in self.directory_tags:
            for tag, _count in self.directory_tags[directory].most_common(10):
                usage = self.tag_usage[tag]
                confidence = self._calculate_tag_confidence(usage)
                # Give directory predictions slightly higher weight
                predictions[tag] = max(predictions.get(tag, 0), confidence * 1.1)

        # Sort by confidence
        sorted_predictions = sorted(
            predictions.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_predictions[:max_predictions]

    def get_related_tags(self, tag: str, max_related: int = 5) -> List[str]:
        """
        Get tags that are frequently used with the given tag.

        Args:
            tag: The tag to find related tags for
            max_related: Maximum number of related tags

        Returns:
            List of related tag names
        """
        if tag not in self.tag_cooccurrence:
            return []

        related = self.tag_cooccurrence[tag].most_common(max_related)
        return [t for t, _ in related]

    def update_model(self, feedback: List[Dict]) -> None:
        """
        Update the learning model based on user feedback.

        Args:
            feedback: List of feedback items with structure:
                {
                    'file_path': str,
                    'suggested_tags': List[str],
                    'accepted_tags': List[str],
                    'rejected_tags': List[str],
                    'timestamp': str
                }
        """
        logger.info(f"Updating model with {len(feedback)} feedback items")

        for item in feedback:
            file_path = Path(item['file_path'])
            accepted = item.get('accepted_tags', [])
            rejected = item.get('rejected_tags', [])

            # Record accepted tags
            if accepted:
                self.record_tag_application(file_path, accepted)

            # Reduce confidence for rejected tags
            for tag in rejected:
                if tag in self.tag_usage:
                    # Reduce count slightly (but don't go below 1)
                    self.tag_usage[tag].count = max(
                        1,
                        self.tag_usage[tag].count - 0.5
                    )

        self._save_data()

    def get_popular_tags(self, limit: int = 20) -> List[Tuple[str, int]]:
        """
        Get most popular tags by usage count.

        Args:
            limit: Maximum number of tags to return

        Returns:
            List of (tag, count) tuples
        """
        tag_counts = [
            (usage.tag, usage.count)
            for usage in self.tag_usage.values()
        ]

        tag_counts.sort(key=lambda x: x[1], reverse=True)
        return tag_counts[:limit]

    def get_recent_tags(self, days: int = 30, limit: int = 20) -> List[str]:
        """
        Get recently used tags.

        Args:
            days: Number of days to look back
            limit: Maximum number of tags to return

        Returns:
            List of tag names
        """
        cutoff = datetime.now() - timedelta(days=days)

        recent = [
            (usage.tag, usage.last_used)
            for usage in self.tag_usage.values()
            if usage.last_used and usage.last_used >= cutoff
        ]

        recent.sort(key=lambda x: x[1], reverse=True)
        return [tag for tag, _ in recent[:limit]]

    def get_tag_suggestions_for_context(
        self,
        file_type: Optional[str] = None,
        directory: Optional[str] = None,
        existing_tags: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get tag suggestions based on context.

        Args:
            file_type: File extension
            directory: Directory path
            existing_tags: Tags already applied
            limit: Maximum suggestions

        Returns:
            List of (tag, confidence) tuples
        """
        suggestions = {}

        # Suggest based on file type
        if file_type and file_type in self.file_type_tags:
            for tag, _count in self.file_type_tags[file_type].most_common(15):
                usage = self.tag_usage[tag]
                confidence = self._calculate_tag_confidence(usage)
                suggestions[tag] = confidence

        # Suggest based on directory
        if directory and directory in self.directory_tags:
            for tag, _count in self.directory_tags[directory].most_common(15):
                usage = self.tag_usage[tag]
                confidence = self._calculate_tag_confidence(usage)
                suggestions[tag] = max(suggestions.get(tag, 0), confidence * 1.1)

        # Suggest based on existing tags (co-occurrence)
        if existing_tags:
            for existing_tag in existing_tags:
                if existing_tag in self.tag_cooccurrence:
                    for tag, _count in self.tag_cooccurrence[existing_tag].most_common(5):
                        usage = self.tag_usage[tag]
                        confidence = self._calculate_tag_confidence(usage) * 1.2
                        suggestions[tag] = max(suggestions.get(tag, 0), confidence)

        # Filter out existing tags
        if existing_tags:
            for tag in existing_tags:
                suggestions.pop(tag, None)

        # Sort and limit
        sorted_suggestions = sorted(
            suggestions.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_suggestions[:limit]

    def _calculate_tag_confidence(self, usage: TagUsage) -> float:
        """
        Calculate confidence score for a tag based on usage.

        Factors:
        - Frequency (how often used)
        - Recency (how recently used)
        - Consistency (file type associations)

        Returns:
            Confidence score (0-100)
        """
        # Base confidence from frequency
        freq_score = min(usage.count * 10, 60)  # Max 60 from frequency

        # Recency bonus
        recency_score = 0
        if usage.last_used:
            days_ago = (datetime.now() - usage.last_used).days
            if days_ago <= 7:
                recency_score = 20
            elif days_ago <= 30:
                recency_score = 10
            elif days_ago <= 90:
                recency_score = 5

        # Consistency bonus (used across multiple file types)
        consistency_score = min(len(usage.file_types) * 5, 20)

        total = freq_score + recency_score + consistency_score
        return min(total, 100.0)

    def _save_data(self) -> None:
        """Save learning data to disk."""
        try:
            data = {
                'tag_usage': {
                    tag: usage.to_dict()
                    for tag, usage in self.tag_usage.items()
                },
                'tag_cooccurrence': {
                    tag: dict(counter)
                    for tag, counter in self.tag_cooccurrence.items()
                },
                'file_type_tags': {
                    ft: dict(counter)
                    for ft, counter in self.file_type_tags.items()
                },
                'directory_tags': {
                    dir_: dict(counter)
                    for dir_, counter in self.directory_tags.items()
                },
                'last_updated': datetime.now().isoformat()
            }

            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved learning data to {self.storage_path}")

        except Exception as e:
            logger.error(f"Error saving learning data: {e}")

    def _load_data(self) -> None:
        """Load learning data from disk."""
        if not self.storage_path.exists():
            logger.info("No existing learning data found")
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            # Load tag usage
            self.tag_usage = {
                tag: TagUsage.from_dict(usage_data)
                for tag, usage_data in data.get('tag_usage', {}).items()
            }

            # Load tag co-occurrence
            self.tag_cooccurrence = defaultdict(Counter)
            for tag, counter_dict in data.get('tag_cooccurrence', {}).items():
                self.tag_cooccurrence[tag] = Counter(counter_dict)

            # Load file type tags
            self.file_type_tags = defaultdict(Counter)
            for ft, counter_dict in data.get('file_type_tags', {}).items():
                self.file_type_tags[ft] = Counter(counter_dict)

            # Load directory tags
            self.directory_tags = defaultdict(Counter)
            for dir_, counter_dict in data.get('directory_tags', {}).items():
                self.directory_tags[dir_] = Counter(counter_dict)

            logger.info(f"Loaded learning data: {len(self.tag_usage)} tags tracked")

        except Exception as e:
            logger.error(f"Error loading learning data: {e}")
