"""
Smart Suggestions Service

Generates intelligent file organization suggestions using AI models
and pattern analysis.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import uuid
import hashlib

from ..models.suggestion_types import (
    Suggestion,
    SuggestionType,
    SuggestionBatch,
    ConfidenceFactors
)
from ..models.text_model import TextModel
from .pattern_analyzer import PatternAnalyzer, PatternAnalysis

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculates confidence scores for suggestions using multiple factors.
    """

    def __init__(self):
        """Initialize the confidence scorer."""
        pass

    def score_suggestion(
        self,
        file_path: Path,
        target_path: Optional[Path],
        suggestion_type: SuggestionType,
        pattern_analysis: Optional[PatternAnalysis] = None,
        user_history: Optional[Dict] = None
    ) -> ConfidenceFactors:
        """
        Calculate confidence score for a suggestion.

        Args:
            file_path: Source file path
            target_path: Target location (for move/restructure)
            suggestion_type: Type of suggestion
            pattern_analysis: Pattern analysis results
            user_history: User's past actions

        Returns:
            ConfidenceFactors with calculated scores
        """
        factors = ConfidenceFactors()

        # Pattern strength
        if pattern_analysis:
            factors.pattern_strength = self._calculate_pattern_strength(
                file_path, pattern_analysis
            )

        # Content similarity (if target exists)
        if target_path and target_path.exists():
            factors.content_similarity = self._calculate_content_similarity(
                file_path, target_path
            )

        # User history
        if user_history:
            factors.user_history = self._calculate_user_history_score(
                file_path, target_path, user_history
            )

        # Naming convention match
        if target_path:
            factors.naming_convention = self._calculate_naming_match(
                file_path, target_path, pattern_analysis
            )

        # File type appropriateness
        if target_path:
            factors.file_type_match = self._calculate_file_type_match(
                file_path, target_path, pattern_analysis
            )

        # Recency factor
        factors.recency = self._calculate_recency_score(file_path)

        # Size appropriateness
        if target_path:
            factors.size_appropriateness = self._calculate_size_score(
                file_path, target_path
            )

        return factors

    def _calculate_pattern_strength(
        self, file_path: Path, analysis: PatternAnalysis
    ) -> float:
        """Calculate how strongly the file matches detected patterns."""
        if not analysis.naming_patterns:
            return 50.0

        # Check if file matches any detected patterns
        filename = file_path.stem
        max_confidence = 0.0

        for pattern in analysis.naming_patterns:
            if any(filename in example for example in pattern.example_files):
                max_confidence = max(max_confidence, pattern.confidence)

        return max_confidence

    def _calculate_content_similarity(
        self, file_path: Path, target_path: Path
    ) -> float:
        """Calculate content similarity between file and target location."""
        # For now, use simple file type matching
        # In a full implementation, this would use AI to analyze content

        if not file_path.suffix:
            return 30.0

        # Check if target directory has similar file types
        target_dir = target_path if target_path.is_dir() else target_path.parent
        similar_files = list(target_dir.glob(f"*{file_path.suffix}"))

        if not similar_files:
            return 20.0

        # More similar files = higher confidence
        similarity = min(len(similar_files) * 10, 100.0)
        return similarity

    def _calculate_user_history_score(
        self, file_path: Path, target_path: Optional[Path], history: Dict
    ) -> float:
        """Calculate score based on user's past actions."""
        if not target_path:
            return 50.0

        # Check if user has moved similar files to this location before
        file_type = file_path.suffix
        target_str = str(target_path.parent)

        # Look for similar actions in history
        similar_actions = history.get('move_history', {}).get(file_type, {})
        target_count = similar_actions.get(target_str, 0)

        if target_count > 0:
            # User has moved this file type here before
            return min(50 + target_count * 10, 100.0)

        return 40.0

    def _calculate_naming_match(
        self, file_path: Path, target_path: Path, analysis: Optional[PatternAnalysis]
    ) -> float:
        """Calculate naming convention match score."""
        if not analysis:
            return 50.0

        target_dir = target_path if target_path.is_dir() else target_path.parent

        # Find naming patterns in target directory
        target_patterns = [
            p for p in analysis.location_patterns
            if p.directory == target_dir
        ]

        if not target_patterns:
            return 40.0

        # Check if file matches target directory patterns
        pattern_names = target_patterns[0].naming_patterns if target_patterns else []

        # Simple check: does filename follow any pattern?
        if pattern_names:
            return 70.0
        else:
            return 50.0

    def _calculate_file_type_match(
        self, file_path: Path, target_path: Path, analysis: Optional[PatternAnalysis]
    ) -> float:
        """Calculate if file type is appropriate for target location."""
        if not analysis:
            return 50.0

        target_dir = target_path if target_path.is_dir() else target_path.parent
        file_type = file_path.suffix.lower()

        # Find what file types exist in target directory
        target_patterns = [
            p for p in analysis.location_patterns
            if p.directory == target_dir
        ]

        if not target_patterns:
            return 40.0

        # Check if file type matches
        target_types = target_patterns[0].file_types
        if file_type in target_types:
            return 85.0
        elif not target_types:
            return 50.0
        else:
            return 25.0

    def _calculate_recency_score(self, file_path: Path) -> float:
        """Calculate score based on file recency."""
        try:
            mtime = file_path.stat().st_mtime
            age_days = (datetime.now().timestamp() - mtime) / 86400

            # More recent files get slightly higher scores
            if age_days < 7:
                return 60.0
            elif age_days < 30:
                return 55.0
            elif age_days < 90:
                return 50.0
            else:
                return 45.0
        except OSError:
            return 50.0

    def _calculate_size_score(self, file_path: Path, target_path: Path) -> float:
        """Calculate if file size is appropriate for target location."""
        try:
            file_size = file_path.stat().st_size
            target_dir = target_path if target_path.is_dir() else target_path.parent

            # Get sizes of existing files in target
            existing_files = [f for f in target_dir.iterdir() if f.is_file()]
            if not existing_files:
                return 50.0

            existing_sizes = [f.stat().st_size for f in existing_files]
            avg_size = sum(existing_sizes) / len(existing_sizes)

            # Check if file size is similar to existing files
            size_ratio = file_size / avg_size if avg_size > 0 else 1.0

            if 0.5 <= size_ratio <= 2.0:
                return 70.0
            elif 0.1 <= size_ratio <= 10.0:
                return 50.0
            else:
                return 30.0
        except (OSError, ZeroDivisionError):
            return 50.0


class SuggestionEngine:
    """
    Generates intelligent file organization suggestions.
    """

    def __init__(
        self,
        text_model: Optional[TextModel] = None,
        min_confidence: float = 40.0
    ):
        """
        Initialize the suggestion engine.

        Args:
            text_model: AI text model for generating explanations
            min_confidence: Minimum confidence threshold for suggestions
        """
        self.text_model = text_model
        self.min_confidence = min_confidence
        self.pattern_analyzer = PatternAnalyzer()
        self.confidence_scorer = ConfidenceScorer()

    def generate_suggestions(
        self,
        files: List[Path],
        pattern_analysis: Optional[PatternAnalysis] = None,
        user_history: Optional[Dict] = None,
        max_suggestions: int = 50
    ) -> List[Suggestion]:
        """
        Generate suggestions for organizing files.

        Args:
            files: List of files to analyze
            pattern_analysis: Optional pre-computed pattern analysis
            user_history: Optional user action history
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of ranked suggestions
        """
        logger.info(f"Generating suggestions for {len(files)} files")

        if not files:
            return []

        # Analyze patterns if not provided
        if pattern_analysis is None:
            # Get common root directory
            root = self._get_common_root(files)
            pattern_analysis = self.pattern_analyzer.analyze_directory(root)

        suggestions = []

        # Generate different types of suggestions
        suggestions.extend(self._suggest_moves(files, pattern_analysis, user_history))
        suggestions.extend(self._suggest_renames(files, pattern_analysis))
        suggestions.extend(self._suggest_restructures(pattern_analysis))

        # Filter by minimum confidence
        suggestions = [s for s in suggestions if s.confidence >= self.min_confidence]

        # Rank and limit
        ranked_suggestions = self.rank_suggestions(suggestions)

        logger.info(f"Generated {len(ranked_suggestions)} suggestions")
        return ranked_suggestions[:max_suggestions]

    def _suggest_moves(
        self,
        files: List[Path],
        analysis: PatternAnalysis,
        user_history: Optional[Dict]
    ) -> List[Suggestion]:
        """Suggest moving files to better locations."""
        suggestions = []

        for file_path in files:
            # Find best target location based on patterns
            target = self._find_best_location(file_path, analysis)

            if target and target != file_path.parent:
                # Calculate confidence
                factors = self.confidence_scorer.score_suggestion(
                    file_path, target, SuggestionType.MOVE, analysis, user_history
                )
                confidence = factors.calculate_weighted_score()

                # Generate reasoning
                reasoning = self._generate_move_reasoning(file_path, target, factors)

                suggestions.append(Suggestion(
                    suggestion_id=self._generate_id(file_path, target),
                    suggestion_type=SuggestionType.MOVE,
                    file_path=file_path,
                    target_path=target / file_path.name,
                    confidence=confidence,
                    reasoning=reasoning,
                    metadata={'factors': factors.to_dict()}
                ))

        return suggestions

    def _suggest_renames(
        self, files: List[Path], analysis: PatternAnalysis
    ) -> List[Suggestion]:
        """Suggest renaming files to match patterns."""
        suggestions = []

        for file_path in files:
            # Check if filename matches any detected patterns
            new_name = self._suggest_better_name(file_path, analysis)

            if new_name and new_name != file_path.name:
                factors = self.confidence_scorer.score_suggestion(
                    file_path, None, SuggestionType.RENAME, analysis
                )
                confidence = factors.calculate_weighted_score()

                reasoning = f"Rename to match detected naming pattern in this directory"

                suggestions.append(Suggestion(
                    suggestion_id=self._generate_id(file_path, None),
                    suggestion_type=SuggestionType.RENAME,
                    file_path=file_path,
                    new_name=new_name,
                    confidence=confidence,
                    reasoning=reasoning,
                    metadata={'factors': factors.to_dict()}
                ))

        return suggestions

    def _suggest_restructures(self, analysis: PatternAnalysis) -> List[Suggestion]:
        """Suggest restructuring directories."""
        suggestions = []

        # Look for clusters that could be organized better
        for cluster in analysis.content_clusters:
            if len(cluster.file_paths) >= 5 and cluster.confidence > 60:
                # Suggest creating a dedicated directory for this cluster
                target_dir = analysis.directory / cluster.category

                factors = ConfidenceFactors(
                    pattern_strength=cluster.confidence,
                    content_similarity=80.0
                )
                confidence = factors.calculate_weighted_score()

                reasoning = (
                    f"Found {len(cluster.file_paths)} {cluster.category} files "
                    f"that could be organized together. "
                    f"Common keywords: {', '.join(cluster.common_keywords[:3])}"
                )

                # Create a restructure suggestion for the first file as example
                if cluster.file_paths:
                    suggestions.append(Suggestion(
                        suggestion_id=self._generate_id(
                            cluster.file_paths[0], target_dir
                        ),
                        suggestion_type=SuggestionType.RESTRUCTURE,
                        file_path=cluster.file_paths[0],
                        target_path=target_dir,
                        confidence=confidence,
                        reasoning=reasoning,
                        related_files=cluster.file_paths,
                        metadata={
                            'cluster_id': cluster.cluster_id,
                            'factors': factors.to_dict()
                        }
                    ))

        return suggestions

    def rank_suggestions(self, suggestions: List[Suggestion]) -> List[Suggestion]:
        """
        Rank suggestions by confidence and importance.

        Args:
            suggestions: List of suggestions to rank

        Returns:
            Sorted list of suggestions
        """
        # Primary sort: confidence
        # Secondary sort: suggestion type priority
        type_priority = {
            SuggestionType.RESTRUCTURE: 4,
            SuggestionType.MOVE: 3,
            SuggestionType.RENAME: 2,
            SuggestionType.TAG: 1,
            SuggestionType.DELETE: 0
        }

        return sorted(
            suggestions,
            key=lambda s: (s.confidence, type_priority.get(s.suggestion_type, 0)),
            reverse=True
        )

    def explain_suggestion(self, suggestion: Suggestion) -> str:
        """
        Generate detailed explanation for a suggestion.

        Args:
            suggestion: Suggestion to explain

        Returns:
            Human-readable explanation
        """
        explanation_parts = [f"**{suggestion.suggestion_type.value.upper()} Suggestion**"]
        explanation_parts.append(f"Confidence: {suggestion.confidence:.1f}%")
        explanation_parts.append(f"\nReasoning: {suggestion.reasoning}")

        if 'factors' in suggestion.metadata:
            factors = suggestion.metadata['factors']
            explanation_parts.append("\nConfidence Factors:")
            for factor, value in factors.items():
                if factor != 'weights' and factor != 'weighted_score':
                    explanation_parts.append(f"  - {factor}: {value:.1f}%")

        return "\n".join(explanation_parts)

    def _find_best_location(
        self, file_path: Path, analysis: PatternAnalysis
    ) -> Optional[Path]:
        """Find the best location for a file based on patterns."""
        file_type = file_path.suffix.lower()

        # Look for location patterns with matching file types
        candidates = [
            p for p in analysis.location_patterns
            if file_type in p.file_types and p.directory != file_path.parent
        ]

        if not candidates:
            return None

        # Return the location with most files (strongest pattern)
        best_location = max(candidates, key=lambda p: p.file_count)
        return best_location.directory

    def _suggest_better_name(
        self, file_path: Path, analysis: PatternAnalysis
    ) -> Optional[str]:
        """Suggest a better name for the file based on patterns."""
        # Find patterns in the file's directory
        dir_patterns = [
            p for p in analysis.location_patterns
            if p.directory == file_path.parent
        ]

        if not dir_patterns or not dir_patterns[0].naming_patterns:
            return None

        # For now, return None (would need more sophisticated logic)
        # In full implementation, this would use AI to suggest names
        return None

    def _generate_move_reasoning(
        self, file_path: Path, target: Path, factors: ConfidenceFactors
    ) -> str:
        """Generate human-readable reasoning for move suggestion."""
        reasons = []

        if factors.pattern_strength > 60:
            reasons.append("matches organizational pattern")

        if factors.file_type_match > 60:
            reasons.append("file type fits target location")

        if factors.content_similarity > 60:
            reasons.append("similar files already exist there")

        if factors.user_history > 60:
            reasons.append("you've moved similar files there before")

        if not reasons:
            reasons.append("would improve organization")

        return f"Move to {target.name} - " + ", ".join(reasons)

    def _generate_id(self, file_path: Path, target: Optional[Path]) -> str:
        """Generate unique ID for suggestion."""
        content = f"{file_path}{target}{datetime.now().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _get_common_root(self, files: List[Path]) -> Path:
        """Get common root directory for files."""
        if not files:
            return Path.cwd()

        # Get all parent directories
        parents = [f.parent for f in files]

        # Find common ancestor
        common = parents[0]
        for parent in parents[1:]:
            try:
                common = Path(*common.parts[:len(common.parts)])
                while common not in parent.parents and common != parent:
                    common = common.parent
            except (ValueError, IndexError):
                common = Path.cwd()
                break

        return common
