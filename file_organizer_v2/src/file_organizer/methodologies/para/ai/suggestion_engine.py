"""
PARA Suggestion Engine

Combines heuristic analysis, feature extraction, and optional AI models
to produce intelligent PARA categorization suggestions. Designed to work
entirely offline with no cloud dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..categories import PARACategory
from ..config import PARAConfig
from ..detection.heuristics import HeuristicEngine, HeuristicResult
from .feature_extractor import FeatureExtractor, MetadataFeatures, StructuralFeatures, TextFeatures

logger = logging.getLogger(__name__)

# Confidence level thresholds
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.60
CONFIDENCE_LOW = 0.40


def _confidence_label(confidence: float) -> str:
    """Return a human-readable label for a confidence value.

    Args:
        confidence: Confidence score between 0.0 and 1.0.

    Returns:
        One of "High", "Medium", "Low", or "Very Low".
    """
    if confidence >= CONFIDENCE_HIGH:
        return "High"
    if confidence >= CONFIDENCE_MEDIUM:
        return "Medium"
    if confidence >= CONFIDENCE_LOW:
        return "Low"
    return "Very Low"


@dataclass
class PARASuggestion:
    """A PARA categorization suggestion for a file.

    Attributes:
        category: The recommended PARA category.
        confidence: Confidence score (0.0 to 1.0).
        reasoning: List of reasons supporting this suggestion.
        alternative_categories: Ranked alternatives with confidence scores.
        suggested_subfolder: Optional subfolder name within the category.
        tags: Descriptive tags for the file.
        metadata: Additional metadata about the suggestion.
    """

    category: PARACategory
    confidence: float
    reasoning: list[str] = field(default_factory=list)
    alternative_categories: list[tuple[PARACategory, float]] = field(default_factory=list)
    suggested_subfolder: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate suggestion fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def confidence_label(self) -> str:
        """Human-readable confidence level."""
        return _confidence_label(self.confidence)

    @property
    def is_confident(self) -> bool:
        """Whether this suggestion meets the high confidence threshold."""
        return self.confidence >= CONFIDENCE_HIGH

    @property
    def requires_review(self) -> bool:
        """Whether this suggestion should be reviewed by the user."""
        return self.confidence < CONFIDENCE_MEDIUM


class PARASuggestionEngine:
    """Engine that produces PARA categorization suggestions for files.

    Combines multiple signals -- heuristic scores, text features, metadata
    features, and structural features -- to recommend the best PARA category.
    Optionally integrates with a local LLM for enhanced understanding, but
    works fully without one.

    Example::

        config = PARAConfig()
        engine = PARASuggestionEngine(config)
        suggestion = engine.suggest(Path("/path/to/meeting-notes.md"))
        print(suggestion.category, suggestion.confidence_label)
    """

    def __init__(
        self,
        config: PARAConfig | None = None,
        heuristic_engine: HeuristicEngine | None = None,
        feature_extractor: FeatureExtractor | None = None,
    ) -> None:
        """Initialize the suggestion engine.

        Args:
            config: PARA configuration. Uses defaults if not provided.
            heuristic_engine: Pre-configured heuristic engine. Created from
                config if not provided.
            feature_extractor: Feature extractor instance. Created with
                defaults if not provided.
        """
        self._config = config or PARAConfig()
        self._heuristic_engine = heuristic_engine or HeuristicEngine(
            enable_temporal=self._config.enable_temporal_heuristic,
            enable_content=self._config.enable_content_heuristic,
            enable_structural=self._config.enable_structural_heuristic,
            enable_ai=self._config.enable_ai_heuristic,
        )
        self._feature_extractor = feature_extractor or FeatureExtractor()

    def suggest(
        self,
        file_path: Path,
        content: str | None = None,
    ) -> PARASuggestion:
        """Generate a PARA categorization suggestion for a single file.

        Runs heuristic analysis and feature extraction, then combines the
        signals to produce a ranked suggestion.

        Args:
            file_path: Path to the file to categorize.
            content: Optional text content of the file. If not provided,
                only filename/metadata-based analysis is performed.

        Returns:
            PARASuggestion with the recommended category and reasoning.
        """
        reasoning: list[str] = []
        tags: list[str] = []

        # Step 1: Run heuristic engine
        heuristic_result = self._run_heuristics(file_path)
        heuristic_scores = {cat: score.score for cat, score in heuristic_result.scores.items()}
        heuristic_signals = {cat: score.signals for cat, score in heuristic_result.scores.items()}

        # Step 2: Extract features
        text_features: TextFeatures | None = None
        if content:
            text_features = self._feature_extractor.extract_text_features(content)

        metadata_features = self._feature_extractor.extract_metadata_features(file_path)
        structural_features = self._feature_extractor.extract_structural_features(file_path)

        # Step 3: Compute feature-based scores
        feature_scores = self._compute_feature_scores(
            text_features,
            metadata_features,
            structural_features,
        )

        # Step 4: Combine scores with configurable weights
        combined_scores = self._combine_scores(heuristic_scores, feature_scores)

        # Step 5: Select best category
        sorted_categories = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        best_category = sorted_categories[0][0]
        best_score = sorted_categories[0][1]

        # Clamp confidence
        confidence = max(0.0, min(1.0, best_score))

        # Build reasoning
        reasoning.extend(
            self._build_reasoning(
                best_category,
                heuristic_signals,
                text_features,
                metadata_features,
                structural_features,
            )
        )

        # Build alternative categories
        alternatives: list[tuple[PARACategory, float]] = [
            (cat, max(0.0, min(1.0, score))) for cat, score in sorted_categories[1:] if score > 0.1
        ]

        # Suggest subfolder
        suggested_subfolder = self._suggest_subfolder(
            best_category,
            file_path,
            text_features,
        )

        # Build tags
        if text_features:
            tags.extend(text_features.keywords[:5])
        if metadata_features.file_type:
            tags.append(metadata_features.file_type.lstrip("."))

        return PARASuggestion(
            category=best_category,
            confidence=confidence,
            reasoning=reasoning,
            alternative_categories=alternatives,
            suggested_subfolder=suggested_subfolder,
            tags=sorted(set(tags)),
            metadata={
                "heuristic_scores": {cat.value: s for cat, s in heuristic_scores.items()},
                "feature_scores": {cat.value: s for cat, s in feature_scores.items()},
                "combined_scores": {cat.value: s for cat, s in combined_scores.items()},
                "confidence_label": _confidence_label(confidence),
            },
        )

    def suggest_batch(self, file_paths: list[Path]) -> list[PARASuggestion]:
        """Generate suggestions for multiple files.

        Args:
            file_paths: List of file paths to categorize.

        Returns:
            List of PARASuggestion objects, one per file.
        """
        suggestions: list[PARASuggestion] = []
        for path in file_paths:
            try:
                suggestion = self.suggest(path)
                suggestions.append(suggestion)
            except Exception as e:
                logger.error("Failed to generate suggestion for %s: %s", path, e)
                # Return a low-confidence fallback
                suggestions.append(
                    PARASuggestion(
                        category=PARACategory.RESOURCE,
                        confidence=0.1,
                        reasoning=[f"Error during analysis: {e}"],
                    )
                )
        return suggestions

    def explain(self, suggestion: PARASuggestion) -> str:
        """Generate a human-readable explanation of a suggestion.

        Args:
            suggestion: The suggestion to explain.

        Returns:
            A formatted string explaining the suggestion.
        """
        lines: list[str] = [
            f"Recommended category: {suggestion.category.value.title()}",
            f"Confidence: {suggestion.confidence:.0%} ({suggestion.confidence_label})",
            "",
            "Reasoning:",
        ]

        for i, reason in enumerate(suggestion.reasoning, 1):
            lines.append(f"  {i}. {reason}")

        if suggestion.alternative_categories:
            lines.append("")
            lines.append("Alternatives:")
            for alt_cat, alt_score in suggestion.alternative_categories:
                lines.append(
                    f"  - {alt_cat.value.title()}: {alt_score:.0%} ({_confidence_label(alt_score)})"
                )

        if suggestion.suggested_subfolder:
            lines.append("")
            lines.append(f"Suggested subfolder: {suggestion.suggested_subfolder}")

        if suggestion.tags:
            lines.append("")
            lines.append(f"Tags: {', '.join(suggestion.tags)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_heuristics(self, file_path: Path) -> HeuristicResult:
        """Run the heuristic engine on a file path.

        Args:
            file_path: Path to the file.

        Returns:
            HeuristicResult from the engine.
        """
        try:
            return self._heuristic_engine.evaluate(file_path)
        except Exception as e:
            logger.error("Heuristic evaluation failed for %s: %s", file_path, e)
            from ..detection.heuristics import CategoryScore

            return HeuristicResult(
                scores={cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory},
                overall_confidence=0.0,
                needs_manual_review=True,
            )

    def _compute_feature_scores(
        self,
        text_features: TextFeatures | None,
        metadata_features: MetadataFeatures,
        structural_features: StructuralFeatures,
    ) -> dict[PARACategory, float]:
        """Compute per-category scores from extracted features.

        Args:
            text_features: Text analysis results (may be None).
            metadata_features: File metadata results.
            structural_features: Path structure results.

        Returns:
            Dictionary mapping each PARACategory to a feature-based score.
        """
        scores: dict[PARACategory, float] = dict.fromkeys(PARACategory, 0.0)

        # --- Text-based signals ---
        if text_features:
            kw_counts = text_features.category_keyword_counts
            total_kw = sum(kw_counts.values()) or 1

            # Distribute scores proportionally
            cat_name_map = {
                "project": PARACategory.PROJECT,
                "area": PARACategory.AREA,
                "resource": PARACategory.RESOURCE,
                "archive": PARACategory.ARCHIVE,
            }
            for name, cat in cat_name_map.items():
                if name in kw_counts and kw_counts[name] > 0:
                    scores[cat] += min(0.4, (kw_counts[name] / total_kw) * 0.6)

            # Temporal indicators boost PROJECT
            if text_features.temporal_indicators:
                scores[PARACategory.PROJECT] += min(
                    0.2,
                    len(text_features.temporal_indicators) * 0.04,
                )

            # Action items boost PROJECT
            if text_features.action_items:
                scores[PARACategory.PROJECT] += min(
                    0.15,
                    len(text_features.action_items) * 0.03,
                )

            # Document type hints
            doc_type = text_features.document_type
            if doc_type in ("plan", "proposal", "presentation"):
                scores[PARACategory.PROJECT] += 0.1
            elif doc_type in ("notes",):
                scores[PARACategory.AREA] += 0.05
            elif doc_type in ("reference", "template"):
                scores[PARACategory.RESOURCE] += 0.1

        # --- Metadata-based signals ---
        days_mod = metadata_features.days_since_modified

        if days_mod < 30:
            scores[PARACategory.PROJECT] += 0.1
        elif 30 <= days_mod <= 180:
            scores[PARACategory.AREA] += 0.05
        elif days_mod > 180:
            scores[PARACategory.ARCHIVE] += 0.15

        if metadata_features.access_frequency > 0.7:
            scores[PARACategory.PROJECT] += 0.05
        elif metadata_features.access_frequency < 0.2 and days_mod > 90:
            scores[PARACategory.ARCHIVE] += 0.1

        # --- Structural signals ---
        hint = structural_features.parent_category_hint
        if hint:
            cat_map = {
                "project": PARACategory.PROJECT,
                "area": PARACategory.AREA,
                "resource": PARACategory.RESOURCE,
                "archive": PARACategory.ARCHIVE,
            }
            if hint in cat_map:
                scores[cat_map[hint]] += 0.25

        if structural_features.has_project_structure:
            scores[PARACategory.PROJECT] += 0.1

        if structural_features.has_date_in_path:
            scores[PARACategory.PROJECT] += 0.05

        return scores

    def _combine_scores(
        self,
        heuristic_scores: dict[PARACategory, float],
        feature_scores: dict[PARACategory, float],
    ) -> dict[PARACategory, float]:
        """Combine heuristic and feature scores using weighted averaging.

        The heuristic engine already applies its own internal weighting.
        Here we blend the overall heuristic result with feature extraction
        at a 60/40 ratio.

        Args:
            heuristic_scores: Scores from the heuristic engine.
            feature_scores: Scores from feature extraction.

        Returns:
            Combined scores per category.
        """
        heuristic_weight = 0.60
        feature_weight = 0.40

        combined: dict[PARACategory, float] = {}
        for cat in PARACategory:
            h_score = heuristic_scores.get(cat, 0.0)
            f_score = feature_scores.get(cat, 0.0)
            combined[cat] = h_score * heuristic_weight + f_score * feature_weight

        return combined

    def _build_reasoning(
        self,
        best_category: PARACategory,
        heuristic_signals: dict[PARACategory, list[str]],
        text_features: TextFeatures | None,
        metadata_features: MetadataFeatures,
        structural_features: StructuralFeatures,
    ) -> list[str]:
        """Build a list of reasoning strings for the suggestion.

        Args:
            best_category: The recommended category.
            heuristic_signals: Signals from heuristic analysis per category.
            text_features: Text analysis results.
            metadata_features: File metadata.
            structural_features: Path structure analysis.

        Returns:
            List of reasoning strings.
        """
        reasons: list[str] = []

        # Heuristic-based reasons
        signals = heuristic_signals.get(best_category, [])
        if signals:
            reasons.append(f"Heuristic analysis detected: {', '.join(signals[:5])}")

        # Text-based reasons
        if text_features:
            kw_counts = text_features.category_keyword_counts
            cat_name = best_category.value
            if kw_counts.get(cat_name, 0) > 0:
                reasons.append(
                    f"Content contains {kw_counts[cat_name]} {cat_name}-related keywords"
                )

            if best_category == PARACategory.PROJECT and text_features.temporal_indicators:
                reasons.append(
                    f"Found {len(text_features.temporal_indicators)} "
                    f"temporal references suggesting time-bound work"
                )

            if best_category == PARACategory.PROJECT and text_features.action_items:
                reasons.append(f"Found {len(text_features.action_items)} action items")

        # Metadata reasons
        days = metadata_features.days_since_modified
        if days > 0:
            if best_category == PARACategory.PROJECT and days < 30:
                reasons.append("File was recently modified (active work)")
            elif best_category == PARACategory.ARCHIVE and days > 180:
                reasons.append(f"File has not been modified in {int(days)} days")

        # Structural reasons
        if structural_features.parent_category_hint:
            reasons.append(
                f"Parent directory suggests '{structural_features.parent_category_hint}'"
            )
        if structural_features.has_project_structure:
            reasons.append("Directory contains project structure indicators")

        if not reasons:
            reasons.append(f"Best match based on combined analysis: {best_category.value}")

        return reasons

    def _suggest_subfolder(
        self,
        category: PARACategory,
        file_path: Path,
        text_features: TextFeatures | None,
    ) -> str | None:
        """Suggest a subfolder name within the selected category.

        Args:
            category: The selected PARA category.
            file_path: Original file path.
            text_features: Text features (used for document type).

        Returns:
            Suggested subfolder name or None.
        """
        # Use document type as subfolder hint for resources
        if category == PARACategory.RESOURCE and text_features:
            doc_type = text_features.document_type
            if doc_type != "unknown":
                return doc_type.title() + "s"

        # Use parent directory name as subfolder for projects/areas
        if category in (PARACategory.PROJECT, PARACategory.AREA):
            parent_name = file_path.parent.name
            if parent_name and parent_name not in (".", "/", "~"):
                return parent_name

        return None
