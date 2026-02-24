"""Checkpoint management for resumable batch processing.

This module provides the CheckpointManager class for creating, loading,
and updating checkpoints that track which files have been processed and
store content hashes for detecting file modifications between runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from file_organizer.parallel.models import Checkpoint

logger = logging.getLogger(__name__)

_DEFAULT_CHECKPOINTS_DIR = Path.home() / ".file-organizer" / "checkpoints"

_HASH_CHUNK_SIZE = 8192


def compute_file_hash(path: Path) -> str:
    """Compute the SHA-256 hash of a file's contents.

    Reads the file in chunks to handle large files efficiently.

    Args:
        path: Path to the file to hash.

    Returns:
        Hex-encoded SHA-256 digest string.

    Raises:
        OSError: If the file cannot be read.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class CheckpointManager:
    """Manages checkpoint files for resumable batch processing.

    Each checkpoint is stored as a JSON file named ``{job_id}.checkpoint.json``
    in the configured checkpoints directory.

    Args:
        checkpoints_dir: Directory where checkpoint files are stored.
            Defaults to ``~/.file-organizer/checkpoints/``.
    """

    def __init__(self, checkpoints_dir: Path | None = None) -> None:
        """Set up the checkpoint manager with the given directory."""
        self._checkpoints_dir = checkpoints_dir or _DEFAULT_CHECKPOINTS_DIR

    @property
    def checkpoints_dir(self) -> Path:
        """Return the directory where checkpoint files are stored."""
        return self._checkpoints_dir

    def _ensure_dir(self) -> None:
        """Create the checkpoints directory if it does not exist."""
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _checkpoint_path(self, job_id: str) -> Path:
        """Return the file path for a given job's checkpoint."""
        return self._checkpoints_dir / f"{job_id}.checkpoint.json"

    def create_checkpoint(
        self,
        job_id: str,
        completed_files: list[Path],
        pending_files: list[Path],
    ) -> Checkpoint:
        """Create a new checkpoint for a job.

        Computes file hashes for all completed and pending files that exist
        on disk, then persists the checkpoint to a JSON file.

        Args:
            job_id: Identifier of the associated job.
            completed_files: Files already processed.
            pending_files: Files remaining to be processed.

        Returns:
            The newly created Checkpoint.
        """
        file_hashes: dict[str, str] = {}
        all_files = list(completed_files) + list(pending_files)
        for path in all_files:
            try:
                file_hashes[str(path)] = compute_file_hash(path)
            except OSError:
                logger.warning("Cannot hash file (may not exist): %s", path)

        checkpoint = Checkpoint(
            job_id=job_id,
            completed_paths=list(completed_files),
            pending_paths=list(pending_files),
            file_hashes=file_hashes,
            last_updated=datetime.now(UTC),
        )
        self.save_checkpoint(checkpoint)
        return checkpoint

    def load_checkpoint(self, job_id: str) -> Checkpoint | None:
        """Load a checkpoint from disk.

        Args:
            job_id: Identifier of the job whose checkpoint to load.

        Returns:
            The deserialized Checkpoint, or None if it does not exist.
        """
        path = self._checkpoint_path(job_id)
        if not path.exists():
            logger.debug("Checkpoint file not found: %s", path)
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return Checkpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to load checkpoint %s: %s", job_id, exc)
            return None

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint to disk using atomic write.

        Args:
            checkpoint: The checkpoint to save.
        """
        self._ensure_dir()
        path = self._checkpoint_path(checkpoint.job_id)
        data = checkpoint.to_dict()

        # Atomic write: write to temp file, then rename
        temp_path = path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            temp_path.replace(path)
            logger.debug("Saved checkpoint for job %s", checkpoint.job_id)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def update_checkpoint_state(
        self,
        checkpoint: Checkpoint,
        completed_file: Path,
    ) -> None:
        """Update the checkpoint object in-memory to mark a file as completed.

        This moves the file from pending to completed and updates its content hash.
        It does NOT persist the change to disk.

        Args:
            checkpoint: The checkpoint object to update.
            completed_file: The file that has been processed.
        """
        resolved = completed_file
        # Keep list model compatibility but avoid rebuilding the full list.
        try:
            checkpoint.pending_paths.remove(resolved)
        except ValueError:
            pass

        if resolved not in checkpoint.completed_paths:
            checkpoint.completed_paths.append(resolved)

        # Update hash if the file exists
        try:
            checkpoint.file_hashes[str(resolved)] = compute_file_hash(resolved)
        except OSError:
            pass

        checkpoint.last_updated = datetime.now(UTC)

    def update_checkpoint(
        self,
        job_id: str,
        completed_file: Path,
    ) -> Checkpoint | None:
        """Mark a single file as completed and immediately persist to disk.

        WARNING: This performs a full disk read/write cycle. For batch processing,
        use update_checkpoint_state() and save_checkpoint() manually.

        Args:
            job_id: Identifier of the associated job.
            completed_file: Path of the file that just finished processing.

        Returns:
            The updated Checkpoint, or None if no checkpoint exists.
        """
        checkpoint = self.load_checkpoint(job_id)
        if checkpoint is None:
            logger.warning("Cannot update checkpoint: no checkpoint for job %s", job_id)
            return None

        self.update_checkpoint_state(checkpoint, completed_file)
        self.save_checkpoint(checkpoint)
        return checkpoint

    def delete_checkpoint(self, job_id: str) -> bool:
        """Delete a checkpoint file.

        Args:
            job_id: Identifier of the job whose checkpoint to delete.

        Returns:
            True if the file was deleted, False if it did not exist.
        """
        path = self._checkpoint_path(job_id)
        if path.exists():
            path.unlink()
            logger.debug("Deleted checkpoint: %s", path)
            return True
        return False

    def has_file_changed(self, checkpoint: Checkpoint, path: Path) -> bool:
        """Check whether a file has been modified since the checkpoint was created.

        Compares the current file hash against the stored hash. If no stored
        hash exists or the file cannot be read, the file is considered changed.

        Args:
            checkpoint: The checkpoint containing stored hashes.
            path: Path to the file to check.

        Returns:
            True if the file has changed or cannot be verified.
        """
        stored_hash = checkpoint.file_hashes.get(str(path))
        if stored_hash is None:
            return True

        try:
            current_hash = compute_file_hash(path)
        except OSError:
            return True

        return current_hash != stored_hash
