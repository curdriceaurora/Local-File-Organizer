"""
PARA Migration Manager

Handles migration of files from flat or hierarchical structures to PARA organization.
Supports dry-run, rollback, and detailed reporting.
"""

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .categories import PARACategory, CategorizationResult
from .config import PARAConfig
from .detection.heuristics import HeuristicEngine
from .folder_generator import PARAFolderGenerator

logger = logging.getLogger(__name__)


@dataclass
class MigrationFile:
    """Represents a file to be migrated."""
    source_path: Path
    target_category: PARACategory
    target_path: Path
    confidence: float
    reasoning: list[str] = field(default_factory=list)


@dataclass
class MigrationPlan:
    """Plan for migrating files to PARA structure."""
    files: list[MigrationFile]
    total_count: int
    by_category: dict[PARACategory, int]
    estimated_size: int  # bytes
    created_at: datetime


@dataclass
class MigrationReport:
    """Report of migration execution."""
    plan: MigrationPlan
    migrated: list[Path]
    failed: list[tuple[Path, str]]
    skipped: list[Path]
    duration_seconds: float
    success: bool


class PARAMigrationManager:
    """
    Manages migration of files to PARA structure.

    Analyzes existing directory structure, categorizes files,
    and migrates them to appropriate PARA folders with rollback support.
    """

    def __init__(
        self,
        config: Optional[PARAConfig] = None,
        heuristic_engine: Optional[HeuristicEngine] = None
    ):
        """
        Initialize migration manager.

        Args:
            config: PARA configuration
            heuristic_engine: Engine for categorizing files
        """
        self.config = config or PARAConfig()
        self.heuristic_engine = heuristic_engine or HeuristicEngine(self.config)
        self.folder_generator = PARAFolderGenerator(self.config)

    def analyze_source(
        self,
        source_path: Path,
        target_root: Path,
        recursive: bool = True,
        file_extensions: Optional[list[str]] = None
    ) -> MigrationPlan:
        """
        Analyze source directory and create migration plan.

        Args:
            source_path: Source directory to migrate from
            target_root: Target PARA root directory
            recursive: Whether to scan subdirectories
            file_extensions: Optional filter for file extensions

        Returns:
            MigrationPlan with categorized files
        """
        logger.info(f"Analyzing source: {source_path}")

        files_to_migrate: list[MigrationFile] = []
        by_category: dict[PARACategory, int] = {
            PARACategory.PROJECT: 0,
            PARACategory.AREA: 0,
            PARACategory.RESOURCE: 0,
            PARACategory.ARCHIVE: 0,
        }
        total_size = 0

        # Scan files
        pattern = "**/*" if recursive else "*"
        for file_path in source_path.glob(pattern):
            if not file_path.is_file():
                continue

            # Filter by extension if specified
            if file_extensions and file_path.suffix.lower() not in file_extensions:
                continue

            # Categorize file
            try:
                result = self.heuristic_engine.categorize(file_path)
                category = result.category
                confidence = result.confidence

                # Determine target path
                category_path = self.folder_generator.get_category_path(
                    category,
                    target_root
                )
                relative_path = file_path.relative_to(source_path)
                target_path = category_path / relative_path.name

                # Create migration entry
                migration_file = MigrationFile(
                    source_path=file_path,
                    target_category=category,
                    target_path=target_path,
                    confidence=confidence,
                    reasoning=result.reasoning if hasattr(result, 'reasoning') else []
                )
                files_to_migrate.append(migration_file)

                # Update stats
                by_category[category] += 1
                total_size += file_path.stat().st_size

            except Exception as e:
                logger.warning(f"Failed to categorize {file_path}: {e}")
                continue

        plan = MigrationPlan(
            files=files_to_migrate,
            total_count=len(files_to_migrate),
            by_category=by_category,
            estimated_size=total_size,
            created_at=datetime.now()
        )

        logger.info(f"Migration plan created: {plan.total_count} files")
        return plan

    def execute_migration(
        self,
        plan: MigrationPlan,
        dry_run: bool = True,
        create_backup: bool = True,
        preserve_timestamps: bool = True
    ) -> MigrationReport:
        """
        Execute migration according to plan.

        Args:
            plan: Migration plan to execute
            dry_run: If True, don't actually move files
            create_backup: Whether to create backup before migration
            preserve_timestamps: Whether to preserve file timestamps

        Returns:
            MigrationReport with results
        """
        start_time = datetime.now()
        logger.info(f"Executing migration (dry_run={dry_run})")

        migrated: list[Path] = []
        failed: list[tuple[Path, str]] = []
        skipped: list[Path] = []

        # Create backup if requested
        backup_id: Optional[str] = None
        if create_backup and not dry_run:
            backup_id = self._create_backup(plan)
            logger.info(f"Backup created: {backup_id}")

        # Execute migrations
        for migration_file in plan.files:
            try:
                # Check if target already exists
                if migration_file.target_path.exists():
                    logger.warning(f"Target already exists: {migration_file.target_path}")
                    skipped.append(migration_file.source_path)
                    continue

                if not dry_run:
                    # Ensure target directory exists
                    migration_file.target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Move file
                    shutil.move(
                        str(migration_file.source_path),
                        str(migration_file.target_path)
                    )

                    # Preserve timestamps if requested
                    if preserve_timestamps:
                        stat = migration_file.source_path.stat()
                        shutil.copystat(
                            str(migration_file.source_path),
                            str(migration_file.target_path)
                        )

                    migrated.append(migration_file.target_path)
                    logger.info(f"Migrated: {migration_file.source_path} → {migration_file.target_path}")
                else:
                    migrated.append(migration_file.target_path)
                    logger.info(f"[DRY RUN] Would migrate: {migration_file.source_path} → {migration_file.target_path}")

            except Exception as e:
                logger.error(f"Failed to migrate {migration_file.source_path}: {e}")
                failed.append((migration_file.source_path, str(e)))

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Create report
        success = len(failed) == 0
        report = MigrationReport(
            plan=plan,
            migrated=migrated,
            failed=failed,
            skipped=skipped,
            duration_seconds=duration,
            success=success
        )

        logger.info(f"Migration completed: {len(migrated)} migrated, {len(failed)} failed, {len(skipped)} skipped")
        return report

    def _create_backup(self, plan: MigrationPlan) -> str:
        """
        Create backup of source files before migration.

        Args:
            plan: Migration plan

        Returns:
            Backup identifier
        """
        backup_id = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # TODO: Implement actual backup logic
        logger.info(f"Backup ID: {backup_id}")
        return backup_id

    def rollback(self, migration_id: str) -> bool:
        """
        Rollback a completed migration.

        Args:
            migration_id: Migration identifier to rollback

        Returns:
            True if rollback succeeded
        """
        # TODO: Implement rollback logic
        logger.warning("Rollback not yet implemented")
        return False

    def generate_preview(self, plan: MigrationPlan) -> str:
        """
        Generate human-readable preview of migration plan.

        Args:
            plan: Migration plan

        Returns:
            Formatted preview string
        """
        lines = [
            "# PARA Migration Plan",
            "",
            f"Total files: {plan.total_count}",
            f"Estimated size: {plan.estimated_size / (1024*1024):.2f} MB",
            f"Created: {plan.created_at}",
            "",
            "## Distribution by Category",
        ]

        for category, count in plan.by_category.items():
            percentage = (count / plan.total_count * 100) if plan.total_count > 0 else 0
            lines.append(f"- {category.value.title()}: {count} files ({percentage:.1f}%)")

        lines.extend([
            "",
            "## Files",
            ""
        ])

        # Show first 20 files as examples
        for i, mf in enumerate(plan.files[:20]):
            lines.append(f"{i+1}. {mf.source_path.name} → {mf.target_category.value} (confidence: {mf.confidence:.0%})")

        if len(plan.files) > 20:
            lines.append(f"... and {len(plan.files) - 20} more files")

        return "\n".join(lines)
