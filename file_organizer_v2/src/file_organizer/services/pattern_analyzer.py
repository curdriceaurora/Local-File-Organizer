"""
Pattern Analyzer Service

Analyzes file organization patterns including directory structures,
naming conventions, and content-based clustering.
"""

import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NamingPattern:
    """Represents a detected file naming pattern."""
    pattern: str
    regex: str
    example_files: List[str]
    count: int
    confidence: float
    description: str


@dataclass
class LocationPattern:
    """Represents a pattern in file locations."""
    directory: Path
    file_types: Set[str]
    naming_patterns: List[str]
    file_count: int
    depth_level: int
    category: Optional[str] = None


@dataclass
class ContentCluster:
    """Represents a cluster of files with similar content characteristics."""
    cluster_id: str
    file_paths: List[Path]
    common_keywords: List[str]
    file_types: Set[str]
    size_range: Tuple[int, int]
    category: str
    confidence: float


@dataclass
class PatternAnalysis:
    """Complete pattern analysis results."""
    directory: Path
    naming_patterns: List[NamingPattern]
    location_patterns: List[LocationPattern]
    content_clusters: List[ContentCluster]
    file_type_distribution: Dict[str, int]
    depth_distribution: Dict[int, int]
    analyzed_at: datetime
    total_files: int
    metadata: Dict = field(default_factory=dict)


class PatternAnalyzer:
    """
    Analyzes file organization patterns to detect structure, naming conventions,
    and content-based clusters.
    """

    def __init__(self, min_pattern_count: int = 3, max_depth: int = 10):
        """
        Initialize the pattern analyzer.

        Args:
            min_pattern_count: Minimum number of files to form a pattern
            max_depth: Maximum directory depth to analyze
        """
        self.min_pattern_count = min_pattern_count
        self.max_depth = max_depth

        # Common naming patterns to detect
        self.common_patterns = [
            (r'^([A-Z]{2,})[_-]', 'PREFIX_STYLE'),
            (r'_([0-9]{4}[-_][0-9]{2}[-_][0-9]{2})', 'DATE_SUFFIX'),
            (r'^([0-9]{4}[-_][0-9]{2}[-_][0-9]{2})_', 'DATE_PREFIX'),
            (r'([vV][0-9]+\.[0-9]+)', 'VERSION'),
            (r'_([0-9]{3,})\.', 'NUMERIC_SUFFIX'),
            (r'^([0-9]{3,})[-_]', 'NUMERIC_PREFIX'),
            (r'([A-Z][a-z]+){2,}', 'CAMEL_CASE'),
            (r'([a-z]+_[a-z]+)', 'SNAKE_CASE'),
            (r'([a-z]+-[a-z]+)', 'KEBAB_CASE'),
        ]

    def analyze_directory(self, directory: Path) -> PatternAnalysis:
        """
        Perform complete pattern analysis on a directory.

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
                analyzed_at=datetime.now(),
                total_files=0
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
            analyzed_at=datetime.now(),
            total_files=len(files),
            metadata={
                'min_pattern_count': self.min_pattern_count,
                'max_depth': self.max_depth
            }
        )

    def _collect_files(self, directory: Path, current_depth: int = 0) -> List[Path]:
        """
        Recursively collect all files up to max_depth.

        Args:
            directory: Directory to scan
            current_depth: Current recursion depth

        Returns:
            List of file paths
        """
        if current_depth > self.max_depth:
            return []

        files = []
        try:
            for item in directory.iterdir():
                if item.is_file():
                    files.append(item)
                elif item.is_dir() and not item.name.startswith('.'):
                    files.extend(self._collect_files(item, current_depth + 1))
        except PermissionError:
            logger.warning(f"Permission denied: {directory}")

        return files

    def detect_naming_patterns(self, files: List[Path]) -> List[NamingPattern]:
        """
        Detect naming patterns across files.

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

                detected_patterns.append(NamingPattern(
                    pattern=pattern_type,
                    regex=regex,
                    example_files=matched_files[:5],  # Store up to 5 examples
                    count=len(matched_files),
                    confidence=confidence,
                    description=self._get_pattern_description(pattern_type)
                ))

        # Sort by count (most common first)
        detected_patterns.sort(key=lambda p: p.count, reverse=True)

        logger.info(f"Detected {len(detected_patterns)} naming patterns")
        return detected_patterns

    def get_location_patterns(self, directory: Path) -> List[LocationPattern]:
        """
        Analyze location-based organizational patterns.

        Args:
            directory: Root directory to analyze

        Returns:
            List of location patterns
        """
        logger.info(f"Analyzing location patterns in {directory}")

        location_patterns = []

        # Analyze each subdirectory
        for subdir in directory.rglob('*'):
            if not subdir.is_dir() or subdir.name.startswith('.'):
                continue

            # Get files in this directory (non-recursive)
            files = [f for f in subdir.iterdir() if f.is_file()]

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

            location_patterns.append(LocationPattern(
                directory=subdir,
                file_types=file_types,
                naming_patterns=naming_patterns,
                file_count=len(files),
                depth_level=depth,
                category=category
            ))

        # Sort by file count
        location_patterns.sort(key=lambda p: p.file_count, reverse=True)

        logger.info(f"Detected {len(location_patterns)} location patterns")
        return location_patterns

    def cluster_by_content(self, files: List[Path]) -> List[ContentCluster]:
        """
        Group files into clusters based on content characteristics.

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

                clusters.append(ContentCluster(
                    cluster_id=f"cluster_{cluster_id}",
                    file_paths=location_files,
                    common_keywords=keywords[:10],  # Top 10 keywords
                    file_types={file_type},
                    size_range=size_range,
                    category=category,
                    confidence=confidence
                ))

                cluster_id += 1

        # Sort by confidence
        clusters.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(f"Created {len(clusters)} content clusters")
        return clusters

    def _analyze_file_types(self, files: List[Path]) -> Dict[str, int]:
        """Count files by type."""
        type_counter = Counter(f.suffix.lower() for f in files if f.suffix)
        return dict(type_counter.most_common())

    def _analyze_depth_distribution(self, files: List[Path], root: Path) -> Dict[int, int]:
        """Analyze distribution of files across directory depths."""
        depth_counter = Counter()

        for file_path in files:
            try:
                depth = len(file_path.relative_to(root).parent.parts)
                depth_counter[depth] += 1
            except ValueError:
                pass

        return dict(depth_counter)

    def _extract_common_keywords(self, files: List[Path]) -> List[str]:
        """Extract common keywords from filenames."""
        # Split filenames into words
        word_counter = Counter()

        for file_path in files:
            # Split on common separators
            words = re.split(r'[_\-\s.]+', file_path.stem.lower())
            # Filter out short words and numbers
            words = [w for w in words if len(w) > 2 and not w.isdigit()]
            word_counter.update(words)

        # Return most common words
        return [word for word, count in word_counter.most_common(20)]

    def _calculate_cluster_confidence(self, files: List[Path], keywords: List[str]) -> float:
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

    def _infer_category(self, name: str, file_types: Set[str]) -> str:
        """Infer category from directory name or file types."""
        name_lower = name.lower()

        # Category keywords
        categories = {
            'documents': ['doc', 'document', 'pdf', 'report', 'paper'],
            'images': ['image', 'photo', 'picture', 'img', 'pic'],
            'videos': ['video', 'movie', 'film', 'clip'],
            'audio': ['audio', 'music', 'sound', 'song'],
            'code': ['code', 'src', 'source', 'script', 'program'],
            'archives': ['archive', 'backup', 'compressed'],
            'downloads': ['download', 'temp', 'tmp'],
        }

        # Check name
        for category, keywords in categories.items():
            if any(kw in name_lower for kw in keywords):
                return category

        # Check file types
        type_categories = {
            'documents': {'.pdf', '.doc', '.docx', '.txt', '.md', '.rtf'},
            'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg'},
            'videos': {'.mp4', '.avi', '.mov', '.mkv', '.wmv'},
            'audio': {'.mp3', '.wav', '.flac', '.aac', '.ogg'},
            'code': {'.py', '.js', '.java', '.cpp', '.c', '.go', '.rs'},
            'archives': {'.zip', '.tar', '.gz', '.rar', '.7z'},
        }

        for category, extensions in type_categories.items():
            if file_types & extensions:
                return category

        return 'general'

    def _get_pattern_description(self, pattern_type: str) -> str:
        """Get human-readable description of pattern type."""
        descriptions = {
            'PREFIX_STYLE': 'Files with uppercase prefix (e.g., IMG_001.jpg)',
            'DATE_SUFFIX': 'Files with date suffix (e.g., report_2024-01-15.pdf)',
            'DATE_PREFIX': 'Files with date prefix (e.g., 2024-01-15_meeting.txt)',
            'VERSION': 'Files with version numbers (e.g., app_v1.2.zip)',
            'NUMERIC_SUFFIX': 'Files with numeric suffix (e.g., photo_001.jpg)',
            'NUMERIC_PREFIX': 'Files with numeric prefix (e.g., 001_chapter.pdf)',
            'CAMEL_CASE': 'Files in CamelCase (e.g., MyDocument.txt)',
            'SNAKE_CASE': 'Files in snake_case (e.g., my_document.txt)',
            'KEBAB_CASE': 'Files in kebab-case (e.g., my-document.txt)',
        }
        return descriptions.get(pattern_type, 'Unknown pattern')
