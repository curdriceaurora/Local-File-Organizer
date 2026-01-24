"""
PARA Heuristics Engine

Multi-factor heuristic detection system for automatic PARA categorization.
Uses temporal, content, structural, and AI-based heuristics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, Optional, Union
import logging
import re
import time

from ..categories import PARACategory
from ..config import PARAConfig, TemporalThresholds

logger = logging.getLogger(__name__)


@dataclass
class CategoryScore:
    """Score for a PARA category."""
    category: PARACategory
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    signals: list[str] = field(default_factory=list)  # What triggered this score


@dataclass
class HeuristicResult:
    """Result from a heuristic evaluation."""
    scores: dict[PARACategory, CategoryScore]
    overall_confidence: float
    recommended_category: PARACategory | None = None
    needs_manual_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Heuristic(ABC):
    """Base class for all heuristics."""

    def __init__(self, weight: float = 1.0):
        """
        Initialize heuristic.

        Args:
            weight: Weight of this heuristic in final scoring (0.0 to 1.0)
        """
        self.weight = weight

    @abstractmethod
    def evaluate(self, file_path: Path, metadata: Dict | None = None) -> HeuristicResult:
        """
        Evaluate file and return category scores.

        Args:
            file_path: Path to file to evaluate
            metadata: Optional pre-extracted metadata

        Returns:
            HeuristicResult with category scores
        """
        pass


class TemporalHeuristic(Heuristic):
    """
    Temporal heuristic using file timestamps and patterns.

    Signals:
    - Recent activity (configurable threshold) → PROJECT
    - Regular access pattern → AREA
    - Old, untouched files → ARCHIVE
    - Creation vs modification gap → categorization hints
    """

    def __init__(self, weight: float = 1.0, temporal_thresholds: TemporalThresholds | None = None):
        """
        Initialize temporal heuristic.

        Args:
            weight: Weight of this heuristic in final scoring (0.0 to 1.0)
            temporal_thresholds: Temporal thresholds configuration (None = defaults)
        """
        super().__init__(weight)
        self.thresholds = temporal_thresholds or TemporalThresholds()

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
        """Evaluate based on temporal patterns."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        if not file_path.exists():
            return HeuristicResult(scores, 0.0, None, True)

        stat = file_path.stat()
        now = time.time()

        # Get creation time (platform-specific)
        # On Unix: st_ctime is change time, not creation time
        # On macOS/BSD: st_birthtime is actual creation time
        # On Windows: st_ctime is creation time
        try:
            creation_time = stat.st_birthtime  # macOS/BSD
        except AttributeError:
            creation_time = stat.st_ctime  # Windows fallback

        # Calculate time differences
        days_since_modified = (now - stat.st_mtime) / 86400
        days_since_accessed = (now - stat.st_atime) / 86400
        days_since_created = (now - creation_time) / 86400

        # PROJECT signals: recent activity
        if days_since_modified < self.thresholds.project_max_age:
            scores[PARACategory.PROJECT].score += 0.4
            scores[PARACategory.PROJECT].signals.append("recently_modified")

        # AREA signals: regular but not too recent
        if self.thresholds.area_min_age <= days_since_modified <= self.thresholds.area_max_age:
            scores[PARACategory.AREA].score += 0.3
            scores[PARACategory.AREA].signals.append("moderate_age")

        # RESOURCE signals: stable, not frequently modified
        if days_since_modified > self.thresholds.resource_min_age and abs(days_since_created - days_since_modified) > self.thresholds.project_max_age:
            scores[PARACategory.RESOURCE].score += 0.3
            scores[PARACategory.RESOURCE].signals.append("stable_reference")

        # ARCHIVE signals: old and untouched
        if days_since_modified > self.thresholds.archive_min_age and days_since_accessed > self.thresholds.archive_min_inactive:
            scores[PARACategory.ARCHIVE].score += 0.5
            scores[PARACategory.ARCHIVE].signals.append("old_untouched")

        # Calculate confidence based on signal strength
        max_score = max(s.score for s in scores.values())
        confidence = min(max_score, 1.0) if max_score > 0 else 0.3

        for score in scores.values():
            score.confidence = confidence

        # Determine recommendation
        sorted_scores = sorted(scores.values(), key=lambda x: x.score, reverse=True)
        recommended = sorted_scores[0].category if sorted_scores[0].score > 0.2 else None

        return HeuristicResult(
            scores=scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=confidence < 0.5,
            metadata={"temporal_analysis": "complete"}
        )


class ContentHeuristic(Heuristic):
    """
    Content-based heuristic using filename and path patterns.

    Signals:
    - Deadline/date patterns → PROJECT
    - Recurring keywords → AREA
    - Reference terms → RESOURCE
    - "Old", "backup", "archive" → ARCHIVE
    """

    # Default keyword patterns (used as fallback)
    DEFAULT_PROJECT_KEYWORDS: ClassVar[list[str]] = [
        "project", "deadline", "due", "sprint", "milestone", "deliverable",
        "proposal", "presentation", "report", "draft", "final", "v1", "v2"
    ]

    DEFAULT_AREA_KEYWORDS: ClassVar[list[str]] = [
        "area", "ongoing", "recurring", "weekly", "monthly", "routine",
        "maintenance", "health", "finance", "learning", "notes"
    ]

    DEFAULT_RESOURCE_KEYWORDS: ClassVar[list[str]] = [
        "reference", "template", "guide", "tutorial", "documentation",
        "handbook", "manual", "example", "sample", "resource", "library"
    ]

    DEFAULT_ARCHIVE_KEYWORDS: ClassVar[list[str]] = [
        "archive", "old", "backup", "deprecated", "obsolete", "legacy",
        "completed", "finished", "done", "past", "historical"
    ]

    def __init__(self, weight: float = 1.0, config: PARAConfig | None = None):
        """
        Initialize content heuristic.

        Args:
            weight: Weight of this heuristic in final scoring (0.0 to 1.0)
            config: PARA configuration for keyword patterns (None = defaults)
        """
        super().__init__(weight)
        self.config = config or PARAConfig()

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
        """Evaluate based on content patterns."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        # Analyze filename and path
        full_path = str(file_path).lower()
        filename = file_path.name.lower()

        # Check for date patterns (PROJECT indicator)
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # 2024-01-15
            r'\d{2}/\d{2}/\d{4}',  # 01/15/2024
            r'due[_-]?\d{2}',      # due_15
        ]

        for pattern in date_patterns:
            if re.search(pattern, filename):
                scores[PARACategory.PROJECT].score += 0.3
                scores[PARACategory.PROJECT].signals.append("date_pattern")
                break

        # Keyword matching using config or defaults
        project_keywords = self.config.get_category_keywords(PARACategory.PROJECT)
        for keyword in project_keywords:
            if keyword in full_path:
                scores[PARACategory.PROJECT].score += 0.2
                scores[PARACategory.PROJECT].signals.append(f"keyword:{keyword}")

        area_keywords = self.config.get_category_keywords(PARACategory.AREA)
        for keyword in area_keywords:
            if keyword in full_path:
                scores[PARACategory.AREA].score += 0.2
                scores[PARACategory.AREA].signals.append(f"keyword:{keyword}")

        resource_keywords = self.config.get_category_keywords(PARACategory.RESOURCE)
        for keyword in resource_keywords:
            if keyword in full_path:
                scores[PARACategory.RESOURCE].score += 0.2
                scores[PARACategory.RESOURCE].signals.append(f"keyword:{keyword}")

        archive_keywords = self.config.get_category_keywords(PARACategory.ARCHIVE)
        for keyword in archive_keywords:
            if keyword in full_path:
                scores[PARACategory.ARCHIVE].score += 0.3
                scores[PARACategory.ARCHIVE].signals.append(f"keyword:{keyword}")

        # Normalize scores
        for score in scores.values():
            score.score = min(score.score, 1.0)

        # Calculate confidence
        max_score = max(s.score for s in scores.values())
        confidence = max_score if max_score > 0 else 0.3

        for score in scores.values():
            score.confidence = confidence

        # Recommendation
        sorted_scores = sorted(scores.values(), key=lambda x: x.score, reverse=True)
        recommended = sorted_scores[0].category if sorted_scores[0].score > 0.3 else None

        return HeuristicResult(
            scores=scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=confidence < 0.5,
            metadata={"content_analysis": "complete"}
        )


class StructuralHeuristic(Heuristic):
    """
    Structural heuristic using directory hierarchy and organization.

    Signals:
    - Deep nesting in project folders → PROJECT
    - Top-level ongoing directories → AREA
    - Organized reference libraries → RESOURCE
    - Archive folders → ARCHIVE
    """

    def evaluate(self, file_path: Path, metadata: Dict | None = None) -> HeuristicResult:
        """Evaluate based on file structure."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        # Analyze path structure
        parts = file_path.parts
        depth = len(parts)

        # Check parent directory names
        parent_names = [p.lower() for p in parts[:-1]]

        # PROJECT: typically in dated or specific project folders
        if depth > 3:  # Deeper nesting
            scores[PARACategory.PROJECT].score += 0.2
            scores[PARACategory.PROJECT].signals.append("deep_nesting")

        # AREA: often in top-level category folders
        area_indicators = ["areas", "ongoing", "active", "current"]
        if any(ind in parent_names for ind in area_indicators):
            scores[PARACategory.AREA].score += 0.4
            scores[PARACategory.AREA].signals.append("area_directory")

        # RESOURCE: in reference/library structures
        resource_indicators = ["resources", "references", "library", "docs", "templates"]
        if any(ind in parent_names for ind in resource_indicators):
            scores[PARACategory.RESOURCE].score += 0.4
            scores[PARACategory.RESOURCE].signals.append("resource_directory")

        # ARCHIVE: in archive/old folders
        archive_indicators = ["archive", "archives", "old", "past", "completed"]
        if any(ind in parent_names for ind in archive_indicators):
            scores[PARACategory.ARCHIVE].score += 0.5
            scores[PARACategory.ARCHIVE].signals.append("archive_directory")

        # Calculate confidence
        max_score = max(s.score for s in scores.values())
        confidence = max_score if max_score > 0 else 0.3

        for score in scores.values():
            score.confidence = confidence

        # Recommendation
        sorted_scores = sorted(scores.values(), key=lambda x: x.score, reverse=True)
        recommended = sorted_scores[0].category if sorted_scores[0].score > 0.3 else None

        return HeuristicResult(
            scores=scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=confidence < 0.5,
            metadata={"structural_analysis": "complete"}
        )


class AIHeuristic(Heuristic):
    """
    AI-powered heuristic using semantic analysis.

    This is a placeholder for future AI integration.
    Can use local LLMs via Ollama for semantic understanding.
    """

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
        """Evaluate using AI (not yet implemented).

        Raises:
            NotImplementedError: AI heuristic is not yet implemented
        """
        raise NotImplementedError(
            "AI heuristic is not yet implemented. "
            "This will use local LLMs via Ollama for semantic understanding. "
            "Set enable_ai_heuristic=False in PARAConfig to disable this heuristic."
        )


class HeuristicEngine:
    """
    Main heuristic engine that combines multiple heuristics.

    Scoring methodology:
    1. Each heuristic provides category scores (0-1)
    2. Scores are weighted by heuristic weight
    3. Final score = weighted average across all heuristics
    4. Confidence = (top_score - second_score) / top_score
    """

    def __init__(
        self,
        config: PARAConfig | None = None,
        enable_temporal: bool = True,
        enable_content: bool = True,
        enable_structural: bool = True,
        enable_ai: bool = False,
    ):
        """
        Initialize heuristic engine.

        Args:
            config: PARA configuration (None = defaults)
            enable_temporal: Enable temporal heuristic
            enable_content: Enable content heuristic
            enable_structural: Enable structural heuristic
            enable_ai: Enable AI heuristic
        """
        self.config = config or PARAConfig()
        self.heuristics: list[Heuristic] = []

        if enable_temporal:
            self.heuristics.append(
                TemporalHeuristic(
                    weight=self.config.heuristic_weights.temporal,
                    temporal_thresholds=self.config.temporal_thresholds
                )
            )

        if enable_content:
            self.heuristics.append(
                ContentHeuristic(
                    weight=self.config.heuristic_weights.content,
                    config=self.config
                )
            )

        if enable_structural:
            self.heuristics.append(
                StructuralHeuristic(weight=self.config.heuristic_weights.structural)
            )

        if enable_ai:
            self.heuristics.append(
                AIHeuristic(weight=self.config.heuristic_weights.ai)
            )

    def evaluate(self, file_path: Path, metadata: Dict | None = None) -> HeuristicResult:
        """
        Evaluate file using all enabled heuristics.

        Args:
            file_path: Path to file
            metadata: Optional pre-extracted metadata

        Returns:
            Combined HeuristicResult
        """
        if not self.heuristics:
            raise ValueError("No heuristics enabled")

        # Run all heuristics
        results = []
        for heuristic in self.heuristics:
            try:
                result = heuristic.evaluate(file_path, metadata)
                results.append((heuristic, result))
            except Exception as e:
                logger.error(f"Heuristic {heuristic.__class__.__name__} failed: {e}")

        if not results:
            # All heuristics failed
            return HeuristicResult(
                scores={cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory},
                overall_confidence=0.0,
                needs_manual_review=True,
            )

        # Combine scores using weighted average
        combined_scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}
        total_weight = sum(h.weight for h, _ in results)

        for heuristic, result in results:
            weight_factor = heuristic.weight / total_weight

            for category, score in result.scores.items():
                combined_scores[category].score += score.score * weight_factor
                combined_scores[category].signals.extend(score.signals)

        # Calculate overall confidence
        scores_list = sorted(combined_scores.values(), key=lambda x: x.score, reverse=True)
        top_score = scores_list[0].score
        second_score = scores_list[1].score if len(scores_list) > 1 else 0.0

        if top_score > 0:
            confidence = (top_score + (top_score - second_score)) / 2.0
        else:
            confidence = 0.0

        # Update individual confidences
        for score in combined_scores.values():
            score.confidence = confidence

        # Determine recommendation based on thresholds
        recommended = None
        for category in scores_list:
            threshold = self.config.get_category_threshold(category.category)
            if category.score >= threshold:
                recommended = category.category
                break

        # Check if manual review needed
        needs_review = confidence < self.config.manual_review_threshold or recommended is None

        return HeuristicResult(
            scores=combined_scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=needs_review,
            metadata={"combined_analysis": "complete"}
        )
