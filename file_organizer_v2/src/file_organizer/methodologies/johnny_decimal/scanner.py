"""
Johnny Decimal Migration Scanner

Scans existing folder structures to prepare for migration to Johnny Decimal system.
Detects current organization patterns and suggests appropriate JD mappings.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .categories import JohnnyDecimalNumber, NumberingScheme

logger = logging.getLogger(__name__)


@dataclass
class FolderInfo:
    """Information about a folder to be migrated."""

    path: Path
    name: str
    depth: int
    children: List["FolderInfo"] = field(default_factory=list)
    file_count: int = 0
    total_size: int = 0  # bytes
    suggested_number: Optional[JohnnyDecimalNumber] = None
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    """Result of scanning a directory structure."""

    root_path: Path
    total_folders: int
    total_files: int
    total_size: int
    max_depth: int
    folder_tree: List[FolderInfo]
    detected_patterns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class FolderScanner:
    """
    Scans existing folder structures for migration to Johnny Decimal.

    Analyzes hierarchy, naming patterns, and content to suggest
    appropriate Johnny Decimal number assignments.
    """

    def __init__(
        self,
        scheme: Optional[NumberingScheme] = None,
        max_depth: int = 10,
        skip_hidden: bool = True,
    ):
        """
        Initialize the folder scanner.

        Args:
            scheme: Johnny Decimal numbering scheme for suggestions
            max_depth: Maximum depth to scan
            skip_hidden: Whether to skip hidden files/folders
        """
        self.scheme = scheme
        self.max_depth = max_depth
        self.skip_hidden = skip_hidden
        self._total_files = 0
        self._total_size = 0

    def scan_directory(self, root_path: Path) -> ScanResult:
        """
        Scan a directory structure and analyze for migration.

        Args:
            root_path: Root directory to scan

        Returns:
            ScanResult with folder hierarchy and statistics

        Raises:
            ValueError: If root_path doesn't exist or is not a directory
        """
        if not root_path.exists():
            raise ValueError(f"Path does not exist: {root_path}")

        if not root_path.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")

        logger.info(f"Scanning directory: {root_path}")

        self._total_files = 0
        self._total_size = 0

        # Scan root level
        folder_tree = self._scan_folder(root_path, depth=0)

        # Detect organizational patterns
        patterns = self._detect_patterns(folder_tree)

        # Find maximum depth
        max_depth = self._find_max_depth(folder_tree)

        # Generate warnings
        warnings = self._generate_warnings(folder_tree, max_depth)

        result = ScanResult(
            root_path=root_path,
            total_folders=self._count_folders(folder_tree),
            total_files=self._total_files,
            total_size=self._total_size,
            max_depth=max_depth,
            folder_tree=folder_tree,
            detected_patterns=patterns,
            warnings=warnings,
        )

        logger.info(
            f"Scan complete: {result.total_folders} folders, "
            f"{result.total_files} files, depth={result.max_depth}"
        )

        return result

    def _scan_folder(self, path: Path, depth: int) -> List[FolderInfo]:
        """
        Recursively scan a folder and its children.

        Args:
            path: Folder path to scan
            depth: Current depth in hierarchy

        Returns:
            List of FolderInfo objects for folders at this level
        """
        if depth > self.max_depth:
            logger.warning(f"Max depth exceeded at {path}")
            return []

        folders: List[FolderInfo] = []

        try:
            items = sorted(path.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied: {path}")
            return folders

        for item in items:
            # Skip hidden files/folders if configured
            if self.skip_hidden and item.name.startswith("."):
                continue

            if item.is_dir():
                # Scan subdirectory
                folder_info = self._create_folder_info(item, depth)
                folder_info.children = self._scan_folder(item, depth + 1)
                folders.append(folder_info)
            elif item.is_file():
                # Count files
                self._total_files += 1
                try:
                    self._total_size += item.stat().st_size
                except OSError:
                    pass

        return folders

    def _create_folder_info(self, path: Path, depth: int) -> FolderInfo:
        """
        Create FolderInfo object for a folder.

        Args:
            path: Folder path
            depth: Depth in hierarchy

        Returns:
            FolderInfo object with folder metadata
        """
        file_count = 0
        total_size = 0

        try:
            # Count immediate files
            for item in path.iterdir():
                if item.is_file():
                    file_count += 1
                    try:
                        total_size += item.stat().st_size
                    except OSError:
                        pass
        except PermissionError:
            pass

        folder_info = FolderInfo(
            path=path,
            name=path.name,
            depth=depth,
            file_count=file_count,
            total_size=total_size,
        )

        return folder_info

    def _detect_patterns(self, folder_tree: List[FolderInfo]) -> List[str]:
        """
        Detect organizational patterns in the folder structure.

        Args:
            folder_tree: Scanned folder tree

        Returns:
            List of detected pattern descriptions
        """
        patterns = []

        # Check for PARA structure
        para_folders = {"projects", "areas", "resources", "archive"}
        root_names = {f.name.lower() for f in folder_tree}

        if para_folders.issubset(root_names):
            patterns.append("PARA methodology detected")

        # Check for date-based organization
        # Look for 4-digit years in reasonable range (1900-2099)
        def has_year_pattern(name: str) -> bool:
            import re
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', name)
            return year_match is not None

        date_patterns = [
            all(f.name.isdigit() and len(f.name) == 4 for f in folder_tree[:3]),
            any(has_year_pattern(f.name) for f in folder_tree),
        ]

        if any(date_patterns):
            patterns.append("Date-based organization detected")

        # Check for existing Johnny Decimal
        jd_pattern = any(self._looks_like_jd_number(f.name) for f in folder_tree)
        if jd_pattern:
            patterns.append("Existing Johnny Decimal numbers detected")

        # Check for flat vs hierarchical
        if len(folder_tree) > 20 and all(len(f.children) == 0 for f in folder_tree):
            patterns.append("Flat structure (many top-level folders)")
        elif any(len(f.children) > 5 for f in folder_tree):
            patterns.append("Deep hierarchical structure")

        return patterns if patterns else ["No specific pattern detected"]

    def _looks_like_jd_number(self, name: str) -> bool:
        """
        Check if a folder name looks like it contains a JD number.

        Args:
            name: Folder name

        Returns:
            True if name appears to contain JD number
        """
        # Check for patterns like "10", "11.01", "11.01.001"
        parts = name.split()
        if not parts:
            return False

        first_part = parts[0]

        # Check for two-digit area number
        if first_part.isdigit() and len(first_part) == 2:
            return True

        # Check for category number (XX.XX)
        if "." in first_part:
            number_parts = first_part.split(".")
            if len(number_parts) == 2 and all(p.isdigit() and len(p) == 2 for p in number_parts):
                return True
            # Check for ID (XX.XX.XXX)
            if len(number_parts) == 3:
                if (
                    all(p.isdigit() for p in number_parts)
                    and len(number_parts[0]) == 2
                    and len(number_parts[1]) == 2
                    and len(number_parts[2]) == 3
                ):
                    return True

        return False

    def _find_max_depth(self, folder_tree: List[FolderInfo]) -> int:
        """
        Find maximum depth in folder tree.

        Args:
            folder_tree: Folder tree to analyze

        Returns:
            Maximum depth found
        """
        if not folder_tree:
            return 0

        max_depth = 0
        for folder in folder_tree:
            current_depth = folder.depth
            if folder.children:
                child_depth = self._find_max_depth(folder.children)
                current_depth = max(current_depth, child_depth)
            max_depth = max(max_depth, current_depth)

        return max_depth

    def _count_folders(self, folder_tree: List[FolderInfo]) -> int:
        """
        Count total number of folders in tree.

        Args:
            folder_tree: Folder tree

        Returns:
            Total folder count
        """
        count = len(folder_tree)
        for folder in folder_tree:
            count += self._count_folders(folder.children)
        return count

    def _generate_warnings(self, folder_tree: List[FolderInfo], max_depth: int) -> List[str]:
        """
        Generate warnings about potential migration issues.

        Args:
            folder_tree: Scanned folder tree
            max_depth: Maximum depth found

        Returns:
            List of warning messages
        """
        warnings = []

        # Warn about deep hierarchies
        if max_depth > 5:
            warnings.append(
                f"Deep hierarchy detected (depth={max_depth}). "
                "Consider flattening to 2-3 levels for Johnny Decimal."
            )

        # Warn about many top-level folders
        if len(folder_tree) > 10:
            warnings.append(
                f"Many top-level folders ({len(folder_tree)}). "
                "Johnny Decimal works best with 10 or fewer areas."
            )

        # Warn about name conflicts
        names = [f.name for f in folder_tree]
        duplicates = [name for name in names if names.count(name) > 1]
        if duplicates:
            warnings.append(f"Duplicate folder names detected: {set(duplicates)}")

        return warnings
