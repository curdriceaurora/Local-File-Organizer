"""Auto-Tagging Service.

Intelligent tag suggestion system that learns from user behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .content_analyzer import ContentTagAnalyzer
from .tag_learning import TagLearningEngine, TagPattern, TagUsage
from .tag_recommender import TagRecommendation, TagRecommender, TagSuggestion

__all__ = [
    "ContentTagAnalyzer",
    "TagLearningEngine",
    "TagPattern",
    "TagUsage",
    "TagRecommender",
    "TagSuggestion",
    "TagRecommendation",
    "AutoTaggingService",
]


class AutoTaggingService:
    """Main auto-tagging service orchestrator.

    Coordinates content analysis, learning, and recommendation.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        """Initialize the auto-tagging service.

        Args:
            storage_path: Optional path for storing learning data
        """
        self.content_analyzer = ContentTagAnalyzer()
        self.learning_engine = TagLearningEngine(storage_path=storage_path)
        self.recommender = TagRecommender(
            content_analyzer=self.content_analyzer, learning_engine=self.learning_engine
        )

    def suggest_tags(
        self,
        file_path: Path,
        existing_tags: list[str] | None = None,
        top_n: int = 10,
    ) -> TagRecommendation:
        """Suggest tags for a file.

        Args:
            file_path: Path to the file
            existing_tags: Tags already applied
            top_n: Maximum suggestions

        Returns:
            TagRecommendation object
        """
        return self.recommender.recommend_tags(file_path, existing_tags=existing_tags, top_n=top_n)

    def record_tag_usage(
        self,
        file_path: Path,
        tags: list[str],
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record when user applies tags.

        Args:
            file_path: Path to the file
            tags: List of tags applied
            context: Optional context dict
        """
        self.learning_engine.record_tag_application(file_path, tags, context=context)

    def provide_feedback(self, feedback_items: list[dict[str, Any]]) -> None:
        """Update learning model with user feedback.

        Args:
            feedback_items: List of feedback dicts
        """
        self.learning_engine.update_model(feedback_items)

    def get_popular_tags(self, limit: int = 20) -> list[tuple[str, int]]:
        """Get most popular tags."""
        return self.learning_engine.get_popular_tags(limit=limit)

    def get_recent_tags(self, days: int = 30, limit: int = 20) -> list[str]:
        """Get recently used tags."""
        return self.learning_engine.get_recent_tags(days=days, limit=limit)
