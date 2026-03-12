"""PARA-Aware File Mover.

Organizes files into PARA directory structures based on AI suggestions.
All file operations support dry-run mode for safety. Designed for local,
privacy-first file management.
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..categories import PARACategory
from ..config import PARAConfig
from .suggestion_engine import PARASuggestion, PARASuggestionEngine

logger = logging.getLogger(__name__)


@dataclass
class MoveSuggestion:
    """Suggestion to move a file to a PARA-organized location.

    Attributes:
        file_path: Current path of the file.
        target_category: Recommended PARA category.
        target_path: Full destination path for the file.
        confidence: Confidence in this move suggestion.
        reasoning: Explanations for this suggestion.
    """

    file_path: Path
    target_category: PARACategory
    target_path: Path
    confidence: float
    reasoning: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class MoveResult:
    """Result of a file move operation.

    Attributes:
        success: Whether the move completed successfully.
        source: Original file path.
        destination: Target file path.
        error: Error message if the move failed.
        dry_run: Whether this was a dry-run (no actual changes).
    """

    success: bool
    source: Path
    destination: Path
    error: str | None = None
    dry_run: bool = False


@dataclass
class OrganizationReport:
    """Report summarizing a bulk organization operation.

    Attributes:
        total_files: Total number of files analyzed.
        moved: Number of files successfully moved (or would be moved in dry-run).
        skipped: Number of files skipped (low confidence, already organized, etc.).
        errors: Number of files that encountered errors.
        category_distribution: Count of files per PARA category.
        move_results: Detailed results for each file.
        suggestions: All move suggestions generated.
    """

    total_files: int = 0
    moved: int = 0
    skipped: int = 0
    errors: int = 0
    category_distribution: dict[str, int] = field(default_factory=dict)
    move_results: list[MoveResult] = field(default_factory=list)
    suggestions: list[MoveSuggestion] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Proportion of files successfully moved."""
        if self.total_files == 0:
            return 0.0
        return self.moved / self.total_files


class PARAFileMover:
    """Moves files into PARA-organized directory structures.

    Combines the suggestion engine with file system operations to
    organize files according to PARA methodology. All operations
    default to dry-run mode for safety.

    Example::

        mover = PARAFileMover(config, root_dir=Path("/home/user/Documents"))
        suggestion = mover.suggest_move(Path("report.pdf"))
        result = mover.move_file(suggestion, dry_run=False)
    """

    def __init__(
        self,
        config: PARAConfig | None = None,
        suggestion_engine: PARASuggestionEngine | None = None,
        root_dir: Path | None = None,
    ) -> None:
        """Initialize the PARA file mover.

        Args:
            config: PARA configuration. Uses defaults if not provided.
            suggestion_engine: Pre-configured suggestion engine. Created
                from config if not provided.
            root_dir: Root directory for PARA organization. Defaults to
                config.default_root or current working directory.
        """
        self._config = config or PARAConfig()
        self._engine = suggestion_engine or PARASuggestionEngine(config=self._config)
        self._root_dir = root_dir or self._config.default_root or Path.cwd()

    @property
    def root_dir(self) -> Path:
        """The root directory for PARA organization."""
        return self._root_dir

    def suggest_move(
        self,
        file_path: Path,
        content: str | None = None,
    ) -> MoveSuggestion:
        """Generate a move suggestion for a single file.

        Args:
            file_path: Path to the file to analyze.
            content: Optional text content for deeper analysis.

        Returns:
            MoveSuggestion with recommended destination.
        """
        suggestion = self._engine.suggest(file_path, content=content)
        target_path = self._compute_target_path(file_path, suggestion)

        return MoveSuggestion(
            file_path=file_path,
            target_category=suggestion.category,
            target_path=target_path,
            confidence=suggestion.confidence,
            reasoning=suggestion.reasoning,
        )

    def move_file(
        self,
        suggestion: MoveSuggestion,
        dry_run: bool = True,
    ) -> MoveResult:
        """Execute a file move based on a suggestion.

        Args:
            suggestion: The move suggestion to execute.
            dry_run: If True (default), only simulate the move without
                making changes.

        Returns:
            MoveResult indicating success or failure.
        """
        source = suggestion.file_path
        destination = suggestion.target_path

        # Validate source exists
        if not source.exists():
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=f"Source file does not exist: {source}",
                dry_run=dry_run,
            )

        # Check if already at destination
        if source.resolve() == destination.resolve():
            return MoveResult(
                success=True,
                source=source,
                destination=destination,
                error=None,
                dry_run=dry_run,
            )

        if dry_run:
            logger.info("[DRY RUN] Would move %s -> %s", source, destination)
            return MoveResult(
                success=True,
                source=source,
                destination=destination,
                dry_run=True,
            )

        # Execute the actual move
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Handle name collision
            final_dest = self._resolve_collision(destination)

            shutil.move(str(source), str(final_dest))
            logger.info("Moved %s -> %s", source, final_dest)

            return MoveResult(
                success=True,
                source=source,
                destination=final_dest,
                dry_run=False,
            )
        except OSError as e:
            logger.error("Failed to move %s -> %s: %s", source, destination, e, exc_info=True)
            return MoveResult(
                success=False,
                source=source,
                destination=destination,
                error=str(e),
                dry_run=False,
            )

    def bulk_organize(
        self,
        directory: Path,
        dry_run: bool = True,
        min_confidence: float = 0.6,
        recursive: bool = False,
    ) -> OrganizationReport:
        """Organize all files in a directory into PARA structure.

        Args:
            directory: Directory containing files to organize.
            dry_run: If True (default), only simulate moves.
            min_confidence: Minimum confidence threshold to proceed with a move.
            recursive: Whether to scan subdirectories.

        Returns:
            OrganizationReport summarizing the operation.
        """
        report = OrganizationReport()

        if not directory.exists() or not directory.is_dir():
            logger.error("Directory does not exist: %s", directory)
            return report

        # Collect files
        if recursive:
            files = [f for f in directory.rglob("*") if f.is_file()]
        else:
            files = [f for f in directory.iterdir() if f.is_file()]

        report.total_files = len(files)

        for file_path in files:
            try:
                suggestion = self.suggest_move(file_path)
                report.suggestions.append(suggestion)

                # Skip low-confidence suggestions
                if suggestion.confidence < min_confidence:
                    report.skipped += 1
                    continue

                # Skip if already in the right place
                if self._is_already_organized(file_path, suggestion.target_category):
                    report.skipped += 1
                    continue

                result = self.move_file(suggestion, dry_run=dry_run)
                report.move_results.append(result)

                if result.success:
                    report.moved += 1
                    cat_name = suggestion.target_category.value
                    report.category_distribution[cat_name] = (
                        report.category_distribution.get(cat_name, 0) + 1
                    )
                else:
                    report.errors += 1

            except Exception as e:
                logger.error("Error processing %s: %s", file_path, e, exc_info=True)
                report.errors += 1

        return report

    def suggest_archive(
        self,
        directory: Path,
        inactive_days: int = 180,
    ) -> list[MoveSuggestion]:
        """Suggest files that should be archived based on inactivity.

        Scans a directory for files that have not been modified in the
        specified number of days and suggests moving them to Archive.

        Args:
            directory: Directory to scan for inactive files.
            inactive_days: Number of days without modification to consider
                a file inactive. Defaults to 180.

        Returns:
            List of MoveSuggestion objects for files that should be archived.
        """
        suggestions: list[MoveSuggestion] = []

        if not directory.exists() or not directory.is_dir():
            return suggestions

        now = time.time()

        try:
            files = [f for f in directory.rglob("*") if f.is_file()]
        except OSError as e:
            logger.error("Cannot scan directory %s: %s", directory, e, exc_info=True)
            return suggestions

        for file_path in files:
            try:
                stat = file_path.stat()
                days_inactive = (now - stat.st_mtime) / 86400.0

                if days_inactive >= inactive_days:
                    target_path = self._compute_target_path_for_category(
                        file_path,
                        PARACategory.ARCHIVE,
                    )
                    confidence = min(0.95, 0.5 + (days_inactive / (inactive_days * 3)))

                    suggestions.append(
                        MoveSuggestion(
                            file_path=file_path,
                            target_category=PARACategory.ARCHIVE,
                            target_path=target_path,
                            confidence=confidence,
                            reasoning=[
                                f"File has not been modified in {int(days_inactive)} days "
                                f"(threshold: {inactive_days} days)",
                            ],
                        )
                    )
            except OSError as e:
                logger.warning("Cannot stat file %s: %s", file_path, e, exc_info=True)

        # Sort by inactivity (most inactive first)
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_target_path(
        self,
        file_path: Path,
        suggestion: PARASuggestion,
    ) -> Path:
        """Compute the target path for a file based on its suggestion.

        Args:
            file_path: Original file path.
            suggestion: The PARA suggestion.

        Returns:
            Target path within the PARA directory structure.
        """
        category_dir = self._config.get_category_directory(suggestion.category)
        base = self._root_dir / category_dir

        if suggestion.suggested_subfolder:
            base = base / suggestion.suggested_subfolder

        return base / file_path.name

    def _compute_target_path_for_category(
        self,
        file_path: Path,
        category: PARACategory,
    ) -> Path:
        """Compute target path for a specific category.

        Args:
            file_path: Original file path.
            category: Target PARA category.

        Returns:
            Target path within the PARA directory structure.
        """
        category_dir = self._config.get_category_directory(category)
        return self._root_dir / category_dir / file_path.name

    def _is_already_organized(
        self,
        file_path: Path,
        target_category: PARACategory,
    ) -> bool:
        """Check if a file is already in the correct PARA directory.

        Args:
            file_path: Current file path.
            target_category: Expected PARA category.

        Returns:
            True if the file is already in the correct category directory.
        """
        category_dir = self._config.get_category_directory(target_category)
        expected_parent = self._root_dir / category_dir

        try:
            file_resolved = file_path.resolve()
            expected_resolved = expected_parent.resolve()
            return str(file_resolved).startswith(str(expected_resolved))
        except OSError:
            return False

    def _resolve_collision(self, destination: Path) -> Path:
        """Resolve filename collision by appending a counter.

        Args:
            destination: Desired destination path.

        Returns:
            A non-colliding path (original or with counter appended).
        """
        if not destination.exists():
            return destination

        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent

        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            candidate = parent / new_name
            if not candidate.exists():
                return candidate
            counter += 1
            if counter > 1000:
                raise OSError(
                    f"Cannot resolve collision for {destination}: "
                    f"too many existing files with same name"
                )
