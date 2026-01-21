"""
Auto-Tagging Service

Intelligent tag suggestion system that learns from user behavior.
"""

from .content_analyzer import ContentTagAnalyzer
from .tag_learning import (
    TagLearningEngine,
    TagPattern,
    TagUsage
)
from .tag_recommender import (
    TagRecommender,
    TagSuggestion,
    TagRecommendation
)

__all__ = [
    'ContentTagAnalyzer',
    'TagLearningEngine',
    'TagPattern',
    'TagUsage',
    'TagRecommender',
    'TagSuggestion',
    'TagRecommendation',
    'AutoTaggingService'
]


class AutoTaggingService:
    """
    Main auto-tagging service orchestrator.

    Coordinates content analysis, learning, and recommendation.
    """

    def __init__(self, storage_path=None):
        """
        Initialize the auto-tagging service.

        Args:
            storage_path: Optional path for storing learning data
        """
        self.content_analyzer = ContentTagAnalyzer()
        self.learning_engine = TagLearningEngine(storage_path=storage_path)
        self.recommender = TagRecommender(
            content_analyzer=self.content_analyzer,
            learning_engine=self.learning_engine
        )

    def suggest_tags(self, file_path, existing_tags=None, top_n=10):
        """
        Suggest tags for a file.

        Args:
            file_path: Path to the file
            existing_tags: Tags already applied
            top_n: Maximum suggestions

        Returns:
            TagRecommendation object
        """
        return self.recommender.recommend_tags(
            file_path,
            existing_tags=existing_tags,
            top_n=top_n
        )

    def record_tag_usage(self, file_path, tags, context=None):
        """
        Record when user applies tags.

        Args:
            file_path: Path to the file
            tags: List of tags applied
            context: Optional context dict
        """
        self.learning_engine.record_tag_application(
            file_path,
            tags,
            context=context
        )

    def provide_feedback(self, feedback_items):
        """
        Update learning model with user feedback.

        Args:
            feedback_items: List of feedback dicts
        """
        self.learning_engine.update_model(feedback_items)

    def get_popular_tags(self, limit=20):
        """Get most popular tags."""
        return self.learning_engine.get_popular_tags(limit=limit)

    def get_recent_tags(self, days=30, limit=20):
        """Get recently used tags."""
        return self.learning_engine.get_recent_tags(days=days, limit=limit)
