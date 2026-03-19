"""PARA Heuristics Engine.

Multi-factor heuristic detection system for automatic PARA categorization.
Uses temporal, content, structural, and AI-based heuristics.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    ollama = None  # type: ignore[assignment]
    OLLAMA_AVAILABLE = False

from ..categories import PARACategory
from ..config import AIHeuristicConfig, CategoryThresholds

logger = logging.getLogger(__name__)


@dataclass
class CategoryScore:
    """Score for a PARA category."""

    category: PARACategory
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    signals: list[str] = field(default_factory=list)  # What triggered this score

    def __post_init__(self) -> None:
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
    abstained: bool = False


class Heuristic(ABC):
    """Base class for all heuristics."""

    def __init__(self, weight: float = 1.0):
        """Initialize heuristic.

        Args:
            weight: Weight of this heuristic in final scoring (0.0 to 1.0)
        """
        self.weight = weight

    @abstractmethod
    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
        """Evaluate file and return category scores.

        Args:
            file_path: Path to file to evaluate
            metadata: Optional pre-extracted metadata

        Returns:
            HeuristicResult with category scores
        """
        pass


class TemporalHeuristic(Heuristic):
    """Temporal heuristic using file timestamps and patterns.

    Signals:
    - Recent activity (last 30 days) → PROJECT
    - Regular access pattern → AREA
    - Old, untouched files → ARCHIVE
    - Creation vs modification gap → categorization hints
    - Old year patterns in path (e.g., "2020") → ARCHIVE
    """

    @staticmethod
    def _contains_old_year(path_str: str, current_year: int, threshold_years: int = 3) -> bool:
        """Check if path contains old year patterns (folders named like "2020").

        Args:
            path_str: Path string to check
            current_year: Current year
            threshold_years: Years before current year to consider "old"

        Returns:
            True if path contains year older than threshold
        """
        import re

        # Match standalone 4-digit years (word boundaries)
        year_pattern = r"\b(19\d{2}|20\d{2})\b"
        matches = re.findall(year_pattern, path_str)

        for year_str in matches:
            year = int(year_str)
            # Consider years from threshold_years ago and older as archive indicators
            if year <= current_year - threshold_years:
                return True
        return False

    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
        """Evaluate based on temporal patterns."""
        import time
        from datetime import UTC, datetime

        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        if not file_path.exists():
            return HeuristicResult(scores, 0.0, None, True)

        stat = file_path.stat()
        now = time.time()
        current_year = datetime.now(UTC).year

        # Calculate time differences
        days_since_modified = (now - stat.st_mtime) / 86400
        days_since_accessed = (now - stat.st_atime) / 86400
        # Cross-platform file age: use birth time if available (macOS/Windows),
        # fall back to modification time on Linux (st_ctime is inode change time, not creation).
        if hasattr(stat, "st_birthtime"):  # macOS
            ref_time = stat.st_birthtime
        elif os.name == "nt":  # Windows
            ref_time = stat.st_ctime
        else:  # Linux — use mtime as best proxy for "last active"
            ref_time = stat.st_mtime
        days_since_created = (now - ref_time) / 86400

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
            metadata={"temporal_analysis": "complete"},
        )


class ContentHeuristic(Heuristic):
    """Content-based heuristic using filename and path patterns.

    Signals:
    - Deadline/date patterns → PROJECT
    - Recurring keywords → AREA
    - Reference terms → RESOURCE
    - "Old", "backup", "archive" → ARCHIVE
    """

    # Keyword patterns for each category
    PROJECT_KEYWORDS = [
        "project",
        "deadline",
        "due",
        "sprint",
        "milestone",
        "deliverable",
        "proposal",
        "presentation",
        "report",
        "draft",
        "final",
        "v1",
        "v2",
    ]

    AREA_KEYWORDS = [
        "area",
        "ongoing",
        "recurring",
        "weekly",
        "monthly",
        "routine",
        "maintenance",
        "health",
        "finance",
        "learning",
        "notes",
    ]

    RESOURCE_KEYWORDS = [
        "reference",
        "template",
        "guide",
        "tutorial",
        "documentation",
        "handbook",
        "manual",
        "example",
        "sample",
        "resource",
        "library",
    ]

    ARCHIVE_KEYWORDS = [
        "archive",
        "old",
        "backup",
        "deprecated",
        "obsolete",
        "legacy",
        "completed",
        "finished",
        "done",
        "past",
        "historical",
    ]

    @staticmethod
    def _matches_keyword(keyword: str, text: str) -> bool:
        r"""Check if keyword matches in text using word boundaries.

        Prevents false positives like "project" matching "projection".
        Uses regex word boundaries (\b) for accurate matching.

        Args:
            keyword: The keyword to search for
            text: The text to search in (already lowercased)

        Returns:
            True if keyword matches as a complete word
        """
        # Escape special regex characters and add word boundaries
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
        """Evaluate based on content patterns."""
        scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}

        # Analyze filename and path
        full_path = str(file_path).lower()
        filename = file_path.name.lower()

        # Check for date patterns (PROJECT indicator)
        import re

        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",  # 2024-01-15
            r"\d{2}/\d{2}/\d{4}",  # 01/15/2024
            r"due[_-]?\d{2}",  # due_15
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
            metadata={"content_analysis": "complete"},
        )


class StructuralHeuristic(Heuristic):
    """Structural heuristic using directory hierarchy and organization.

    Signals:
    - Deep nesting in project folders → PROJECT
    - Top-level ongoing directories → AREA
    - Organized reference libraries → RESOURCE
    - Archive folders → ARCHIVE
    """

    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
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
            metadata={"structural_analysis": "complete"},
        )


class AIHeuristic(Heuristic):
    """AI-powered heuristic using Ollama for semantic PARA classification.

    Uses a local LLM via Ollama to analyze file content and classify it
    into PARA categories. Static PARA methodology instructions are passed
    via the ``system`` role; dynamic file context (path, name, content)
    is passed via the ``prompt`` role. Gracefully degrades when Ollama is
    unavailable by returning neutral (zero) scores.
    """

    # Confidence damping factor — prevents the AI heuristic from
    # dominating when other heuristics are uncertain.
    _CONFIDENCE_DAMPING: float = 0.8

    _SYSTEM_MESSAGE: str = (
        "You are a file organization assistant using the PARA methodology.\n"
        "Classify the following file into PARA categories by assigning a score "
        "to each category.\n\n"
        "Categories:\n"
        "- PROJECT: Time-bound efforts with specific goals, deadlines, or deliverables\n"
        "- AREA: Ongoing responsibilities requiring continuous maintenance (no end date)\n"
        "- RESOURCE: Reference materials, knowledge, and information for future use\n"
        "- ARCHIVE: Inactive or completed items no longer actively used\n\n"
        "Respond with ONLY a JSON object (no markdown, no explanation):\n"
        '{"project": 0.0, "area": 0.0, "resource": 0.0, "archive": 0.0, '
        '"reasoning": "brief explanation"}\n\n'
        "Rules:\n"
        "- Scores must sum to approximately 1.0\n"
        "- Each score must be between 0.0 and 1.0\n"
        "- Base your assessment on the file content, name, and path\n"
    )

    _USER_TEMPLATE: str = (
        "File path: {file_path}\n"
        "File name: {file_name}\n"
        "File extension: {file_ext}\n\n"
        "Content preview:\n{content}\n"
    )

    def __init__(self, weight: float = 1.0, config: AIHeuristicConfig | None = None) -> None:
        """Initialize AI heuristic.

        Args:
            weight: Weight of this heuristic in final scoring (0.0 to 1.0)
            config: AI heuristic configuration. Uses defaults if not provided.
        """
        super().__init__(weight=weight)
        self.config = config or AIHeuristicConfig()
        self._client: Any = None
        self._available: bool | None = None
        self._init_lock = threading.Lock()

    def _ensure_client(self) -> bool:
        """Lazily create the Ollama client (thread-safe).

        Uses a double-check locking pattern so the Ollama connectivity test
        runs at most once per instance even under concurrent access.

        Returns:
            True if client is available, False otherwise.
        """
        if self._available is not None:
            return self._available

        with self._init_lock:
            # Re-check after acquiring the lock in case another thread already
            # completed initialization while this thread was waiting.
            if self._available is not None:
                return self._available

            if not OLLAMA_AVAILABLE:
                self._available = False
                return False

            try:
                self._client = ollama.Client(
                    host=self.config.ollama_url,
                    timeout=self.config.timeout,
                )
                self._client.list()
                self._available = True
            except Exception:
                logger.warning("Ollama unavailable at %s", self.config.ollama_url, exc_info=True)
                self._available = False

        return self._available

    def _extract_content(self, file_path: Path, metadata: dict[str, Any] | None) -> str:
        """Extract text content from a file for the classification prompt.

        For text-readable files, reads the first ``max_content_chars``
        characters. For binary or unreadable files, returns a summary
        built from the file path and any supplied metadata.

        Args:
            file_path: Path to the file.
            metadata: Optional pre-extracted metadata dict.

        Returns:
            A string suitable for inclusion in the LLM prompt.
        """
        try:
            with file_path.open("rb") as f:
                raw = f.read(self.config.max_content_chars)
            # Fast path: valid UTF-8 is text regardless of byte values.
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Not valid UTF-8 — count low control bytes (null + non-whitespace
                # controls) as binary indicators.  Bytes ≥ 128 are NOT counted here
                # because they appear in Latin-1 and other single-byte encodings
                # that may still be human-readable.
                non_text = sum(1 for b in raw if b == 0 or (b < 32 and b not in (9, 10, 13)))
                if raw and non_text / len(raw) > 0.30:
                    raise ValueError("binary content") from None
                content = raw.decode("utf-8", errors="replace")
            if content.strip():
                return content
        except (OSError, ValueError):
            pass

        # Fallback: describe the file from path and metadata
        parts = [f"[Binary or unreadable file: {file_path.name}]"]
        if metadata:
            for key, value in metadata.items():
                parts.append(f"{key}: {value}")
        return "\n".join(parts)

    def _build_prompt(self, file_path: Path, content: str) -> str:
        """Build the per-file user message for PARA classification.

        Contains only dynamic, file-specific context (path, name, extension,
        content preview). The static PARA methodology instructions are passed
        separately via ``_SYSTEM_MESSAGE`` in the ``system`` kwarg of
        ``ollama.Client.generate()``.

        Args:
            file_path: Path to the file being classified.
            content: Extracted text content or metadata summary.

        Returns:
            The formatted user message string containing file-specific context.
        """
        return self._USER_TEMPLATE.format(
            file_path=file_path,
            file_name=file_path.name,
            file_ext=file_path.suffix or "(none)",
            content=content,
        )

    def _parse_response(self, response_text: str) -> dict[str, Any] | None:
        """Parse LLM response into category scores.

        Handles responses wrapped in markdown code fences and normalises
        scores so they sum to 1.0.

        Args:
            response_text: Raw text from the LLM.

        Returns:
            Dict with keys ``project``, ``area``, ``resource``, ``archive``
            (float) and ``reasoning`` (str), or ``None`` on parse failure.
        """
        # Locate the outermost JSON object in the response, regardless of
        # whether the LLM wrapped it in markdown code fences or prose.
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        text = response_text[start : end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        categories = ["project", "area", "resource", "archive"]
        if not all(cat in data for cat in categories):
            return None

        # Validate and clamp scores
        scores: dict[str, Any] = {}
        for cat in categories:
            try:
                val = float(data[cat])
            except (TypeError, ValueError):
                return None
            scores[cat] = max(0.0, min(1.0, val))

        # Normalise so scores sum to 1.0
        total = sum(scores[cat] for cat in categories)
        if total > 0:
            for cat in categories:
                scores[cat] = scores[cat] / total

        scores["reasoning"] = str(data.get("reasoning", ""))
        return scores

    @staticmethod
    def _zero_result(metadata_reason: str) -> HeuristicResult:
        """Return a neutral (all-zero) result with the given metadata reason.

        Sets ``abstained=True`` so the engine excludes this heuristic's weight
        from the denominator and avoids diluting scores from other heuristics.
        """
        return HeuristicResult(
            scores={cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory},
            overall_confidence=0.0,
            recommended_category=None,
            needs_manual_review=True,
            metadata={"ai_analysis": metadata_reason},
            abstained=True,
        )

    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
        """Evaluate a file using Ollama LLM semantic analysis.

        Calls the configured Ollama model with the file content and a PARA
        classification prompt. On any failure (Ollama not installed, server
        unavailable, malformed response), returns neutral zero scores so that
        the heuristic pipeline is never blocked.

        Args:
            file_path: Path to the file to evaluate.
            metadata: Optional pre-extracted metadata.

        Returns:
            HeuristicResult with per-category scores from the LLM.
        """
        if not OLLAMA_AVAILABLE:
            logger.debug("ollama package not installed — skipping AI heuristic")
            return self._zero_result("ollama_not_installed")

        if not self._ensure_client():
            return self._zero_result("ollama_unavailable")

        content = self._extract_content(file_path, metadata)
        prompt = self._build_prompt(file_path, content)

        try:
            response = self._client.generate(
                model=self.config.model,
                system=self._SYSTEM_MESSAGE,
                prompt=prompt,
                options={
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
                stream=False,
            )
            response_text: str = response.get("response", "") or ""
        except Exception:
            logger.warning("Ollama generate failed", exc_info=True)
            return self._zero_result("ollama_error")

        parsed = self._parse_response(response_text)
        if parsed is None:
            logger.warning(
                "Failed to parse AI heuristic response from model %s (response length: %d)",
                self.config.model,
                len(response_text),
            )
            return self._zero_result("parse_error")

        # Map parsed scores to CategoryScore objects.
        # Derive the key → category mapping from PARACategory.value so that
        # if the enum gains or renames values the map stays in sync.
        category_map: dict[str, PARACategory] = {cat.value: cat for cat in PARACategory}
        reasoning = parsed.get("reasoning", "")
        max_key = max(category_map, key=lambda k: parsed[k])
        max_score = parsed[max_key]
        confidence = max_score * self._CONFIDENCE_DAMPING

        scores: dict[PARACategory, CategoryScore] = {}
        for key, para_cat in category_map.items():
            signals = [f"AI: {reasoning}"] if key == max_key and reasoning else []
            scores[para_cat] = CategoryScore(
                category=para_cat,
                score=parsed[key],
                confidence=confidence,
                signals=signals,
            )

        sorted_scores = sorted(scores.values(), key=lambda s: s.score, reverse=True)
        recommended = sorted_scores[0].category if sorted_scores[0].score > 0.3 else None

        return HeuristicResult(
            scores=scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=confidence < 0.5,
            metadata={"ai_analysis": "complete"},
        )


class HeuristicEngine:
    """Main heuristic engine that combines multiple heuristics.

    Scoring methodology:
    1. Each heuristic provides category scores (0-1)
    2. Scores are weighted by heuristic weight
    3. Final score = weighted average across all heuristics
    4. Confidence = (top_score - second_score) / top_score
    """

    # Default auto-categorization thresholds (used when no config is provided)
    _DEFAULT_THRESHOLDS = CategoryThresholds()

    def __init__(
        self,
        enable_temporal: bool = True,
        enable_content: bool = True,
        enable_structural: bool = True,
        enable_ai: bool = False,
        thresholds: CategoryThresholds | None = None,
        ai_config: AIHeuristicConfig | None = None,
    ):
        """Initialize heuristic engine.

        Args:
            enable_temporal: Enable temporal heuristic
            enable_content: Enable content heuristic
            enable_structural: Enable structural heuristic
            enable_ai: Enable AI heuristic
            thresholds: Category-specific confidence thresholds; uses
                ``CategoryThresholds`` defaults when not provided.
            ai_config: Configuration for the AI heuristic. Uses defaults
                when not provided.
        """
        self._thresholds = thresholds or self._DEFAULT_THRESHOLDS
        self.heuristics: list[Heuristic] = []

        if enable_temporal:
            self.heuristics.append(TemporalHeuristic(weight=0.25))

        if enable_content:
            self.heuristics.append(ContentHeuristic(weight=0.35))

        if enable_structural:
            self.heuristics.append(StructuralHeuristic(weight=0.30))

        if enable_ai:
            self.heuristics.append(AIHeuristic(weight=0.10, config=ai_config))

    @property
    def THRESHOLDS(self) -> dict[PARACategory, float]:
        """Backwards-compatible public accessor returning thresholds as a dict.

        Returns a mapping from each PARACategory to its minimum confidence
        threshold, matching the original class-level ``THRESHOLDS`` dict API.
        """
        return {
            PARACategory.PROJECT: self._thresholds.project,
            PARACategory.AREA: self._thresholds.area,
            PARACategory.RESOURCE: self._thresholds.resource,
            PARACategory.ARCHIVE: self._thresholds.archive,
        }

    def evaluate(self, file_path: Path, metadata: dict[str, Any] | None = None) -> HeuristicResult:
        """Evaluate file using all enabled heuristics.

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

        # Combine scores using weighted average.
        # Heuristics that abstained (e.g. AI when Ollama is unavailable) are
        # excluded from the denominator so they don't dilute other scores.
        combined_scores = {cat: CategoryScore(cat, 0.0, 0.0) for cat in PARACategory}
        active_results = [(h, r) for h, r in results if not r.abstained]
        total_weight = sum(h.weight for h, _ in active_results) or sum(h.weight for h, _ in results)

        for heuristic, result in results:
            if result.abstained:
                continue
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
        thresholds_map = self.THRESHOLDS
        recommended: PARACategory | None = None
        for cat_score in scores_list:
            if cat_score.score >= thresholds_map[cat_score.category]:
                recommended = cat_score.category
                break

        # Check if manual review needed
        needs_review = confidence < 0.60 or recommended is None

        return HeuristicResult(
            scores=combined_scores,
            overall_confidence=confidence,
            recommended_category=recommended,
            needs_manual_review=needs_review,
            metadata={"combined_analysis": "complete"},
        )
