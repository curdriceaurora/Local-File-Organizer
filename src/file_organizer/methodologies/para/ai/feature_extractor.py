"""
Feature Extraction for PARA Smart Suggestions

Extracts text, metadata, and structural features from files to support
intelligent PARA categorization. All analysis is performed locally
without any cloud API dependencies.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Temporal indicator patterns that suggest time-bound work (PROJECT signals)
_TEMPORAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),  # 2024-01-15, 2024/1/15
    re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}", re.I),
    re.compile(r"\bdue\s+(?:date|by)\b", re.I),
    re.compile(r"\bdeadline\b", re.I),
    re.compile(r"\bQ[1-4]\s+\d{4}\b"),  # Q1 2024
    re.compile(r"\b(?:sprint|milestone|phase)\s*\d+\b", re.I),
    re.compile(r"\b(?:week|month|year)\s+(?:of|ending)\b", re.I),
]

# Action item patterns that suggest active work
_ACTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*[-*]\s*\[\s*[xX ]?\s*\]", re.MULTILINE),  # Checkboxes
    re.compile(r"\bTODO\b", re.I),
    re.compile(r"\bFIXME\b", re.I),
    re.compile(r"\bACTION\s*(?:ITEM|REQUIRED)?\b", re.I),
    re.compile(r"\b(?:need|needs)\s+to\b", re.I),
    re.compile(r"\b(?:should|must|shall)\s+\w+", re.I),
    re.compile(r"\bassigned\s+to\b", re.I),
]

# Document type indicators
_DOCUMENT_TYPE_MAP: dict[str, list[str]] = {
    "report": ["report", "summary", "findings", "analysis", "review"],
    "proposal": ["proposal", "rfp", "bid", "pitch"],
    "plan": ["plan", "roadmap", "strategy", "schedule", "timeline"],
    "notes": ["notes", "minutes", "memo", "journal", "log"],
    "reference": ["reference", "guide", "manual", "handbook", "documentation"],
    "template": ["template", "boilerplate", "scaffold", "starter"],
    "presentation": ["slides", "presentation", "deck", "keynote"],
    "spreadsheet": ["budget", "tracker", "ledger", "inventory"],
    "code": ["script", "module", "library", "package", "source"],
    "creative": ["draft", "manuscript", "essay", "article", "blog"],
}

# Category keywords for content analysis
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "project": [
        "deadline",
        "milestone",
        "deliverable",
        "sprint",
        "goal",
        "project plan",
        "due date",
        "completion",
        "task list",
        "proposal",
        "campaign",
        "launch",
        "initiative",
        "prototype",
        "mvp",
        "release",
        "version",
        "iteration",
    ],
    "area": [
        "ongoing",
        "maintenance",
        "routine",
        "checklist",
        "regular",
        "continuous",
        "process",
        "standard",
        "recurring",
        "daily",
        "weekly",
        "monthly",
        "management",
        "operations",
        "relationship",
        "health",
        "finance",
        "budget",
        "team",
        "responsibility",
    ],
    "resource": [
        "reference",
        "tutorial",
        "guide",
        "template",
        "documentation",
        "how-to",
        "example",
        "learning",
        "research",
        "article",
        "manual",
        "handbook",
        "resource",
        "knowledge",
        "info",
        "cheatsheet",
        "glossary",
        "faq",
        "best practices",
    ],
    "archive": [
        "final",
        "completed",
        "archived",
        "old",
        "legacy",
        "deprecated",
        "obsolete",
        "historical",
        "past",
        "inactive",
        "finished",
        "done",
        "closed",
        "ended",
        "retired",
        "superseded",
        "outdated",
    ],
}


@dataclass
class TextFeatures:
    """Features extracted from text content of a file.

    Attributes:
        keywords: Important keywords found in the content.
        temporal_indicators: Date/time references found (deadline signals).
        action_items: Actionable items found (TODO, checkboxes, etc.).
        document_type: Detected document type (report, plan, notes, etc.).
        word_count: Total word count of the content.
        category_keyword_counts: Count of keywords per PARA category.
    """

    keywords: list[str] = field(default_factory=list)
    temporal_indicators: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    document_type: str = "unknown"
    word_count: int = 0
    category_keyword_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class MetadataFeatures:
    """Features extracted from file system metadata.

    Attributes:
        creation_date: When the file was created.
        modification_date: When the file was last modified.
        file_size: Size in bytes.
        file_type: File extension (e.g., ".pdf", ".docx").
        access_frequency: Estimated access frequency based on atime/mtime ratio.
        days_since_modified: Days since last modification.
        days_since_created: Days since creation.
    """

    creation_date: datetime | None = None
    modification_date: datetime | None = None
    file_size: int = 0
    file_type: str = ""
    access_frequency: float = 0.0
    days_since_modified: float = 0.0
    days_since_created: float = 0.0


@dataclass
class StructuralFeatures:
    """Features extracted from file path and directory structure.

    Attributes:
        directory_depth: How deeply nested the file is.
        sibling_count: Number of files in the same directory.
        parent_category_hint: PARA category hint from parent directory name.
        path_keywords: Keywords found in the file path.
        has_project_structure: Whether the parent looks like a project folder.
        has_date_in_path: Whether the path contains date patterns.
    """

    directory_depth: int = 0
    sibling_count: int = 0
    parent_category_hint: str | None = None
    path_keywords: list[str] = field(default_factory=list)
    has_project_structure: bool = False
    has_date_in_path: bool = False


class FeatureExtractor:
    """Extracts features from files for PARA categorization.

    This class provides methods to analyze file content, metadata, and
    directory structure to produce feature sets that inform PARA category
    suggestions. All analysis is local and privacy-preserving.

    Example::

        extractor = FeatureExtractor()
        text_features = extractor.extract_text_features("Meeting notes from Q1 sprint...")
        metadata_features = extractor.extract_metadata_features(Path("/path/to/file.md"))
        structural_features = extractor.extract_structural_features(Path("/path/to/file.md"))
    """

    def __init__(self, max_content_length: int = 50_000) -> None:
        """Initialize the feature extractor.

        Args:
            max_content_length: Maximum content length to analyze (truncates beyond).
        """
        self._max_content_length = max_content_length

    def extract_text_features(self, content: str) -> TextFeatures:
        """Extract features from text content.

        Analyzes the provided text to identify keywords, temporal indicators,
        action items, document type, and word count.

        Args:
            content: The text content to analyze.

        Returns:
            TextFeatures with extracted information.
        """
        if not content or not content.strip():
            return TextFeatures()

        # Truncate if too long
        truncated = content[: self._max_content_length]
        content_lower = truncated.lower()

        # Word count
        words = truncated.split()
        word_count = len(words)

        # Extract temporal indicators
        temporal_indicators: list[str] = []
        for pattern in _TEMPORAL_PATTERNS:
            matches = pattern.findall(truncated)
            temporal_indicators.extend(matches[:5])  # Cap per pattern

        # Extract action items
        action_items: list[str] = []
        for pattern in _ACTION_PATTERNS:
            matches = pattern.findall(truncated)
            for match in matches[:10]:
                cleaned = match.strip()
                if cleaned and len(cleaned) < 200:
                    action_items.append(cleaned)

        # Count category keywords
        category_keyword_counts: dict[str, int] = {}
        all_found_keywords: list[str] = []
        for category, kw_list in _CATEGORY_KEYWORDS.items():
            count = 0
            for kw in kw_list:
                occurrences = content_lower.count(kw.lower())
                if occurrences > 0:
                    count += occurrences
                    all_found_keywords.append(kw)
            category_keyword_counts[category] = count

        # Detect document type
        document_type = self._detect_document_type(content_lower)

        return TextFeatures(
            keywords=sorted(set(all_found_keywords))[:30],
            temporal_indicators=temporal_indicators[:15],
            action_items=action_items[:20],
            document_type=document_type,
            word_count=word_count,
            category_keyword_counts=category_keyword_counts,
        )

    def extract_metadata_features(self, file_path: Path) -> MetadataFeatures:
        """Extract features from file system metadata.

        Reads file stat information to determine creation/modification dates,
        file size, type, and estimated access frequency.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            MetadataFeatures with extracted information.
        """
        if not file_path.exists():
            logger.warning("File does not exist: %s", file_path)
            return MetadataFeatures(file_type=file_path.suffix.lower())

        try:
            stat = file_path.stat()
        except OSError as e:
            logger.error("Cannot stat file %s: %s", file_path, e)
            return MetadataFeatures(file_type=file_path.suffix.lower())

        now = time.time()

        # Cross-platform file creation time:
        #   macOS  → st_birthtime (true birth time)
        #   Windows → st_ctime    (creation time on NTFS)
        #   Linux  → st_mtime     (st_ctime is inode-change time, not creation)
        if hasattr(stat, "st_birthtime"):  # macOS
            creation_ref = stat.st_birthtime
        elif os.name == "nt":  # Windows
            creation_ref = stat.st_ctime
        else:  # Linux — use mtime as best available proxy
            creation_ref = stat.st_mtime

        # Convert timestamps to datetime
        creation_date = datetime.fromtimestamp(creation_ref, tz=UTC)
        modification_date = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

        # Days calculations
        days_since_modified = (now - stat.st_mtime) / 86400.0
        days_since_created = (now - creation_ref) / 86400.0

        # Access frequency estimate: ratio of access recency to modification recency
        # Higher value = more frequently accessed relative to modification
        if days_since_modified > 0:
            days_since_accessed = (now - stat.st_atime) / 86400.0
            access_frequency = max(
                0.0,
                1.0 - (days_since_accessed / max(days_since_modified, 1.0)),
            )
        else:
            access_frequency = 1.0

        return MetadataFeatures(
            creation_date=creation_date,
            modification_date=modification_date,
            file_size=stat.st_size,
            file_type=file_path.suffix.lower(),
            access_frequency=min(access_frequency, 1.0),
            days_since_modified=days_since_modified,
            days_since_created=days_since_created,
        )

    def extract_structural_features(self, file_path: Path) -> StructuralFeatures:
        """Extract features from file path and directory structure.

        Analyzes the directory hierarchy, sibling files, and path naming
        conventions to infer structural PARA signals.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            StructuralFeatures with extracted information.
        """
        parts = file_path.parts
        depth = len(parts) - 1  # Subtract filename itself

        # Count siblings
        sibling_count = 0
        parent_dir = file_path.parent
        if parent_dir.exists() and parent_dir.is_dir():
            try:
                sibling_count = sum(1 for f in parent_dir.iterdir() if f.is_file()) - 1
            except OSError:
                sibling_count = 0

        # Detect parent category hint
        parent_category_hint = self._detect_parent_category(parts)

        # Extract path keywords
        path_str = str(file_path).lower()
        path_keywords: list[str] = []
        for _category, kw_list in _CATEGORY_KEYWORDS.items():
            for kw in kw_list:
                if kw.lower() in path_str:
                    path_keywords.append(kw)

        # Check for project structure indicators
        has_project_structure = self._has_project_structure(parent_dir)

        # Check for date in path
        has_date_in_path = bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", path_str))

        return StructuralFeatures(
            directory_depth=depth,
            sibling_count=max(sibling_count, 0),
            parent_category_hint=parent_category_hint,
            path_keywords=sorted(set(path_keywords)),
            has_project_structure=has_project_structure,
            has_date_in_path=has_date_in_path,
        )

    def _detect_document_type(self, content_lower: str) -> str:
        """Detect the document type from content keywords.

        Args:
            content_lower: Lowercased content string.

        Returns:
            Detected document type string.
        """
        best_type = "unknown"
        best_count = 0

        for doc_type, indicators in _DOCUMENT_TYPE_MAP.items():
            count = sum(1 for ind in indicators if ind in content_lower)
            if count > best_count:
                best_count = count
                best_type = doc_type

        return best_type if best_count >= 1 else "unknown"

    def _detect_parent_category(self, path_parts: tuple[str, ...]) -> str | None:
        """Detect PARA category hints from parent directory names.

        Args:
            path_parts: Tuple of path components.

        Returns:
            Detected category hint or None.
        """
        category_indicators: dict[str, list[str]] = {
            "project": ["projects", "project", "sprints", "initiatives"],
            "area": ["areas", "area", "ongoing", "active", "current"],
            "resource": [
                "resources",
                "resource",
                "references",
                "library",
                "docs",
                "templates",
                "knowledge",
            ],
            "archive": ["archive", "archives", "old", "past", "completed"],
        }

        # Check parent directories (skip the filename)
        for part in reversed(path_parts[:-1]):
            part_lower = part.lower()
            for category, indicators in category_indicators.items():
                if part_lower in indicators:
                    return category

        return None

    def _has_project_structure(self, directory: Path) -> bool:
        """Check if a directory has typical project structure indicators.

        Looks for files like README, TODO, Makefile, package.json, etc.
        that suggest the directory is a project root.

        Args:
            directory: Directory path to check.

        Returns:
            True if the directory appears to be a project.
        """
        if not directory.exists() or not directory.is_dir():
            return False

        project_indicators = {
            "readme",
            "readme.md",
            "readme.txt",
            "todo",
            "todo.md",
            "todo.txt",
            "makefile",
            "dockerfile",
            "package.json",
            "pyproject.toml",
            "setup.py",
            "cargo.toml",
            "go.mod",
            "pom.xml",
            ".git",
            ".gitignore",
            "requirements.txt",
            "gemfile",
        }

        try:
            entries = {entry.name.lower() for entry in directory.iterdir()}
            return bool(entries & project_indicators)
        except OSError:
            return False
