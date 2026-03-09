"""PARA Migration Manager.

Handles migration of files from flat or hierarchical structures to PARA organization.
Supports dry-run, rollback, and detailed reporting with full backup/recovery capabilities.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from file_organizer.config.path_manager import PathManager

from .categories import PARACategory
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


@dataclass
class BackupMetadata:
    """Metadata for a migration backup."""

    backup_id: str
    migration_id: str
    created_at: datetime
    files_backed_up: int
    total_size: int
    checksum: str  # SHA256 of file manifest
    source_root: Path
    status: str  # "created", "verified", "restored"
    restored_at: datetime | None = None
    file_entries: list[dict[str, Any]] = field(default_factory=list)


class BackupIntegrityError(Exception):
    """Raised when backup integrity check fails."""


class RollbackError(Exception):
    """Raised when rollback operation fails."""


class PARAMigrationManager:
    """Manages migration of files to PARA structure.

    Analyzes existing directory structure, categorizes files,
    and migrates them to appropriate PARA folders with rollback support.

    Backup/Recovery Features:
    - Creates full file backups before migration
    - Maintains backup metadata with integrity checksums
    - Supports rollback to pre-migration state
    - Verifies integrity of backups and restored files
    """

    def __init__(
        self, config: PARAConfig | None = None, heuristic_engine: HeuristicEngine | None = None
    ):
        """Initialize migration manager.

        Args:
            config: PARA configuration
            heuristic_engine: Engine for categorizing files
        """
        self.config = config or PARAConfig()
        if heuristic_engine is None:
            # Create heuristic engine from config settings
            self.heuristic_engine = HeuristicEngine(
                enable_temporal=self.config.enable_temporal_heuristic,
                enable_content=self.config.enable_content_heuristic,
                enable_structural=self.config.enable_structural_heuristic,
                enable_ai=self.config.enable_ai_heuristic,
                thresholds=self.config.category_thresholds,
            )
        else:
            self.heuristic_engine = heuristic_engine
        self.folder_generator = PARAFolderGenerator(self.config)

        # Initialize backup directory
        self.path_manager = PathManager()
        self.backup_root = self.path_manager.data_dir / "migration-backups"
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def analyze_source(
        self,
        source_path: Path,
        target_root: Path,
        recursive: bool = True,
        file_extensions: list[str] | None = None,
    ) -> MigrationPlan:
        """Analyze source directory and create migration plan.

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
                result = self.heuristic_engine.evaluate(file_path)
                category = result.recommended_category
                if category is None:
                    # Default to Resource if no clear category
                    category = PARACategory.RESOURCE
                confidence = result.overall_confidence

                # Determine target path
                category_path = self.folder_generator.get_category_path(category, target_root)
                relative_path = file_path.relative_to(source_path)
                target_path = category_path / relative_path.name

                # Create migration entry
                # Extract reasoning from category scores
                reasoning = []
                if category in result.scores:
                    reasoning = result.scores[category].signals

                migration_file = MigrationFile(
                    source_path=file_path,
                    target_category=category,
                    target_path=target_path,
                    confidence=confidence,
                    reasoning=reasoning,
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
            created_at=datetime.now(UTC),
        )

        logger.info(f"Migration plan created: {plan.total_count} files")
        return plan

    def execute_migration(
        self,
        plan: MigrationPlan,
        dry_run: bool = True,
        create_backup: bool = True,
        preserve_timestamps: bool = True,
    ) -> MigrationReport:
        """Execute migration according to plan.

        Args:
            plan: Migration plan to execute
            dry_run: If True, don't actually move files
            create_backup: Whether to create backup before migration
            preserve_timestamps: Whether to preserve file timestamps

        Returns:
            MigrationReport with results
        """
        start_time = datetime.now(UTC)
        logger.info(f"Executing migration (dry_run={dry_run})")

        migrated: list[Path] = []
        failed: list[tuple[Path, str]] = []
        skipped: list[Path] = []

        # Create backup if requested
        backup_id: str | None = None
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

                    # Preserve timestamps if requested (before moving)
                    if preserve_timestamps:
                        # Get stat info before moving
                        source_stat = migration_file.source_path.stat()

                    # Move file
                    shutil.move(str(migration_file.source_path), str(migration_file.target_path))

                    # Apply preserved timestamps after moving
                    if preserve_timestamps:
                        # Restore timestamps on target
                        os.utime(
                            migration_file.target_path, (source_stat.st_atime, source_stat.st_mtime)
                        )

                    migrated.append(migration_file.target_path)
                    logger.info(
                        f"Migrated: {migration_file.source_path} → {migration_file.target_path}"
                    )
                else:
                    migrated.append(migration_file.target_path)
                    logger.info(
                        f"[DRY RUN] Would migrate: {migration_file.source_path} → {migration_file.target_path}"
                    )

            except Exception as e:
                logger.error(f"Failed to migrate {migration_file.source_path}: {e}")
                failed.append((migration_file.source_path, str(e)))

        # Calculate duration
        duration = (datetime.now(UTC) - start_time).total_seconds()

        # Create report
        success = len(failed) == 0
        report = MigrationReport(
            plan=plan,
            migrated=migrated,
            failed=failed,
            skipped=skipped,
            duration_seconds=duration,
            success=success,
        )

        logger.info(
            f"Migration completed: {len(migrated)} migrated, {len(failed)} failed, {len(skipped)} skipped"
        )
        return report

    def _create_backup(self, plan: MigrationPlan) -> str:
        """Create backup of source files before migration.

        Creates a complete backup of all files to be migrated with metadata,
        integrity checksums, and recovery information.

        Args:
            plan: Migration plan

        Returns:
            Backup identifier

        Raises:
            Exception: If backup creation fails
        """
        now_utc = datetime.now(UTC)
        migration_id = f"migration_{now_utc.strftime('%Y%m%dT%H%M%S%f')}Z"
        backup_id = f"backup_{migration_id}"

        logger.info(f"Creating backup: {backup_id}")

        # Create backup directory
        backup_dir = self.backup_root / backup_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        file_entries = []
        total_size = 0

        try:
            # Backup each file with metadata
            for migration_file in plan.files:
                source = migration_file.source_path
                if not source.exists():
                    logger.warning(f"Source file missing during backup: {source}")
                    continue

                try:
                    # Create relative path structure in backup preserving directory hierarchy.
                    # Compute a common base for all source files; fall back to source.name
                    # when source is not relative to that base (avoids ValueError from relative_to).
                    common_base = plan.files[0].source_path.parent if plan.files else source.parent
                    try:
                        rel_path = source.relative_to(common_base)
                    except ValueError:
                        rel_path = Path(source.name)
                    backup_file = backup_dir / rel_path
                    backup_file.parent.mkdir(parents=True, exist_ok=True)

                    # Copy file with metadata
                    shutil.copy2(str(source), str(backup_file))
                    file_size = backup_file.stat().st_size

                    # Calculate file hash for integrity verification
                    file_hash = self._calculate_file_hash(backup_file)

                    # Record entry
                    file_entries.append(
                        {
                            "original_path": str(source),
                            "backup_path": str(backup_file),
                            "size": file_size,
                            "hash": file_hash,
                            "category": migration_file.target_category.value,
                            "confidence": migration_file.confidence,
                        }
                    )

                    total_size += file_size

                except Exception as e:
                    logger.warning(f"Failed to backup {source}: {e}")
                    continue

            # Create manifest file
            manifest = BackupMetadata(
                backup_id=backup_id,
                migration_id=migration_id,
                created_at=now_utc,
                files_backed_up=len(file_entries),
                total_size=total_size,
                checksum="",  # Will be calculated after adding entries
                source_root=plan.files[0].source_path.parent if plan.files else Path.home(),
                status="created",
                file_entries=file_entries,
            )

            # Calculate manifest checksum (across all file hashes)
            manifest_checksum = self._calculate_manifest_checksum(file_entries)
            manifest.checksum = manifest_checksum

            # Save manifest
            manifest_file = backup_dir / "manifest.json"
            with open(manifest_file, "w") as f:
                # Serialize with custom JSON encoder for datetime and Path
                manifest_data = {
                    "backup_id": manifest.backup_id,
                    "migration_id": manifest.migration_id,
                    "created_at": manifest.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "files_backed_up": manifest.files_backed_up,
                    "total_size": manifest.total_size,
                    "checksum": manifest.checksum,
                    "source_root": str(manifest.source_root),
                    "status": manifest.status,
                    "restored_at": manifest.restored_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if manifest.restored_at
                    else None,
                    "file_entries": manifest.file_entries,
                }
                json.dump(manifest_data, f, indent=2)

            # Verify backup integrity (only check files that were actually backed up)
            if file_entries:
                self._verify_backup(backup_dir, manifest)
            else:
                logger.warning("No files were backed up")

            logger.info(f"Backup created successfully: {backup_id}")
            logger.info(f"  Files: {len(file_entries)}")
            logger.info(f"  Total size: {total_size / (1024 * 1024):.2f} MB")

            return backup_id

        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            # Clean up partial backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            raise

    def rollback(self, backup_id: str) -> bool:
        """Rollback a completed migration using backup data.

        Restores all files from backup to their original locations,
        verifies integrity, and cleans up the backup.

        Args:
            backup_id: Backup identifier to rollback

        Returns:
            True if rollback succeeded

        Raises:
            RollbackError: If rollback fails with details
        """
        logger.info(f"Starting rollback from backup: {backup_id}")

        backup_dir = self.backup_root / backup_id
        if not backup_dir.exists():
            raise RollbackError(f"Backup directory not found: {backup_dir}")

        try:
            # Load and verify manifest
            manifest_file = backup_dir / "manifest.json"
            if not manifest_file.exists():
                raise RollbackError(f"Backup manifest not found: {manifest_file}")

            with open(manifest_file) as f:
                manifest_data = json.load(f)

            # Verify integrity before restoring
            self._verify_backup_integrity(backup_dir, manifest_data)

            # Restore files
            restored_count = 0
            failed_restores = []

            for entry in manifest_data.get("file_entries", []):
                original_path = Path(entry["original_path"])
                backup_path = Path(entry["backup_path"])
                expected_hash = entry["hash"]

                try:
                    # Create target directory
                    original_path.parent.mkdir(parents=True, exist_ok=True)

                    # Restore file
                    if original_path.exists():
                        # Backup the current file (which was migrated) using a unique name
                        # to prevent collisions on repeated rollbacks.
                        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "Z"
                        migrated_backup = original_path.with_name(
                            f"{original_path.stem}.{ts}.migrated{original_path.suffix}"
                        )
                        shutil.copy2(str(original_path), str(migrated_backup))
                        logger.debug(f"Saved migrated file: {migrated_backup}")

                    shutil.copy2(str(backup_path), str(original_path))

                    # Verify restored file
                    restored_hash = self._calculate_file_hash(original_path)
                    if restored_hash != expected_hash:
                        raise RollbackError(
                            f"File integrity check failed after restore: {original_path}"
                        )

                    restored_count += 1
                    logger.debug(f"Restored: {original_path}")

                except Exception as e:
                    logger.error(f"Failed to restore {original_path}: {e}")
                    failed_restores.append((str(original_path), str(e)))

            if failed_restores:
                raise RollbackError(
                    f"Rollback completed with {len(failed_restores)} failures: {failed_restores}"
                )

            # Update manifest status
            manifest_data["status"] = "restored"
            manifest_data["restored_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            with open(manifest_file, "w") as f:
                json.dump(manifest_data, f, indent=2)

            logger.info(f"Rollback completed successfully: {restored_count} files restored")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            if isinstance(e, RollbackError):
                raise
            raise RollbackError(f"Rollback operation failed: {e}") from e

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backups.

        Returns:
            List of backup metadata dictionaries
        """
        backups: list[dict[str, Any]] = []

        if not self.backup_root.exists():
            return backups

        for backup_dir in sorted(self.backup_root.iterdir(), reverse=True):
            if not backup_dir.is_dir():
                continue

            manifest_file = backup_dir / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file) as f:
                        manifest = json.load(f)
                    backups.append(manifest)
                except Exception as e:
                    logger.warning(f"Failed to read backup manifest {manifest_file}: {e}")

        return backups

    def verify_backup(self, backup_id: str) -> bool:
        """Verify integrity of a backup.

        Args:
            backup_id: Backup identifier

        Returns:
            True if backup is valid

        Raises:
            BackupIntegrityError: If backup is corrupted
        """
        backup_dir = self.backup_root / backup_id
        if not backup_dir.exists():
            raise BackupIntegrityError(f"Backup not found: {backup_id}")

        manifest_file = backup_dir / "manifest.json"
        if not manifest_file.exists():
            raise BackupIntegrityError(f"Backup manifest not found: {backup_id}")

        try:
            with open(manifest_file) as f:
                manifest_data = json.load(f)

            self._verify_backup_integrity(backup_dir, manifest_data)
            logger.info(f"Backup verification passed: {backup_id}")
            return True

        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            raise BackupIntegrityError(f"Backup integrity check failed: {e}") from e

    def _verify_backup(self, backup_dir: Path, manifest: BackupMetadata) -> None:
        """Verify backup integrity.

        Args:
            backup_dir: Backup directory
            manifest: Backup metadata

        Raises:
            BackupIntegrityError: If verification fails
        """
        logger.info(f"Verifying backup integrity: {manifest.backup_id}")

        # Check all files exist and match hashes
        for entry in manifest.file_entries:
            backup_path = Path(entry["backup_path"])

            if not backup_path.exists():
                raise BackupIntegrityError(f"Backup file missing: {backup_path}")

            actual_hash = self._calculate_file_hash(backup_path)
            expected_hash = entry["hash"]

            if actual_hash != expected_hash:
                raise BackupIntegrityError(
                    f"File hash mismatch: {backup_path} "
                    f"(expected {expected_hash}, got {actual_hash})"
                )

        logger.info(f"Backup verification passed: {len(manifest.file_entries)} files verified")

    def _verify_backup_integrity(self, backup_dir: Path, manifest_data: dict[str, Any]) -> None:
        """Verify backup integrity from manifest data.

        Args:
            backup_dir: Backup directory
            manifest_data: Parsed manifest JSON

        Raises:
            BackupIntegrityError: If verification fails
        """
        logger.info("Verifying backup integrity from manifest")

        # Verify manifest checksum
        file_entries = manifest_data.get("file_entries", [])
        stored_checksum = manifest_data.get("checksum", "")
        calculated_checksum = self._calculate_manifest_checksum(file_entries)

        if stored_checksum != calculated_checksum:
            raise BackupIntegrityError(
                f"Manifest checksum mismatch "
                f"(expected {stored_checksum}, got {calculated_checksum})"
            )

        # Verify each file
        for entry in file_entries:
            backup_path = Path(entry["backup_path"])

            if not backup_path.exists():
                raise BackupIntegrityError(f"Backup file missing: {backup_path}")

            actual_hash = self._calculate_file_hash(backup_path)
            expected_hash = entry["hash"]

            if actual_hash != expected_hash:
                raise BackupIntegrityError(
                    f"File hash mismatch: {backup_path} "
                    f"(expected {expected_hash}, got {actual_hash})"
                )

    @staticmethod
    def _calculate_file_hash(file_path: Path) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex-encoded SHA256 hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def _calculate_manifest_checksum(file_entries: list[dict[str, Any]]) -> str:
        """Calculate checksum of all file hashes.

        Args:
            file_entries: List of file entries with hashes

        Returns:
            Hex-encoded SHA256 checksum
        """
        sha256_hash = hashlib.sha256()
        for entry in sorted(file_entries, key=lambda x: x["original_path"]):
            sha256_hash.update(entry["hash"].encode())
        return sha256_hash.hexdigest()

    def generate_preview(self, plan: MigrationPlan) -> str:
        """Generate human-readable preview of migration plan.

        Args:
            plan: Migration plan

        Returns:
            Formatted preview string
        """
        lines = [
            "# PARA Migration Plan",
            "",
            f"Total files: {plan.total_count}",
            f"Estimated size: {plan.estimated_size / (1024 * 1024):.2f} MB",
            f"Created: {plan.created_at}",
            "",
            "## Distribution by Category",
        ]

        for category, count in plan.by_category.items():
            percentage = (count / plan.total_count * 100) if plan.total_count > 0 else 0
            lines.append(f"- {category.value.title()}: {count} files ({percentage:.1f}%)")

        lines.extend(["", "## Files", ""])

        # Show first 20 files as examples
        for i, mf in enumerate(plan.files[:20]):
            lines.append(
                f"{i + 1}. {mf.source_path.name} → {mf.target_category.value} (confidence: {mf.confidence:.0%})"
            )

        if len(plan.files) > 20:
            lines.append(f"... and {len(plan.files) - 20} more files")

        return "\n".join(lines)
