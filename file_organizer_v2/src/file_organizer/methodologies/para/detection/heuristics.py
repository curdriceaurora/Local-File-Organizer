"""
PARA Heuristics Engine

Multi-factor heuristic detection system for automatic PARA categorization.
Uses temporal, content, structural, and AI-based heuristics.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..categories import PARACategory

logger = logging.getLogger(__name__)


@dataclass
class CategoryScore:
    """Score for a PARA category."""
    category: PARACategory
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    signals: list[str] = field(default_factory=list)  # What triggered this score

    def __post_init__(self):
        """Validate score and confidence are in valid range [0.0, 1.0]."""
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"Score must be in range [0.0, 1.0], got {self.score} for {self.category.value}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Confidence must be in range [0.0, 1.0], got {self.confidence} for {self.category.value}"
            )


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
    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
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
    - Recent activity (last 30 days) → PROJECT
    - Regular access pattern → AREA
    - Old, untouched files → ARCHIVE
    - Creation vs modification gap → categorization hints
    - Old year patterns in path (e.g., "2020") → ARCHIVE
    """

    @staticmethod
    def _contains_old_year(path_str: str, current_year: int, threshold_years: int = 3) -> bool:
        """
        Check if path contains old year patterns (folders named like "2020").

        Args:
            path_str: Path string to check
            current_year: Current year
            threshold_years: Years before current year to consider "old"

        Returns:
            True if path contains year older than threshold
        """
        import re
        # Match standalone 4-digit years (word boundaries)
        year_pattern = r'\b(19\d{2}|20\d{2})\b'
        matches = re.findall(year_pattern, path_str)

        for year_str in matches:
            year = int(year_str)
            # Consider years from threshold_years ago and older as archive indicators
            if year <= current_year - threshold_years:
                return True
        return False

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
        """Evaluate based on temporal patterns."""
        import time
        from datetime import datetime

        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        if not file_path.exists():
            return HeuristicResult(scores, 0.0, None, True)

        stat = file_path.stat()
        now = time.time()
        current_year = datetime.now().year

        # Calculate time differences
        days_since_modified = (now - stat.st_mtime) / 86400
        days_since_accessed = (now - stat.st_atime) / 86400
        days_since_created = (now - stat.st_ctime) / 86400

        # Check for old year patterns in path (e.g., "/Projects/2020/...")
        if self._contains_old_year(str(file_path), current_year):
            scores[PARACategory.ARCHIVE].score += 0.4
            scores[PARACategory.ARCHIVE].signals.append("old_year_in_path")

        # PROJECT signals: recent activity (< 30 days)
        if days_since_modified < 30:
            scores[PARACategory.PROJECT].score += 0.4
            scores[PARACategory.PROJECT].signals.append("recently_modified")

        # AREA signals: regular but not too recent
        if 30 <= days_since_modified <= 180:
            scores[PARACategory.AREA].score += 0.3
            scores[PARACategory.AREA].signals.append("moderate_age")

        # RESOURCE signals: stable, not frequently modified
        if days_since_modified > 60 and abs(days_since_created - days_since_modified) > 30:
            scores[PARACategory.RESOURCE].score += 0.3
            scores[PARACategory.RESOURCE].signals.append("stable_reference")

        # ARCHIVE signals: old and untouched
        if days_since_modified > 180 and days_since_accessed > 90:
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

    # Keyword patterns for each category
    PROJECT_KEYWORDS = [
        "project", "deadline", "due", "sprint", "milestone", "deliverable",
        "proposal", "presentation", "report", "draft", "final", "v1", "v2"
    ]

    AREA_KEYWORDS = [
        "area", "ongoing", "recurring", "weekly", "monthly", "routine",
        "maintenance", "health", "finance", "learning", "notes"
    ]

    RESOURCE_KEYWORDS = [
        "reference", "template", "guide", "tutorial", "documentation",
        "handbook", "manual", "example", "sample", "resource", "library"
    ]

    ARCHIVE_KEYWORDS = [
        "archive", "old", "backup", "deprecated", "obsolete", "legacy",
        "completed", "finished", "done", "past", "historical"
    ]

    @staticmethod
    def _matches_keyword(keyword: str, text: str) -> bool:
        """
        Check if keyword matches in text using word boundaries.

        Prevents false positives like "project" matching "projection".
        Uses regex word boundaries (\\b) for accurate matching.

        Args:
            keyword: The keyword to search for
            text: The text to search in (already lowercased)

        Returns:
            True if keyword matches as a complete word
        """
        # Escape special regex characters and add word boundaries
        pattern = r'\b' + re.escape(keyword) + r'\b'
        return bool(re.search(pattern, text, re.IGNORECASE))

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
        """Evaluate based on content patterns."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        # Analyze filename and path
        full_path = str(file_path).lower()
        filename = file_path.name.lower()

        # Check for date patterns (PROJECT indicator)
        import re
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

        # Keyword matching with word boundaries
        for keyword in self.PROJECT_KEYWORDS:
            if self._matches_keyword(keyword, full_path):
                scores[PARACategory.PROJECT].score += 0.2
                scores[PARACategory.PROJECT].signals.append(f"keyword:{keyword}")

        for keyword in self.AREA_KEYWORDS:
            if self._matches_keyword(keyword, full_path):
                scores[PARACategory.AREA].score += 0.2
                scores[PARACategory.AREA].signals.append(f"keyword:{keyword}")

        for keyword in self.RESOURCE_KEYWORDS:
            if self._matches_keyword(keyword, full_path):
                scores[PARACategory.RESOURCE].score += 0.2
                scores[PARACategory.RESOURCE].signals.append(f"keyword:{keyword}")

        for keyword in self.ARCHIVE_KEYWORDS:
            if self._matches_keyword(keyword, full_path):
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

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
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
        """Evaluate using AI (placeholder for future implementation)."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        # TODO: Implement AI-based evaluation using Ollama
        # This would involve:
        # 1. Extract file content or metadata
        # 2. Generate semantic embedding
        # 3. Compare with PARA category embeddings
        # 4. Return similarity scores

        logger.info("AI heuristic not yet implemented")

        return HeuristicResult(
            scores=scores,
            overall_confidence=0.0,
            recommended_category=None,
            needs_manual_review=True,
            metadata={"ai_analysis": "not_implemented"}
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

    # Auto-categorization thresholds
    THRESHOLDS = {
        PARACategory.PROJECT: 0.75,
        PARACategory.AREA: 0.75,
        PARACategory.RESOURCE: 0.80,
        PARACategory.ARCHIVE: 0.90,  # High bar for auto-archiving
    }

    def __init__(
        self,
        enable_temporal: bool = True,
        enable_content: bool = True,
        enable_structural: bool = True,
        enable_ai: bool = False,
    ):
        """
        Initialize heuristic engine.

        Args:
            enable_temporal: Enable temporal heuristic
            enable_content: Enable content heuristic
            enable_structural: Enable structural heuristic
            enable_ai: Enable AI heuristic
        """
        self.heuristics: list[Heuristic] = []

        if enable_temporal:
            self.heuristics.append(TemporalHeuristic(weight=0.25))

        if enable_content:
            self.heuristics.append(ContentHeuristic(weight=0.35))

        if enable_structural:
            self.heuristics.append(StructuralHeuristic(weight=0.30))

        if enable_ai:
            self.heuristics.append(AIHeuristic(weight=0.10))

    def evaluate(self, file_path: Path, metadata: dict | None = None) -> HeuristicResult:
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
        # Formula: confidence = (top_score - second_score) / top_score
        # This measures how much better the top category is than the second
        scores_list = sorted(combined_scores.values(), key=lambda x: x.score, reverse=True)
        top_score = scores_list[0].score
        second_score = scores_list[1].score if len(scores_list) > 1 else 0.0

        if top_score > 0:
            # Use documented formula with clamping
            confidence = (top_score - second_score) / top_score
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0.0, 1.0]
        else:
            confidence = 0.0

        # Update individual confidences
        for score in combined_scores.values():
            score.confidence = confidence

        # Determine recommendation based on thresholds
        recommended = None
        for category in scores_list:
            if category.score >= self.THRESHOLDS[category.category]:
                recommended = category.category
                break

        # Check if manual review needed
        needs_review = confidence < 0.60 or recommended is None

        return HeuristicResult(
            scores=combined_scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=needs_review,
            metadata={"combined_analysis": "complete"}
        )
