"""
Feedback Collection and Pattern Learning for PARA Suggestions

Provides a privacy-first feedback loop: user acceptances and rejections
are stored locally in JSON and used to learn patterns that improve future
suggestions. No data leaves the local machine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..categories import PARACategory
from ..config import HeuristicWeights

logger = logging.getLogger(__name__)

# Default feedback storage location
_DEFAULT_FEEDBACK_DIR = Path.home() / ".config" / "file-organizer" / "feedback"


@dataclass
class FeedbackEvent:
    """A single feedback event recording a user's response to a suggestion.

    Attributes:
        file_path: Path to the file that was categorized.
        suggested: The category the engine suggested.
        actual: The category the user selected (same as suggested if accepted).
        confidence: The confidence of the original suggestion.
        timestamp: When the feedback was recorded.
        accepted: Whether the user accepted the suggestion.
        file_extension: Extension of the file (for pattern learning).
        parent_directory: Parent directory name (for structural patterns).
    """

    file_path: Path
    suggested: PARACategory
    actual: PARACategory
    confidence: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    accepted: bool = True
    file_extension: str = ""
    parent_directory: str = ""

    def __post_init__(self) -> None:
        """Set derived fields from file_path."""
        if not self.file_extension and self.file_path:
            self.file_extension = Path(self.file_path).suffix.lower()
        if not self.parent_directory and self.file_path:
            self.parent_directory = Path(self.file_path).parent.name

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "file_path": str(self.file_path),
            "suggested": self.suggested.value,
            "actual": self.actual.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "accepted": self.accepted,
            "file_extension": self.file_extension,
            "parent_directory": self.parent_directory,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackEvent:
        """Deserialize from a dictionary."""
        return cls(
            file_path=Path(data["file_path"]),
            suggested=PARACategory(data["suggested"]),
            actual=PARACategory(data["actual"]),
            confidence=float(data["confidence"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            accepted=bool(data["accepted"]),
            file_extension=data.get("file_extension", ""),
            parent_directory=data.get("parent_directory", ""),
        )


@dataclass
class AccuracyStats:
    """Aggregated accuracy statistics from feedback events.

    Attributes:
        total_events: Total number of feedback events.
        accepted_count: Number of accepted suggestions.
        rejected_count: Number of rejected suggestions.
        accuracy_rate: Proportion of accepted suggestions (0.0-1.0).
        per_category_accuracy: Accuracy broken down by category.
        average_confidence: Mean confidence of all suggestions.
        confidence_when_accepted: Mean confidence when suggestion was accepted.
        confidence_when_rejected: Mean confidence when suggestion was rejected.
    """

    total_events: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    accuracy_rate: float = 0.0
    per_category_accuracy: dict[str, float] = field(default_factory=dict)
    average_confidence: float = 0.0
    confidence_when_accepted: float = 0.0
    confidence_when_rejected: float = 0.0


@dataclass
class LearnedRule:
    """A pattern rule learned from feedback events.

    Attributes:
        pattern_type: Type of pattern ("extension", "directory", "keyword").
        pattern_value: The pattern value (e.g., ".pdf", "projects").
        suggested_category: Learned category for this pattern.
        occurrences: How many times this pattern was confirmed.
        confidence: Learned confidence score for this pattern.
    """

    pattern_type: str
    pattern_value: str
    suggested_category: PARACategory
    occurrences: int = 1
    confidence: float = 0.5


class FeedbackCollector:
    """Collects and persists user feedback on PARA suggestions.

    Feedback is stored locally in a JSON file. The collector provides
    methods to record acceptances/rejections and query accuracy stats.

    Example::

        collector = FeedbackCollector()
        collector.record_acceptance(Path("report.pdf"), suggestion)
        stats = collector.get_accuracy_stats()
        print(f"Accuracy: {stats.accuracy_rate:.0%}")
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        """Initialize the feedback collector.

        Args:
            storage_dir: Directory for storing feedback JSON. Uses default
                ~/.config/file-organizer/feedback if not specified.
        """
        self._storage_dir = storage_dir or _DEFAULT_FEEDBACK_DIR
        self._feedback_file = self._storage_dir / "feedback_events.json"
        self._events: list[FeedbackEvent] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load events from disk if not already loaded."""
        if self._loaded:
            return
        self._events = self._load_events()
        self._loaded = True

    def record_acceptance(
        self,
        file_path: Path,
        suggestion: Any,
    ) -> None:
        """Record that the user accepted a suggestion.

        Args:
            file_path: Path to the file.
            suggestion: The PARASuggestion that was accepted. Expected to
                have 'category' and 'confidence' attributes.
        """
        event = FeedbackEvent(
            file_path=file_path,
            suggested=suggestion.category,
            actual=suggestion.category,
            confidence=suggestion.confidence,
            accepted=True,
        )
        self._ensure_loaded()
        self._events.append(event)
        self._save_events()

    def record_rejection(
        self,
        file_path: Path,
        suggestion: Any,
        correct_category: PARACategory,
    ) -> None:
        """Record that the user rejected a suggestion and chose differently.

        Args:
            file_path: Path to the file.
            suggestion: The PARASuggestion that was rejected.
            correct_category: The category the user selected instead.
        """
        event = FeedbackEvent(
            file_path=file_path,
            suggested=suggestion.category,
            actual=correct_category,
            confidence=suggestion.confidence,
            accepted=False,
        )
        self._ensure_loaded()
        self._events.append(event)
        self._save_events()

    def get_accuracy_stats(self) -> AccuracyStats:
        """Compute accuracy statistics from all recorded feedback.

        Returns:
            AccuracyStats with aggregated metrics.
        """
        self._ensure_loaded()
        events = self._events

        if not events:
            return AccuracyStats()

        total = len(events)
        accepted = [e for e in events if e.accepted]
        rejected = [e for e in events if not e.accepted]

        accuracy_rate = len(accepted) / total if total > 0 else 0.0
        avg_confidence = sum(e.confidence for e in events) / total

        conf_accepted = sum(e.confidence for e in accepted) / len(accepted) if accepted else 0.0
        conf_rejected = sum(e.confidence for e in rejected) / len(rejected) if rejected else 0.0

        # Per-category accuracy
        per_cat: dict[str, dict[str, int]] = {}
        for event in events:
            cat_name = event.suggested.value
            if cat_name not in per_cat:
                per_cat[cat_name] = {"total": 0, "accepted": 0}
            per_cat[cat_name]["total"] += 1
            if event.accepted:
                per_cat[cat_name]["accepted"] += 1

        per_category_accuracy = {
            cat: counts["accepted"] / counts["total"]
            for cat, counts in per_cat.items()
            if counts["total"] > 0
        }

        return AccuracyStats(
            total_events=total,
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            accuracy_rate=accuracy_rate,
            per_category_accuracy=per_category_accuracy,
            average_confidence=avg_confidence,
            confidence_when_accepted=conf_accepted,
            confidence_when_rejected=conf_rejected,
        )

    def get_events(self) -> list[FeedbackEvent]:
        """Return all recorded feedback events.

        Returns:
            List of FeedbackEvent objects.
        """
        self._ensure_loaded()
        return list(self._events)

    def clear(self) -> None:
        """Clear all recorded feedback events (local storage only)."""
        self._events = []
        self._loaded = True
        self._save_events()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_events(self) -> list[FeedbackEvent]:
        """Load feedback events from the JSON file.

        Returns:
            List of deserialized FeedbackEvent objects.
        """
        if not self._feedback_file.exists():
            return []

        try:
            with open(self._feedback_file, encoding="utf-8") as f:
                data = json.load(f)
            return [FeedbackEvent.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("Failed to load feedback events: %s", e)
            return []
        except OSError as e:
            logger.error("Cannot read feedback file: %s", e)
            return []

    def _save_events(self) -> None:
        """Persist all feedback events to the JSON file."""
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            data = [event.to_dict() for event in self._events]
            with open(self._feedback_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save feedback events: %s", e)


class PatternLearner:
    """Learns categorization patterns from user feedback.

    Analyzes FeedbackEvents to discover recurring patterns (file extensions,
    directory names, etc.) and produces LearnedRules and adjusted heuristic
    weights.

    Example::

        learner = PatternLearner()
        events = collector.get_events()
        rules = learner.learn_from_feedback(events)
        adjusted_weights = learner.adjust_weights(events)
    """

    def __init__(self, min_occurrences: int = 3) -> None:
        """Initialize the pattern learner.

        Args:
            min_occurrences: Minimum occurrences required to emit a learned rule.
        """
        self._min_occurrences = min_occurrences

    def learn_from_feedback(self, events: list[FeedbackEvent]) -> list[LearnedRule]:
        """Discover categorization patterns from feedback events.

        Looks for recurring patterns in file extensions and parent directory
        names that consistently map to specific PARA categories.

        Args:
            events: List of feedback events to learn from.

        Returns:
            List of learned rules meeting the minimum occurrence threshold.
        """
        if not events:
            return []

        rules: list[LearnedRule] = []

        # Learn extension patterns
        ext_patterns = self._learn_extension_patterns(events)
        rules.extend(ext_patterns)

        # Learn directory patterns
        dir_patterns = self._learn_directory_patterns(events)
        rules.extend(dir_patterns)

        return rules

    def get_user_preferences(
        self,
        events: list[FeedbackEvent] | None = None,
    ) -> dict[str, Any]:
        """Derive user preferences from feedback history.

        Args:
            events: Feedback events to analyze. Empty list if None.

        Returns:
            Dictionary of preference insights.
        """
        if not events:
            return {
                "preferred_categories": {},
                "override_patterns": [],
                "total_interactions": 0,
            }

        # Count how often user chooses each category
        category_counts: dict[str, int] = {}
        for event in events:
            cat = event.actual.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Identify override patterns (rejections)
        override_patterns: list[dict[str, str]] = []
        rejections = [e for e in events if not e.accepted]
        for rej in rejections:
            override_patterns.append(
                {
                    "from": rej.suggested.value,
                    "to": rej.actual.value,
                    "extension": rej.file_extension,
                    "directory": rej.parent_directory,
                }
            )

        return {
            "preferred_categories": category_counts,
            "override_patterns": override_patterns[:20],
            "total_interactions": len(events),
        }

    def adjust_weights(self, events: list[FeedbackEvent]) -> HeuristicWeights:
        """Suggest adjusted heuristic weights based on feedback accuracy.

        If content-based suggestions are frequently wrong but structural ones
        are right, the weights should shift accordingly.

        Args:
            events: Feedback events to analyze.

        Returns:
            Adjusted HeuristicWeights. Returns defaults if insufficient data.
        """
        if len(events) < self._min_occurrences:
            return HeuristicWeights()

        # Analyze which signals correlated with acceptance
        # For simplicity, we adjust based on overall acceptance rate:
        # - High acceptance -> keep defaults
        # - Low acceptance for certain parent dirs -> boost structural
        # - Low acceptance with temporal signals -> reduce temporal

        accepted = [e for e in events if e.accepted]
        acceptance_rate = len(accepted) / len(events)

        # Start from defaults
        temporal = 0.25
        content = 0.35
        structural = 0.30
        ai = 0.10

        if acceptance_rate < 0.5:
            # Low accuracy: boost structural, reduce content slightly
            structural = min(0.40, structural + 0.05)
            content = max(0.25, content - 0.05)
        elif acceptance_rate > 0.8:
            # High accuracy: slight boost to content (working well)
            content = min(0.40, content + 0.03)
            temporal = max(0.22, temporal - 0.03)

        # Check if directory-based patterns dominate rejections
        rejections = [e for e in events if not e.accepted]
        if rejections:
            dir_rejections = [e for e in rejections if e.parent_directory]
            if len(dir_rejections) > len(rejections) * 0.6:
                # Directory-based signals are unreliable
                structural = max(0.20, structural - 0.05)
                content = min(0.45, content + 0.05)

        # Normalize to sum to 1.0
        total = temporal + content + structural + ai
        temporal = round(temporal / total, 2)
        content = round(content / total, 2)
        structural = round(structural / total, 2)
        ai = round(1.0 - temporal - content - structural, 2)

        return HeuristicWeights(
            temporal=temporal,
            content=content,
            structural=structural,
            ai=ai,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _learn_extension_patterns(
        self,
        events: list[FeedbackEvent],
    ) -> list[LearnedRule]:
        """Learn patterns from file extensions.

        Args:
            events: Feedback events.

        Returns:
            List of LearnedRule for extension patterns.
        """
        # Group by extension + actual category
        ext_counts: dict[tuple[str, str], int] = {}
        for event in events:
            if event.file_extension:
                key = (event.file_extension, event.actual.value)
                ext_counts[key] = ext_counts.get(key, 0) + 1

        rules: list[LearnedRule] = []
        for (ext, cat_value), count in ext_counts.items():
            if count >= self._min_occurrences:
                rules.append(
                    LearnedRule(
                        pattern_type="extension",
                        pattern_value=ext,
                        suggested_category=PARACategory(cat_value),
                        occurrences=count,
                        confidence=min(0.9, 0.5 + count * 0.05),
                    )
                )

        return rules

    def _learn_directory_patterns(
        self,
        events: list[FeedbackEvent],
    ) -> list[LearnedRule]:
        """Learn patterns from parent directory names.

        Args:
            events: Feedback events.

        Returns:
            List of LearnedRule for directory patterns.
        """
        dir_counts: dict[tuple[str, str], int] = {}
        for event in events:
            if event.parent_directory:
                key = (event.parent_directory, event.actual.value)
                dir_counts[key] = dir_counts.get(key, 0) + 1

        rules: list[LearnedRule] = []
        for (dirname, cat_value), count in dir_counts.items():
            if count >= self._min_occurrences:
                rules.append(
                    LearnedRule(
                        pattern_type="directory",
                        pattern_value=dirname,
                        suggested_category=PARACategory(cat_value),
                        occurrences=count,
                        confidence=min(0.9, 0.5 + count * 0.05),
                    )
                )

        return rules
