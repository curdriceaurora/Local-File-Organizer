"""Pattern Analyzer Service.

Analyzes file organization patterns including directory structures,
naming conventions, and content-based clustering.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from file_organizer.core.path_guard import safe_walk

logger = logging.getLogger(__name__)


@dataclass
class NamingPattern:
    """Represents a detected file naming pattern."""

    pattern: str
    regex: str
    example_files: list[str]
    count: int
    confidence: float
    description: str


@dataclass
class LocationPattern:
    """Represents a pattern in file locations."""

    directory: Path
    file_types: set[str]
    naming_patterns: list[str]
    file_count: int
    depth_level: int
    category: str | None = None


@dataclass
class ContentCluster:
    """Represents a cluster of files with similar content characteristics."""

    cluster_id: str
    file_paths: list[Path]
    common_keywords: list[str]
    file_types: set[str]
    size_range: tuple[int, int]
    category: str
    confidence: float


@dataclass
class PatternAnalysis:
    """Complete pattern analysis results."""

    directory: Path
    naming_patterns: list[NamingPattern]
    location_patterns: list[LocationPattern]
    content_clusters: list[ContentCluster]
    file_type_distribution: dict[str, int]
    depth_distribution: dict[int, int]
    analyzed_at: datetime
    total_files: int
    metadata: dict[str, Any] = field(default_factory=dict)


class PatternAnalyzer:
    """Analyzes file organization patterns.

    Detects structure, naming conventions, and content-based clusters.
    """

    def __init__(self, min_pattern_count: int = 3, max_depth: int = 10):
        """Initialize the pattern analyzer.

        Args:
            min_pattern_count: Minimum number of files to form a pattern
            max_depth: Maximum directory depth to analyze
        """
        self.min_pattern_count = min_pattern_count
        self.max_depth = max_depth

        # Common naming patterns to detect
        self.common_patterns = [
            (r"^([A-Z]{2,})[_-]", "PREFIX_STYLE"),
            (r"_([0-9]{4}[-_][0-9]{2}[-_][0-9]{2})", "DATE_SUFFIX"),
            (r"^([0-9]{4}[-_][0-9]{2}[-_][0-9]{2})_", "DATE_PREFIX"),
            (r"([vV][0-9]+\.[0-9]+)", "VERSION"),
            (r"_([0-9]{3,})\.", "NUMERIC_SUFFIX"),
            (r"^([0-9]{3,})[-_]", "NUMERIC_PREFIX"),
            (r"([A-Z][a-z]+){2,}", "CAMEL_CASE"),
            (r"([a-z]+_[a-z]+)", "SNAKE_CASE"),
            (r"([a-z]+-[a-z]+)", "KEBAB_CASE"),
        ]

    def analyze_directory(self, directory: Path) -> PatternAnalysis:
        """Perform complete pattern analysis on a directory.

        Args:
            directory: Directory to analyze

        Returns:
            PatternAnalysis with all detected patterns
        """
        logger.info(f"Starting pattern analysis for {directory}")

        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Invalid directory: {directory}")

        # Collect all files
        files = self._collect_files(directory)

        if not files:
            logger.warning(f"No files found in {directory}")
            return PatternAnalysis(
                directory=directory,
                naming_patterns=[],
                location_patterns=[],
                content_clusters=[],
                file_type_distribution={},
                depth_distribution={},
                analyzed_at=datetime.now(UTC),
                total_files=0,
            )

        # Analyze different aspects
        naming_patterns = self.detect_naming_patterns(files)
        location_patterns = self.get_location_patterns(directory)
        content_clusters = self.cluster_by_content(files)
        file_type_dist = self._analyze_file_types(files)
        depth_dist = self._analyze_depth_distribution(files, directory)

        return PatternAnalysis(
            directory=directory,
            naming_patterns=naming_patterns,
            location_patterns=location_patterns,
            content_clusters=content_clusters,
            file_type_distribution=file_type_dist,
            depth_distribution=depth_dist,
            analyzed_at=datetime.now(UTC),
            total_files=len(files),
            metadata={"min_pattern_count": self.min_pattern_count, "max_depth": self.max_depth},
        )

    def _collect_files(self, directory: Path) -> list[Path]:
        """Collect files up to ``max_depth``, using the walk's hidden-path rule.

        Previously this hand-rolled its own traversal and applied a *different*
        definition of "hidden" from :meth:`get_location_patterns`, so one
        ``PatternAnalysis`` carried two rules (#1680):

        - it dot-checked directories only, so hidden **files** such as ``.env``
          were counted in ``total_files`` and ``content_clusters``;
        - the check was leaf-only, so ``root/.cache/visible/`` was skipped here
          but for a different reason than in the other path;
        - symlinks were followed.

        ``safe_walk`` is now the single rule for both. It excludes any path with
        a dot component relative to the root, and skips symlinks — the stricter,
        security-hardened definition, and the one the location analysis has used
        since #1671. Aligning on the looser rule would have meant feeding
        credential-bearing files like ``.ssh/`` into pattern analysis.

        Args:
            directory: Directory to scan

        Returns:
            List of file paths
        """
        # `safe_walk` has no depth parameter, so the bound is applied here.
        # A file directly inside `directory` has one relative part and sits at
        # depth 0, matching the old `current_depth` numbering exactly.
        return [
            path
            for path in safe_walk(directory, only_files=True)
            if len(path.relative_to(directory).parts) - 1 <= self.max_depth
        ]

    def detect_naming_patterns(self, files: list[Path]) -> list[NamingPattern]:
        """Detect naming patterns across files.

        Args:
            files: List of file paths to analyze

        Returns:
            List of detected naming patterns
        """
        logger.info(f"Analyzing naming patterns for {len(files)} files")

        pattern_matches = defaultdict(list)

        # Check each file against common patterns
        for file_path in files:
            filename = file_path.stem

            for pattern_regex, pattern_type in self.common_patterns:
                if re.search(pattern_regex, filename):
                    pattern_matches[pattern_type].append(file_path.name)

        # Build NamingPattern objects
        detected_patterns = []
        for pattern_type, matched_files in pattern_matches.items():
            if len(matched_files) >= self.min_pattern_count:
                # Find the actual regex pattern
                regex = next(r for r, t in self.common_patterns if t == pattern_type)

                confidence = min(len(matched_files) / len(files) * 100, 100.0)

                detected_patterns.append(
                    NamingPattern(
                        pattern=pattern_type,
                        regex=regex,
                        example_files=matched_files[:5],  # Store up to 5 examples
                        count=len(matched_files),
                        confidence=confidence,
                        description=self._get_pattern_description(pattern_type),
                    )
                )

        # Sort by count (most common first)
        detected_patterns.sort(key=lambda p: p.count, reverse=True)

        logger.info(f"Detected {len(detected_patterns)} naming patterns")
        return detected_patterns

    def get_location_patterns(self, directory: Path) -> list[LocationPattern]:
        """Analyze location-based organizational patterns.

        Args:
            directory: Root directory to analyze

        Returns:
            List of location patterns
        """
        logger.info(f"Analyzing location patterns in {directory}")

        location_patterns = []

        # Analyze each subdirectory.
        # only_files=False because this walk wants directories, not files.
        # include_hidden defaults to False, replacing the old
        # `subdir.name.startswith(".")` check — note safe_walk is stricter: it
        # excludes any path with a dot component relative to the root, so a
        # visible directory buried under ".cache/" is no longer analysed.
        for subdir in safe_walk(directory, only_files=False):
            if not subdir.is_dir():
                continue

            # Get files in this directory (non-recursive).
            #
            # `safe_walk`, not `iterdir()`: this enumeration is the THIRD place
            # the analysis decides what counts as hidden, and it was the one
            # left behind. The outer walk above excluded hidden directories and
            # `_collect_files` excluded hidden files, but a raw `iterdir()` here
            # still admitted `docs/.secret` into `file_count`, `file_types` and
            # `naming_patterns` — so `total_files` and `location_patterns`
            # disagreed even after #1680's first pass (caught in review).
            #
            # `recursive=False` keeps this a single-level listing; the hidden
            # check is relative to `subdir`, which is what excludes a dotfile
            # sitting directly inside it.
            files = list(safe_walk(subdir, recursive=False, only_files=True))

            if not files:
                continue

            # Analyze file types
            file_types = {f.suffix.lower() for f in files if f.suffix}

            # Detect naming patterns in this directory
            naming_patterns = []
            for pattern_regex, pattern_type in self.common_patterns:
                matches = sum(1 for f in files if re.search(pattern_regex, f.stem))
                if matches >= self.min_pattern_count:
                    naming_patterns.append(pattern_type)

            # Calculate depth
            try:
                depth = len(subdir.relative_to(directory).parts)
            except ValueError:
                depth = 0

            # Infer category from directory name
            category = self._infer_category(subdir.name, file_types)

            location_patterns.append(
                LocationPattern(
                    directory=subdir,
                    file_types=file_types,
                    naming_patterns=naming_patterns,
                    file_count=len(files),
                    depth_level=depth,
                    category=category,
                )
            )

        # Sort by file count
        location_patterns.sort(key=lambda p: p.file_count, reverse=True)

        logger.info(f"Detected {len(location_patterns)} location patterns")
        return location_patterns

    def cluster_by_content(self, files: list[Path]) -> list[ContentCluster]:
        """Group files into clusters based on content characteristics.

        Args:
            files: List of file paths to cluster

        Returns:
            List of content clusters
        """
        logger.info(f"Clustering {len(files)} files by content")

        # Group by file type first
        type_groups = defaultdict(list)
        for file_path in files:
            file_type = file_path.suffix.lower()
            type_groups[file_type].append(file_path)

        clusters = []
        cluster_id = 0

        for file_type, type_files in type_groups.items():
            if len(type_files) < self.min_pattern_count:
                continue

            # Further cluster by directory location
            location_groups = defaultdict(list)
            for file_path in type_files:
                location_groups[file_path.parent].append(file_path)

            for location, location_files in location_groups.items():
                if len(location_files) < self.min_pattern_count:
                    continue

                # Extract keywords from filenames
                keywords = self._extract_common_keywords(location_files)

                # Calculate size range
                sizes = []
                for f in location_files:
                    try:
                        sizes.append(f.stat().st_size)
                    except OSError:
                        pass

                size_range = (min(sizes), max(sizes)) if sizes else (0, 0)

                # Infer category
                category = self._infer_category(location.name, {file_type})

                # Calculate confidence based on similarity
                confidence = self._calculate_cluster_confidence(location_files, keywords)

                clusters.append(
                    ContentCluster(
                        cluster_id=f"cluster_{cluster_id}",
                        file_paths=location_files,
                        common_keywords=keywords[:10],  # Top 10 keywords
                        file_types={file_type},
                        size_range=size_range,
                        category=category,
                        confidence=confidence,
                    )
                )

                cluster_id += 1

        # Sort by confidence
        clusters.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(f"Created {len(clusters)} content clusters")
        return clusters

    def _analyze_file_types(self, files: list[Path]) -> dict[str, int]:
        """Count files by type."""
        type_counter = Counter(f.suffix.lower() for f in files if f.suffix)
        return dict(type_counter.most_common())

    def _analyze_depth_distribution(self, files: list[Path], root: Path) -> dict[int, int]:
        """Analyze distribution of files across directory depths."""
        depth_counter: Counter[int] = Counter()

        for file_path in files:
            try:
                depth = len(file_path.relative_to(root).parent.parts)
                depth_counter[depth] += 1
            except ValueError:
                pass

        return dict(depth_counter)

    def _extract_common_keywords(self, files: list[Path]) -> list[str]:
        """Extract common keywords from filenames."""
        # Split filenames into words
        word_counter: Counter[str] = Counter()

        for file_path in files:
            # Split on common separators
            words = re.split(r"[_\-\s.]+", file_path.stem.lower())
            # Filter out short words and numbers
            words = [w for w in words if len(w) > 2 and not w.isdigit()]
            word_counter.update(words)

        # Return most common words
        return [word for word, count in word_counter.most_common(20)]

    def _calculate_cluster_confidence(self, files: list[Path], keywords: list[str]) -> float:
        """Calculate confidence score for a cluster."""
        if not files or not keywords:
            return 0.0

        # Count how many files contain top keywords
        keyword_matches = 0
        for file_path in files:
            filename_lower = file_path.stem.lower()
            if any(kw in filename_lower for kw in keywords[:5]):
                keyword_matches += 1

        confidence = (keyword_matches / len(files)) * 100
        return min(confidence, 100.0)

    def _infer_category(self, name: str, file_types: set[str]) -> str:
        """Infer category from directory name or file types."""
        name_lower = name.lower()

        # Category keywords
        categories = {
            "documents": ["doc", "document", "pdf", "report", "paper"],
            "images": ["image", "photo", "picture", "img", "pic"],
            "videos": ["video", "movie", "film", "clip"],
            "audio": ["audio", "music", "sound", "song"],
            "code": ["code", "src", "source", "script", "program"],
            "archives": ["archive", "backup", "compressed"],
            "downloads": ["download", "temp", "tmp"],
        }

        # Check name
        for category, keywords in categories.items():
            if any(kw in name_lower for kw in keywords):
                return category

        # Check file types
        type_categories = {
            "documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"},
            "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"},
            "videos": {".mp4", ".avi", ".mov", ".mkv", ".wmv"},
            "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg"},
            "code": {".py", ".js", ".java", ".cpp", ".c", ".go", ".rs"},
            "archives": {".zip", ".tar", ".gz", ".rar", ".7z"},
        }

        for category, extensions in type_categories.items():
            if file_types & extensions:
                return category

        return "general"

    def _get_pattern_description(self, pattern_type: str) -> str:
        """Get human-readable description of pattern type."""
        descriptions = {
            "PREFIX_STYLE": "Files with uppercase prefix (e.g., IMG_001.jpg)",
            "DATE_SUFFIX": "Files with date suffix (e.g., report_2024-01-15.pdf)",
            "DATE_PREFIX": "Files with date prefix (e.g., 2024-01-15_meeting.txt)",
            "VERSION": "Files with version numbers (e.g., app_v1.2.zip)",
            "NUMERIC_SUFFIX": "Files with numeric suffix (e.g., photo_001.jpg)",
            "NUMERIC_PREFIX": "Files with numeric prefix (e.g., 001_chapter.pdf)",
            "CAMEL_CASE": "Files in CamelCase (e.g., MyDocument.txt)",
            "SNAKE_CASE": "Files in snake_case (e.g., my_document.txt)",
            "KEBAB_CASE": "Files in kebab-case (e.g., my-document.txt)",
        }
        return descriptions.get(pattern_type, "Unknown pattern")
