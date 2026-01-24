"""
Johnny Decimal Migration Manager

Orchestrates the complete migration process from existing folder structures
to Johnny Decimal organization. Provides dry-run, rollback, and detailed reporting.
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .categories import NumberingScheme, get_default_scheme
from .numbering import JohnnyDecimalGenerator
from .scanner import FolderScanner, ScanResult
from .transformer import FolderTransformer, TransformationPlan, TransformationRule
from .validator import MigrationValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of a migration execution."""

    success: bool
    transformed_count: int
    failed_count: int
    skipped_count: int
    duration_seconds: float
    transformed_paths: List[Path] = field(default_factory=list)
    failed_paths: List[tuple[Path, str]] = field(default_factory=list)
    skipped_paths: List[Path] = field(default_factory=list)
    backup_path: Optional[Path] = None


@dataclass
class RollbackInfo:
    """Information needed to rollback a migration."""

    migration_id: str
    timestamp: datetime
    original_structure: Dict[str, tuple[str, str]]  # original_path -> (target_path, original_name)
    backup_path: Optional[Path]


class JohnnyDecimalMigrator:
    """
    Manages migration of existing folder structures to Johnny Decimal format.

    Provides complete workflow: scan → transform → validate → execute
    with dry-run preview and rollback capabilities.
    """

    def __init__(
        self,
        scheme: Optional[NumberingScheme] = None,
        preserve_original_names: bool = True,
    ):
        """
        Initialize the migrator.

        Args:
            scheme: Johnny Decimal numbering scheme (uses default if None)
            preserve_original_names: Keep original folder names after JD numbers
        """
        self.scheme = scheme or get_default_scheme()
        self.generator = JohnnyDecimalGenerator(self.scheme)
        self.scanner = FolderScanner(self.scheme)
        self.transformer = FolderTransformer(
            self.scheme, self.generator, preserve_original_names
        )
        self.validator = MigrationValidator(self.generator)
        self._rollback_history: List[RollbackInfo] = []

    def create_migration_plan(self, root_path: Path) -> tuple[TransformationPlan, ScanResult]:
        """
        Create a complete migration plan for a directory.

        Args:
            root_path: Root directory to migrate

        Returns:
            Tuple of (TransformationPlan, ScanResult)

        Raises:
            ValueError: If root_path is invalid
        """
        logger.info(f"Creating migration plan for {root_path}")

        # Step 1: Scan directory structure
        scan_result = self.scanner.scan_directory(root_path)

        logger.info(
            f"Scanned: {scan_result.total_folders} folders, "
            f"{scan_result.total_files} files"
        )

        # Step 2: Create transformation plan
        plan = self.transformer.create_transformation_plan(
            scan_result.folder_tree, root_path
        )

        logger.info(f"Plan created with {len(plan.rules)} transformations")

        return plan, scan_result

    def validate_plan(self, plan: TransformationPlan) -> ValidationResult:
        """
        Validate a transformation plan.

        Args:
            plan: Transformation plan to validate

        Returns:
            ValidationResult with any issues found
        """
        return self.validator.validate_plan(plan)

    def execute_migration(
        self,
        plan: TransformationPlan,
        dry_run: bool = True,
        create_backup: bool = True,
    ) -> MigrationResult:
        """
        Execute a transformation plan.

        Args:
            plan: Transformation plan to execute
            dry_run: If True, only preview changes without executing
            create_backup: Whether to create backup before migration

        Returns:
            MigrationResult with execution details
        """
        start_time = datetime.now()

        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Executing migration with "
            f"{len(plan.rules)} transformations"
        )

        transformed_paths: List[Path] = []
        failed_paths: List[tuple[Path, str]] = []
        skipped_paths: List[Path] = []
        backup_path: Optional[Path] = None
        rollback_info: Optional[RollbackInfo] = None

        # Create backup if requested
        if create_backup and not dry_run:
            try:
                backup_path = self._create_backup(plan.root_path)
                logger.info(f"Backup created at {backup_path}")

                # Initialize rollback info
                rollback_info = RollbackInfo(
                    migration_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                    timestamp=datetime.now(),
                    original_structure={},
                    backup_path=backup_path,
                )
            except Exception as e:
                logger.error(f"Failed to create backup: {e}")
                return MigrationResult(
                    success=False,
                    transformed_count=0,
                    failed_count=0,
                    skipped_count=0,
                    duration_seconds=0.0,
                    failed_paths=[(plan.root_path, f"Backup failed: {e}")],
                )

        # Execute transformations
        for rule in plan.rules:
            try:
                # Compute target path for both dry run and real execution
                target_path = rule.source_path.parent / rule.target_name

                if dry_run:
                    # Dry run - just log what would happen
                    logger.info(
                        f"[DRY RUN] Would rename: {rule.source_path.name} → {rule.target_name}"
                    )
                    transformed_paths.append(target_path)
                else:
                    # Check if target already exists

                    if target_path.exists() and target_path != rule.source_path:
                        logger.warning(f"Target already exists: {target_path}")
                        skipped_paths.append(rule.source_path)
                        continue

                    # Store original and target paths for rollback
                    if rollback_info:
                        rollback_info.original_structure[str(rule.source_path)] = (
                            str(target_path),
                            rule.source_path.name,
                        )

                    # Execute rename
                    rule.source_path.rename(target_path)
                    transformed_paths.append(target_path)
                    logger.info(f"Renamed: {rule.source_path.name} → {rule.target_name}")

            except Exception as e:
                error_msg = f"Failed to transform {rule.source_path}: {e}"
                logger.error(error_msg)
                failed_paths.append((rule.source_path, str(e)))

        # Save rollback info
        if rollback_info and not dry_run:
            self._save_rollback_info(rollback_info)
            self._rollback_history.append(rollback_info)

        duration = (datetime.now() - start_time).total_seconds()

        result = MigrationResult(
            success=(len(failed_paths) == 0),
            transformed_count=len(transformed_paths),
            failed_count=len(failed_paths),
            skipped_count=len(skipped_paths),
            duration_seconds=duration,
            transformed_paths=transformed_paths,
            failed_paths=failed_paths,
            skipped_paths=skipped_paths,
            backup_path=backup_path,
        )

        logger.info(
            f"Migration {'simulated' if dry_run else 'completed'}: "
            f"{result.transformed_count} transformed, "
            f"{result.failed_count} failed, "
            f"{result.skipped_count} skipped"
        )

        return result

    def rollback(self, migration_id: Optional[str] = None) -> bool:
        """
        Rollback a migration to original state.

        Args:
            migration_id: Specific migration to rollback (latest if None)

        Returns:
            True if rollback succeeded

        Raises:
            ValueError: If migration_id not found
        """
        if not self._rollback_history:
            logger.error("No migrations to rollback")
            return False

        # Find rollback info
        rollback_info = None
        if migration_id:
            for info in self._rollback_history:
                if info.migration_id == migration_id:
                    rollback_info = info
                    break
            if not rollback_info:
                raise ValueError(f"Migration ID not found: {migration_id}")
        else:
            rollback_info = self._rollback_history[-1]

        logger.info(f"Rolling back migration {rollback_info.migration_id}")

        try:
            # Restore original names
            for original_path_str, (target_path_str, original_name) in rollback_info.original_structure.items():
                current_path = Path(target_path_str)
                original_path = Path(original_path_str)

                if current_path.exists():
                    current_path.rename(original_path)
                    logger.debug(f"Restored: {current_path.name} → {original_name}")

            logger.info("Rollback completed successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def _create_backup(self, root_path: Path) -> Path:
        """
        Create backup of directory before migration.

        Args:
            root_path: Directory to backup

        Returns:
            Path to backup directory

        Raises:
            OSError: If backup creation fails
        """
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_path = root_path.parent / backup_name

        shutil.copytree(root_path, backup_path)
        logger.info(f"Created backup at {backup_path}")

        return backup_path

    def _save_rollback_info(self, rollback_info: RollbackInfo) -> None:
        """
        Save rollback information to disk.

        Args:
            rollback_info: Rollback information to save
        """
        rollback_file = Path.home() / ".file_organizer" / "rollback" / f"{rollback_info.migration_id}.json"
        rollback_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "migration_id": rollback_info.migration_id,
            "timestamp": rollback_info.timestamp.isoformat(),
            "original_structure": rollback_info.original_structure,
            "backup_path": str(rollback_info.backup_path) if rollback_info.backup_path else None,
        }

        with open(rollback_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Saved rollback info to {rollback_file}")

    def generate_preview(
        self,
        plan: TransformationPlan,
        scan_result: ScanResult,
        validation: Optional[ValidationResult] = None,
    ) -> str:
        """
        Generate comprehensive preview of migration.

        Args:
            plan: Transformation plan
            scan_result: Scan result
            validation: Optional validation result

        Returns:
            Formatted preview string
        """
        lines = [
            "# Johnny Decimal Migration Preview",
            "",
            "## Source Analysis",
            f"- Root: {scan_result.root_path}",
            f"- Total folders: {scan_result.total_folders}",
            f"- Total files: {scan_result.total_files}",
            f"- Total size: {scan_result.total_size / (1024**2):.2f} MB",
            f"- Max depth: {scan_result.max_depth}",
            "",
        ]

        if scan_result.detected_patterns:
            lines.append("## Detected Patterns")
            for pattern in scan_result.detected_patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        lines.extend([
            "## Migration Plan",
            f"- Total transformations: {len(plan.rules)}",
            f"- Conflicts: {len(plan.conflicts)}",
            f"- Warnings: {len(plan.warnings)}",
            "",
        ])

        if validation:
            lines.extend([
                "## Validation",
                f"- Status: {'✅ VALID' if validation.is_valid else '❌ INVALID'}",
                f"- Errors: {len(validation.errors)}",
                f"- Warnings: {len(validation.warnings)}",
                "",
            ])

        # Sample transformations
        lines.append("## Sample Transformations (first 10)")
        for rule in plan.rules[:10]:
            lines.append(f"- {rule.source_path.name} → {rule.target_name}")

        if len(plan.rules) > 10:
            lines.append(f"... and {len(plan.rules) - 10} more")

        lines.append("")

        return "\n".join(lines)

    def generate_report(self, result: MigrationResult) -> str:
        """
        Generate human-readable migration report.

        Args:
            result: Migration result

        Returns:
            Formatted report string
        """
        lines = [
            "# Migration Execution Report",
            "",
            f"Status: {'✅ SUCCESS' if result.success else '❌ FAILED'}",
            f"Duration: {result.duration_seconds:.2f} seconds",
            "",
            "## Statistics",
            f"- Transformed: {result.transformed_count}",
            f"- Failed: {result.failed_count}",
            f"- Skipped: {result.skipped_count}",
            "",
        ]

        if result.backup_path:
            lines.extend([
                "## Backup",
                f"- Location: {result.backup_path}",
                "",
            ])

        if result.failed_paths:
            lines.append("## Failures")
            for path, error in result.failed_paths:
                lines.append(f"- {path}: {error}")
            lines.append("")

        if result.skipped_paths:
            lines.append(f"## Skipped ({len(result.skipped_paths)} folders)")
            for path in result.skipped_paths[:10]:
                lines.append(f"- {path}")
            if len(result.skipped_paths) > 10:
                lines.append(f"... and {len(result.skipped_paths) - 10} more")
            lines.append("")

        return "\n".join(lines)
