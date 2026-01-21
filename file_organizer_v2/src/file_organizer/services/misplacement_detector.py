"""
Misplacement Detector Service

Detects files that are in the wrong location based on content-location
mismatch analysis.
"""

import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import mimetypes

from .pattern_analyzer import PatternAnalyzer, PatternAnalysis

logger = logging.getLogger(__name__)


@dataclass
class MisplacedFile:
    """Represents a file that appears to be misplaced."""
    file_path: Path
    current_location: Path
    suggested_location: Path
    mismatch_score: float  # 0-100, higher = more misplaced
    reasons: List[str]
    similar_files: List[Path] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'file_path': str(self.file_path),
            'current_location': str(self.current_location),
            'suggested_location': str(self.suggested_location),
            'mismatch_score': self.mismatch_score,
            'reasons': self.reasons,
            'similar_files': [str(f) for f in self.similar_files],
            'metadata': self.metadata,
            'detected_at': self.detected_at.isoformat()
        }


@dataclass
class ContextAnalysis:
    """Analysis of file context and surroundings."""
    file_path: Path
    file_type: str
    mime_type: Optional[str]
    size: int
    directory: Path
    sibling_files: List[Path]
    sibling_types: Set[str]
    parent_category: str
    naming_patterns: List[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'file_path': str(self.file_path),
            'file_type': self.file_type,
            'mime_type': self.mime_type,
            'size': self.size,
            'directory': str(self.directory),
            'sibling_count': len(self.sibling_files),
            'sibling_types': list(self.sibling_types),
            'parent_category': self.parent_category,
            'naming_patterns': self.naming_patterns
        }


class MisplacementDetector:
    """
    Detects files that are in incorrect locations based on content
    and organizational patterns.
    """

    def __init__(
        self,
        min_mismatch_score: float = 60.0,
        similarity_threshold: float = 0.7
    ):
        """
        Initialize the misplacement detector.

        Args:
            min_mismatch_score: Minimum score to consider a file misplaced
            similarity_threshold: Threshold for considering files similar
        """
        self.min_mismatch_score = min_mismatch_score
        self.similarity_threshold = similarity_threshold
        self.pattern_analyzer = PatternAnalyzer()

        # Category to file type mapping
        self.category_types = {
            'documents': {'.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.odt'},
            'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'},
            'videos': {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'},
            'audio': {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'},
            'code': {'.py', '.js', '.java', '.cpp', '.c', '.go', '.rs', '.ts'},
            'archives': {'.zip', '.tar', '.gz', '.rar', '.7z', '.bz2'},
            'spreadsheets': {'.xlsx', '.xls', '.csv', '.ods'},
            'presentations': {'.pptx', '.ppt', '.odp', '.key'},
        }

    def detect_misplaced(
        self,
        directory: Path,
        pattern_analysis: Optional[PatternAnalysis] = None
    ) -> List[MisplacedFile]:
        """
        Detect misplaced files in a directory.

        Args:
            directory: Directory to analyze
            pattern_analysis: Optional pre-computed pattern analysis

        Returns:
            List of misplaced files
        """
        logger.info(f"Detecting misplaced files in {directory}")

        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Invalid directory: {directory}")

        # Analyze patterns if not provided
        if pattern_analysis is None:
            pattern_analysis = self.pattern_analyzer.analyze_directory(directory)

        # Get all files
        files = list(directory.rglob('*'))
        files = [f for f in files if f.is_file() and not f.name.startswith('.')]

        misplaced_files = []

        for file_path in files:
            # Analyze context
            context = self.analyze_context(file_path)

            # Calculate mismatch score
            mismatch_score = self.calculate_mismatch_score(
                file_path, context, pattern_analysis
            )

            if mismatch_score >= self.min_mismatch_score:
                # Find correct location
                suggested_location = self.find_correct_location(
                    file_path, pattern_analysis
                )

                # Find similar files
                similar_files = self.find_similar_files(
                    file_path, suggested_location, pattern_analysis
                )

                # Generate reasons
                reasons = self._generate_mismatch_reasons(
                    file_path, context, mismatch_score
                )

                misplaced_files.append(MisplacedFile(
                    file_path=file_path,
                    current_location=file_path.parent,
                    suggested_location=suggested_location,
                    mismatch_score=mismatch_score,
                    reasons=reasons,
                    similar_files=similar_files,
                    metadata={
                        'context': context.to_dict(),
                        'file_type_mismatch': self._check_type_mismatch(context),
                        'pattern_mismatch': self._check_pattern_mismatch(
                            file_path, context, pattern_analysis
                        )
                    }
                ))

        # Sort by mismatch score (highest first)
        misplaced_files.sort(key=lambda f: f.mismatch_score, reverse=True)

        logger.info(f"Detected {len(misplaced_files)} misplaced files")
        return misplaced_files

    def analyze_context(self, file_path: Path) -> ContextAnalysis:
        """
        Analyze the context of a file.

        Args:
            file_path: File to analyze

        Returns:
            ContextAnalysis with context information
        """
        directory = file_path.parent
        file_type = file_path.suffix.lower()

        # Get MIME type
        mime_type = mimetypes.guess_type(str(file_path))[0]

        # Get file size
        try:
            size = file_path.stat().st_size
        except OSError:
            size = 0

        # Get sibling files
        sibling_files = [f for f in directory.iterdir() if f.is_file() and f != file_path]
        sibling_types = {f.suffix.lower() for f in sibling_files if f.suffix}

        # Infer parent category
        parent_category = self._infer_category_from_type(file_type)

        # Detect naming patterns in directory
        naming_patterns = self._detect_local_patterns(sibling_files)

        return ContextAnalysis(
            file_path=file_path,
            file_type=file_type,
            mime_type=mime_type,
            size=size,
            directory=directory,
            sibling_files=sibling_files,
            sibling_types=sibling_types,
            parent_category=parent_category,
            naming_patterns=naming_patterns
        )

    def calculate_mismatch_score(
        self,
        file_path: Path,
        context: ContextAnalysis,
        pattern_analysis: PatternAnalysis
    ) -> float:
        """
        Calculate how misplaced a file is.

        Args:
            file_path: File to check
            context: Context analysis
            pattern_analysis: Pattern analysis

        Returns:
            Mismatch score (0-100)
        """
        scores = []

        # Type mismatch score
        type_score = self._calculate_type_mismatch(context)
        scores.append(type_score * 0.35)  # 35% weight

        # Pattern mismatch score
        pattern_score = self._calculate_pattern_mismatch(
            file_path, context, pattern_analysis
        )
        scores.append(pattern_score * 0.25)  # 25% weight

        # Isolation score (file alone or with different types)
        isolation_score = self._calculate_isolation_score(context)
        scores.append(isolation_score * 0.20)  # 20% weight

        # Naming convention score
        naming_score = self._calculate_naming_mismatch(file_path, context)
        scores.append(naming_score * 0.20)  # 20% weight

        total_score = sum(scores)
        return min(max(total_score, 0.0), 100.0)

    def find_correct_location(
        self,
        file_path: Path,
        pattern_analysis: PatternAnalysis
    ) -> Path:
        """
        Find the correct location for a misplaced file.

        Args:
            file_path: Misplaced file
            pattern_analysis: Pattern analysis

        Returns:
            Suggested correct location
        """
        file_type = file_path.suffix.lower()
        category = self._infer_category_from_type(file_type)

        # Look for existing directories with matching patterns
        candidates = []

        for location_pattern in pattern_analysis.location_patterns:
            if file_type in location_pattern.file_types:
                candidates.append((
                    location_pattern.directory,
                    location_pattern.file_count * 2  # Weight by file count
                ))

            if location_pattern.category == category:
                candidates.append((
                    location_pattern.directory,
                    location_pattern.file_count
                ))

        if candidates:
            # Return location with highest score
            best_location = max(candidates, key=lambda x: x[1])[0]
            return best_location

        # If no good match, suggest category-based location
        root = pattern_analysis.directory
        category_dir = root / category

        return category_dir

    def find_similar_files(
        self,
        file_path: Path,
        target_location: Path,
        pattern_analysis: PatternAnalysis
    ) -> List[Path]:
        """
        Find files similar to the given file.

        Args:
            file_path: Reference file
            target_location: Location to search
            pattern_analysis: Pattern analysis

        Returns:
            List of similar files
        """
        file_type = file_path.suffix.lower()
        similar_files = []

        if not target_location.exists():
            return []

        # Find files with same type in target location
        for cluster in pattern_analysis.content_clusters:
            if file_type in cluster.file_types:
                # Check if cluster is in or near target location
                cluster_paths = [
                    f for f in cluster.file_paths
                    if self._is_in_or_near(f, target_location)
                ]
                similar_files.extend(cluster_paths)

        return similar_files[:10]  # Limit to 10 similar files

    def _calculate_type_mismatch(self, context: ContextAnalysis) -> float:
        """Calculate type mismatch score."""
        file_type = context.file_type
        sibling_types = context.sibling_types

        if not sibling_types:
            return 30.0  # Alone, but not necessarily misplaced

        # Check if file type matches any sibling
        if file_type in sibling_types:
            return 10.0  # Low mismatch

        # Check if file category matches sibling categories
        file_category = self._infer_category_from_type(file_type)
        sibling_categories = {
            self._infer_category_from_type(t) for t in sibling_types
        }

        if file_category in sibling_categories:
            return 30.0  # Medium mismatch

        return 80.0  # High mismatch

    def _calculate_pattern_mismatch(
        self,
        file_path: Path,
        context: ContextAnalysis,
        pattern_analysis: PatternAnalysis
    ) -> float:
        """Calculate pattern mismatch score."""
        # Check if file follows directory naming patterns
        if not context.naming_patterns:
            return 40.0  # No clear pattern

        filename = file_path.stem.lower()

        # Check if file matches local patterns
        matches_pattern = any(
            pattern in filename for pattern in context.naming_patterns
        )

        if matches_pattern:
            return 20.0  # Follows pattern

        return 70.0  # Doesn't follow pattern

    def _calculate_isolation_score(self, context: ContextAnalysis) -> float:
        """Calculate how isolated/alone a file is."""
        sibling_count = len(context.sibling_files)

        if sibling_count == 0:
            return 80.0  # Completely alone
        elif sibling_count < 3:
            return 60.0  # Few siblings
        elif sibling_count < 10:
            return 30.0  # Some siblings
        else:
            return 10.0  # Many siblings

    def _calculate_naming_mismatch(
        self, file_path: Path, context: ContextAnalysis
    ) -> float:
        """Calculate naming convention mismatch."""
        if not context.sibling_files:
            return 30.0

        # Simple check: does file name style match siblings?
        filename = file_path.stem
        sibling_names = [f.stem for f in context.sibling_files]

        # Check for common patterns
        has_underscore = '_' in filename
        siblings_underscore = sum('_' in name for name in sibling_names)

        has_dash = '-' in filename
        siblings_dash = sum('-' in name for name in sibling_names)

        # If file style differs from majority
        if has_underscore and siblings_dash > siblings_underscore:
            return 60.0
        elif has_dash and siblings_underscore > siblings_dash:
            return 60.0

        return 25.0

    def _infer_category_from_type(self, file_type: str) -> str:
        """Infer category from file type."""
        for category, types in self.category_types.items():
            if file_type in types:
                return category
        return 'general'

    def _check_type_mismatch(self, context: ContextAnalysis) -> bool:
        """Check if file type mismatches location."""
        file_category = self._infer_category_from_type(context.file_type)
        sibling_categories = {
            self._infer_category_from_type(t) for t in context.sibling_types
        }

        return file_category not in sibling_categories

    def _check_pattern_mismatch(
        self,
        file_path: Path,
        context: ContextAnalysis,
        pattern_analysis: PatternAnalysis
    ) -> bool:
        """Check if file doesn't match location patterns."""
        if not context.naming_patterns:
            return False

        filename = file_path.stem.lower()
        return not any(pattern in filename for pattern in context.naming_patterns)

    def _generate_mismatch_reasons(
        self,
        file_path: Path,
        context: ContextAnalysis,
        score: float
    ) -> List[str]:
        """Generate human-readable reasons for mismatch."""
        reasons = []

        # Type mismatch
        if self._check_type_mismatch(context):
            file_category = self._infer_category_from_type(context.file_type)
            reasons.append(
                f"File type ({file_category}) doesn't match surrounding files"
            )

        # Isolation
        if len(context.sibling_files) < 3:
            reasons.append("File is isolated with few similar files nearby")

        # Naming pattern
        if context.naming_patterns:
            reasons.append("File naming doesn't match directory convention")

        # High score
        if score > 80:
            reasons.append("Strong indicators this file is in the wrong location")

        if not reasons:
            reasons.append("File organization could be improved")

        return reasons

    def _detect_local_patterns(self, files: List[Path]) -> List[str]:
        """Detect naming patterns in a set of files."""
        if not files:
            return []

        # Simple pattern detection
        patterns = []

        # Check for common prefixes
        stems = [f.stem.lower() for f in files]
        if len(stems) > 2:
            # Check for date patterns
            if any('202' in s or '201' in s for s in stems):
                patterns.append('date')

            # Check for numeric patterns
            if any(s[:3].isdigit() for s in stems):
                patterns.append('numeric')

            # Check for underscore style
            if sum('_' in s for s in stems) > len(stems) * 0.7:
                patterns.append('underscore')

        return patterns

    def _is_in_or_near(self, file_path: Path, target: Path) -> bool:
        """Check if file is in or near target directory."""
        try:
            file_path.relative_to(target)
            return True
        except ValueError:
            # Check if in sibling directory
            return file_path.parent.parent == target.parent
