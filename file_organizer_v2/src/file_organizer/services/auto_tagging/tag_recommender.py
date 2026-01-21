"""
Tag Recommendation Engine

Combines content analysis and learning insights to generate ranked tag suggestions.
Integrates with smart suggestions infrastructure.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import hashlib

from .content_analyzer import ContentTagAnalyzer
from .tag_learning import TagLearningEngine, TagPattern

logger = logging.getLogger(__name__)


@dataclass
class TagSuggestion:
    """A tag suggestion with confidence and reasoning."""
    tag: str
    confidence: float  # 0-100
    source: str  # content, behavior, hybrid
    reasoning: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'tag': self.tag,
            'confidence': self.confidence,
            'source': self.source,
            'reasoning': self.reasoning,
            'metadata': self.metadata
        }

    @staticmethod
    def from_dict(data: dict) -> 'TagSuggestion':
        """Create from dictionary."""
        return TagSuggestion(
            tag=data['tag'],
            confidence=data['confidence'],
            source=data['source'],
            reasoning=data['reasoning'],
            metadata=data.get('metadata', {})
        )


@dataclass
class TagRecommendation:
    """Complete tag recommendation for a file."""
    file_path: Path
    suggestions: list[TagSuggestion]
    existing_tags: list[str] = field(default_factory=list)
    confidence_threshold: float = 40.0
    timestamp: datetime = field(default_factory=datetime.now)

    def get_high_confidence_tags(self) -> list[str]:
        """Get tags with confidence >= 70%."""
        return [
            s.tag for s in self.suggestions
            if s.confidence >= 70
        ]

    def get_medium_confidence_tags(self) -> list[str]:
        """Get tags with confidence 40-70%."""
        return [
            s.tag for s in self.suggestions
            if 40 <= s.confidence < 70
        ]

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'file_path': str(self.file_path),
            'suggestions': [s.to_dict() for s in self.suggestions],
            'existing_tags': self.existing_tags,
            'confidence_threshold': self.confidence_threshold,
            'timestamp': self.timestamp.isoformat()
        }


class TagRecommender:
    """
    Generates and ranks tag recommendations by combining multiple signals.

    Features:
    - Content-based tagging
    - Behavior-based tagging
    - Hybrid recommendations
    - Confidence scoring
    - Explanation generation
    """

    def __init__(
        self,
        content_analyzer: Optional[ContentTagAnalyzer] = None,
        learning_engine: Optional[TagLearningEngine] = None,
        min_confidence: float = 40.0
    ):
        """
        Initialize the tag recommender.

        Args:
            content_analyzer: Content analysis component
            learning_engine: Learning component
            min_confidence: Minimum confidence threshold
        """
        self.content_analyzer = content_analyzer or ContentTagAnalyzer()
        self.learning_engine = learning_engine or TagLearningEngine()
        self.min_confidence = min_confidence

        # Weights for different sources
        self.source_weights = {
            'content': 0.4,
            'behavior': 0.4,
            'hybrid': 0.2
        }

        logger.info("TagRecommender initialized")

    def recommend_tags(
        self,
        file_path: Path,
        existing_tags: Optional[list[str]] = None,
        top_n: int = 10
    ) -> TagRecommendation:
        """
        Generate tag recommendations for a file.

        Args:
            file_path: Path to the file
            existing_tags: Tags already applied
            top_n: Maximum number of suggestions

        Returns:
            TagRecommendation with ranked suggestions
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return TagRecommendation(
                file_path=file_path,
                suggestions=[],
                existing_tags=existing_tags or []
            )

        logger.debug(f"Generating tag recommendations for: {file_path.name}")

        existing_tags = existing_tags or []

        # Collect suggestions from different sources
        all_suggestions = {}

        # 1. Content-based suggestions
        content_suggestions = self._get_content_suggestions(file_path)
        for tag, confidence in content_suggestions:
            all_suggestions[tag] = TagSuggestion(
                tag=tag,
                confidence=confidence,
                source='content',
                reasoning=self._generate_content_reasoning(tag, file_path)
            )

        # 2. Behavior-based suggestions
        behavior_suggestions = self._get_behavior_suggestions(file_path, existing_tags)
        for tag, confidence in behavior_suggestions:
            if tag in all_suggestions:
                # Combine with existing suggestion (hybrid)
                existing = all_suggestions[tag]
                combined_confidence = self._combine_confidences(
                    existing.confidence,
                    confidence,
                    existing.source,
                    'behavior'
                )
                all_suggestions[tag] = TagSuggestion(
                    tag=tag,
                    confidence=combined_confidence,
                    source='hybrid',
                    reasoning=self._generate_hybrid_reasoning(tag, file_path)
                )
            else:
                all_suggestions[tag] = TagSuggestion(
                    tag=tag,
                    confidence=confidence,
                    source='behavior',
                    reasoning=self._generate_behavior_reasoning(tag, file_path)
                )

        # 3. Related tag suggestions (if existing tags provided)
        if existing_tags:
            related_suggestions = self._get_related_suggestions(existing_tags)
            for tag, confidence in related_suggestions:
                if tag not in all_suggestions and tag not in existing_tags:
                    all_suggestions[tag] = TagSuggestion(
                        tag=tag,
                        confidence=confidence,
                        source='behavior',
                        reasoning=f"Often used with: {', '.join(existing_tags[:3])}"
                    )

        # Filter existing tags
        for tag in existing_tags:
            all_suggestions.pop(tag, None)

        # Filter by minimum confidence
        filtered_suggestions = [
            s for s in all_suggestions.values()
            if s.confidence >= self.min_confidence
        ]

        # Rank suggestions
        ranked_suggestions = self._rank_suggestions(filtered_suggestions)

        logger.info(
            f"Generated {len(ranked_suggestions)} tag suggestions "
            f"for {file_path.name}"
        )

        return TagRecommendation(
            file_path=file_path,
            suggestions=ranked_suggestions[:top_n],
            existing_tags=existing_tags,
            confidence_threshold=self.min_confidence
        )

    def batch_recommend(
        self,
        files: list[Path],
        top_n: int = 10
    ) -> dict[Path, TagRecommendation]:
        """
        Generate recommendations for multiple files.

        Args:
            files: list of file paths
            top_n: Maximum suggestions per file

        Returns:
            Dictionary mapping file paths to recommendations
        """
        logger.info(f"Batch recommending tags for {len(files)} files")

        results = {}
        for file_path in files:
            try:
                recommendation = self.recommend_tags(file_path, top_n=top_n)
                results[file_path] = recommendation
            except Exception as e:
                logger.error(f"Error recommending tags for {file_path}: {e}")
                results[file_path] = TagRecommendation(
                    file_path=file_path,
                    suggestions=[]
                )

        return results

    def calculate_confidence(self, tag: str, file_path: Path) -> float:
        """
        Calculate confidence score for a specific tag.

        Args:
            tag: The tag to score
            file_path: The file to score against

        Returns:
            Confidence score (0-100)
        """
        confidence_scores = []

        # Content-based confidence
        content_tags = self.content_analyzer.analyze_file(file_path)
        if tag in content_tags:
            confidence_scores.append(70.0)

        # Behavior-based confidence
        file_ext = file_path.suffix.lower()
        predicted_tags = self.learning_engine.predict_tags(file_path)
        for predicted_tag, conf in predicted_tags:
            if predicted_tag == tag:
                confidence_scores.append(conf)

        if not confidence_scores:
            return 0.0

        # Return average
        return sum(confidence_scores) / len(confidence_scores)

    def explain_tag(
        self,
        tag: str,
        file_path: Path,
        existing_tags: Optional[list[str]] = None
    ) -> str:
        """
        Generate detailed explanation for why a tag was suggested.

        Args:
            tag: The tag to explain
            file_path: The file
            existing_tags: Tags already applied

        Returns:
            Human-readable explanation
        """
        explanations = []

        # Check content analysis
        content_tags = self.content_analyzer.analyze_file(file_path)
        if tag in content_tags:
            explanations.append(
                f"Found in file content or metadata"
            )

        # Check file type patterns
        file_ext = file_path.suffix.lower()
        if file_ext in self.learning_engine.file_type_tags:
            type_tags = self.learning_engine.file_type_tags[file_ext]
            if tag in type_tags:
                count = type_tags[tag]
                explanations.append(
                    f"You've used this tag {count} times with {file_ext} files"
                )

        # Check directory patterns
        directory = str(file_path.parent)
        if directory in self.learning_engine.directory_tags:
            dir_tags = self.learning_engine.directory_tags[directory]
            if tag in dir_tags:
                count = dir_tags[tag]
                explanations.append(
                    f"You've used this tag {count} times in this directory"
                )

        # Check related tags
        if existing_tags:
            related = self.learning_engine.get_related_tags(tag)
            overlap = set(related) & set(existing_tags)
            if overlap:
                explanations.append(
                    f"Often used with: {', '.join(overlap)}"
                )

        if not explanations:
            return "Suggested based on file analysis"

        return " • ".join(explanations)

    def _get_content_suggestions(
        self,
        file_path: Path
    ) -> list[tuple[str, float]]:
        """Get suggestions from content analysis."""
        try:
            # Get keywords with scores
            keywords = self.content_analyzer.extract_keywords(file_path, top_n=10)

            # Normalize scores to 0-100 range
            if not keywords:
                return []

            max_score = max(score for _, score in keywords)
            if max_score == 0:
                return []

            normalized = [
                (tag, (score / max_score) * 80)  # Max 80% from content
                for tag, score in keywords
            ]

            return normalized

        except Exception as e:
            logger.debug(f"Error getting content suggestions: {e}")
            return []

    def _get_behavior_suggestions(
        self,
        file_path: Path,
        existing_tags: list[str]
    ) -> list[tuple[str, float]]:
        """Get suggestions from learned behavior."""
        try:
            file_ext = file_path.suffix.lower()
            directory = str(file_path.parent)

            # Get context-based suggestions
            suggestions = self.learning_engine.get_tag_suggestions_for_context(
                file_type=file_ext,
                directory=directory,
                existing_tags=existing_tags,
                limit=10
            )

            return suggestions

        except Exception as e:
            logger.debug(f"Error getting behavior suggestions: {e}")
            return []

    def _get_related_suggestions(
        self,
        existing_tags: list[str]
    ) -> list[tuple[str, float]]:
        """Get suggestions based on tag relationships."""
        related_tags = {}

        for tag in existing_tags:
            related = self.learning_engine.get_related_tags(tag, max_related=5)
            for related_tag in related:
                # Confidence based on co-occurrence
                if tag in self.learning_engine.tag_cooccurrence:
                    count = self.learning_engine.tag_cooccurrence[tag][related_tag]
                    total = self.learning_engine.tag_usage[tag].count
                    confidence = (count / total) * 100 if total > 0 else 50
                    related_tags[related_tag] = max(
                        related_tags.get(related_tag, 0),
                        confidence
                    )

        return list(related_tags.items())

    def _combine_confidences(
        self,
        conf1: float,
        conf2: float,
        source1: str,
        source2: str
    ) -> float:
        """Combine confidence scores from different sources."""
        # Weighted average based on source types
        weight1 = self.source_weights.get(source1, 0.5)
        weight2 = self.source_weights.get(source2, 0.5)

        # Normalize weights
        total_weight = weight1 + weight2
        weight1 /= total_weight
        weight2 /= total_weight

        combined = (conf1 * weight1) + (conf2 * weight2)

        # Boost combined score slightly (both sources agree)
        boost = min(10, (conf1 + conf2) / 10)

        return min(combined + boost, 100.0)

    def _rank_suggestions(
        self,
        suggestions: list[TagSuggestion]
    ) -> list[TagSuggestion]:
        """Rank suggestions by confidence and source."""
        # Source priority: hybrid > behavior > content
        source_priority = {
            'hybrid': 3,
            'behavior': 2,
            'content': 1
        }

        return sorted(
            suggestions,
            key=lambda s: (s.confidence, source_priority.get(s.source, 0)),
            reverse=True
        )

    def _generate_content_reasoning(self, tag: str, file_path: Path) -> str:
        """Generate reasoning for content-based suggestion."""
        return f"Found in {file_path.name} content or metadata"

    def _generate_behavior_reasoning(self, tag: str, file_path: Path) -> str:
        """Generate reasoning for behavior-based suggestion."""
        file_ext = file_path.suffix.lower()
        return f"Based on your tagging patterns for {file_ext} files"

    def _generate_hybrid_reasoning(self, tag: str, file_path: Path) -> str:
        """Generate reasoning for hybrid suggestion."""
        return f"Found in content and matches your usage patterns"
