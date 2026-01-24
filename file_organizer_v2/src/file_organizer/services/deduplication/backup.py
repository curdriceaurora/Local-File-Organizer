"""
Backup and restore functionality for safe file operations.

This module provides safe backup management for file operations, including:
- Creating backups before deletion
- Managing backup directory structure
- Maintaining backup manifests with metadata
- Restoring files from backups
- Cleaning up old backups
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# fcntl is Unix-only, not available on Windows
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False


class BackupManager:
    """
    Manages file backups for safe duplicate removal operations.

    The BackupManager creates backups in a dedicated directory before any
    file deletion operations, maintains a manifest of all backups with
    timestamps and metadata, and provides restoration and cleanup capabilities.

    Attributes:
        backup_dir: Path to the backup directory (.file_organizer_backups/)
        manifest_path: Path to the backup manifest JSON file
    """

    BACKUP_DIR_NAME = ".file_organizer_backups"
    MANIFEST_FILE = "manifest.json"

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the BackupManager.

        Args:
            base_dir: Base directory for backups. If None, uses current working directory.
        """
        if base_dir is None:
            base_dir = Path.cwd()

        self.backup_dir = Path(base_dir) / self.BACKUP_DIR_NAME
        self.manifest_path = self.backup_dir / self.MANIFEST_FILE

        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manifest if it doesn't exist
        if not self.manifest_path.exists():
            self._save_manifest({})

    def create_backup(self, file_path: Path) -> Path:
        """
        Create a backup of the specified file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the created backup file

        Raises:
            FileNotFoundError: If the source file doesn't exist
            PermissionError: If unable to create backup due to permissions
            IOError: If backup creation fails
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Generate unique backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_filename = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = (self.backup_dir / backup_filename).resolve()

        # Copy file to backup directory
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as e:
            raise OSError(f"Failed to create backup: {e}")

        # Update manifest
        manifest = self._load_manifest()
        manifest[str(backup_path)] = {
            "original_path": str(file_path),
            "backup_path": str(backup_path),
            "backup_time": datetime.now().isoformat(),
            "file_size": file_path.stat().st_size,
            "original_mtime": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        }
        self._save_manifest(manifest)

        return backup_path

    def restore_backup(self, backup_path: Path, target_path: Optional[Path] = None) -> Path:
        """
        Restore a file from backup.

        Args:
            backup_path: Path to the backup file
            target_path: Target path for restoration. If None, restores to original location.

        Returns:
            Path to the restored file

        Raises:
            FileNotFoundError: If the backup file doesn't exist
            ValueError: If backup is not in manifest
            IOError: If restoration fails
        """
        backup_path = Path(backup_path).resolve()

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Get original path from manifest
        manifest = self._load_manifest()
        backup_key = str(backup_path)

        if backup_key not in manifest:
            raise ValueError(f"Backup not found in manifest: {backup_path}")

        # Determine target path
        if target_path is None:
            target_path = Path(manifest[backup_key]["original_path"])
        else:
            target_path = Path(target_path).resolve()

        # Create parent directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy backup to target location
        try:
            shutil.copy2(backup_path, target_path)
        except Exception as e:
            raise OSError(f"Failed to restore backup: {e}")

        return target_path

    def cleanup_old_backups(self, max_age_days: int = 30) -> list[Path]:
        """
        Remove backups older than the specified age.

        Args:
            max_age_days: Maximum age in days for backups to keep

        Returns:
            List of paths to removed backup files
        """
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")

        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        manifest = self._load_manifest()
        removed_backups = []

        # Find and remove old backups
        for backup_key, _metadata in list(manifest.items()):
            backup_time = datetime.fromisoformat(metadata["backup_time"])

            if backup_time < cutoff_date:
                backup_path = Path(backup_key)

                # Remove backup file if it exists
                if backup_path.exists():
                    try:
                        backup_path.unlink()
                        removed_backups.append(backup_path)
                    except Exception:
                        # Continue even if deletion fails
                        pass

                # Remove from manifest
                del manifest[backup_key]

        # Save updated manifest
        self._save_manifest(manifest)

        return removed_backups

    def get_backup_info(self, backup_path: Path) -> Optional[dict]:
        """
        Get metadata for a specific backup.

        Args:
            backup_path: Path to the backup file

        Returns:
            Dictionary containing backup metadata, or None if not found
        """
        manifest = self._load_manifest()
        backup_key = str(Path(backup_path).resolve())
        return manifest.get(backup_key)

    def list_backups(self) -> list[dict]:
        """
        List all backups with their metadata.

        Returns:
            List of dictionaries containing backup information
        """
        manifest = self._load_manifest()

        backups = []
        for backup_key, _metadata in manifest.items():
            backup_info = metadata.copy()
            backup_info["exists"] = Path(backup_key).exists()
            backups.append(backup_info)

        # Sort by backup time (newest first)
        backups.sort(key=lambda x: x["backup_time"], reverse=True)

        return backups

    def get_statistics(self) -> dict:
        """
        Get statistics about the backup system.

        Returns:
            Dictionary containing backup statistics
        """
        manifest = self._load_manifest()

        total_backups = len(manifest)
        total_size = 0
        existing_backups = 0

        for backup_key, _metadata in manifest.items():
            backup_path = Path(backup_key)
            if backup_path.exists():
                existing_backups += 1
                total_size += backup_path.stat().st_size

        return {
            "total_backups": total_backups,
            "existing_backups": existing_backups,
            "missing_backups": total_backups - existing_backups,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "backup_directory": str(self.backup_dir),
        }

    def verify_backups(self) -> list[str]:
        """
        Verify integrity of all backups.

        Returns:
            List of backup paths that are missing or corrupted
        """
        manifest = self._load_manifest()
        issues = []

        for backup_key, _metadata in manifest.items():
            backup_path = Path(backup_key)

            # Check if backup file exists
            if not backup_path.exists():
                issues.append(f"Missing: {backup_key}")
                continue

            # Check if file size matches
            if backup_path.stat().st_size != metadata["file_size"]:
                issues.append(f"Size mismatch: {backup_key}")

        return issues

    def _load_manifest(self) -> dict:
        """
        Load the backup manifest from disk with file locking.

        Returns:
            Dictionary containing manifest data
        """
        if not self.manifest_path.exists():
            return {}

        try:
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                # Acquire shared lock for reading (Unix only)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    # Release lock (Unix only)
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, OSError):
            # If manifest is corrupted, start fresh
            return {}

    def _save_manifest(self, manifest: dict) -> None:
        """
        Save the backup manifest to disk with file locking.

        Args:
            manifest: Dictionary containing manifest data
        """
        try:
            # Open in read+ mode to avoid truncating before lock
            mode = 'r+' if self.manifest_path.exists() else 'w'
            with open(self.manifest_path, mode, encoding='utf-8') as f:
                # Acquire exclusive lock for writing (Unix only)
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    # Truncate file after acquiring lock
                    if mode == 'r+':
                        f.seek(0)
                        f.truncate()
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
                    f.flush()
                finally:
                    # Release lock (Unix only)
                    if HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            raise OSError(f"Failed to save manifest: {e}") from e
