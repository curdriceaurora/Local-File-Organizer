"""Migration support for legacy path locations to canonical XDG structure."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def detect_legacy_paths(home: Path, config_home: Path, data_home: Path) -> list[Path]:
    """Detect legacy path locations that need migration.

    Checks for:
    - ~/.file-organizer (common mistake variant 1)
    - ~/.file_organizer (underscore variant)
    - ~/.config/file-organizer (old canonical location before XDG_DATA_HOME split)
    """
    legacy_paths = []

    candidates = [
        home / ".file-organizer",
        home / ".file_organizer",
        config_home / "file-organizer",  # Old location in config_home
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            legacy_paths.append(candidate)

    return legacy_paths


class PathMigrator:
    """Handles migration from legacy paths to canonical XDG structure."""

    def __init__(self, legacy_path: Path, canonical_path: Path):
        """Initialize migrator.

        Args:
            legacy_path: Source legacy path to migrate from
            canonical_path: Target canonical path to migrate to
        """
        self.legacy_path = legacy_path
        self.canonical_path = canonical_path
        self.backup_path: Path | None = None
        self.migration_log: dict[str, Any] = {}

    def backup_legacy_path(self) -> Path:
        """Create backup of legacy path before migration.

        Returns:
            Path to backup directory
        """
        # Use microseconds to ensure uniqueness for rapid successive migrations
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        backup = self.legacy_path.parent / f"{self.legacy_path.name}.backup.{timestamp}"
        shutil.copytree(self.legacy_path, backup)
        self.backup_path = backup
        return backup

    def migrate(self) -> None:
        """Migrate files from legacy to canonical location."""
        if not self.legacy_path.exists():
            return

        # Create backup first
        self.backup_legacy_path()

        # Ensure canonical path exists
        self.canonical_path.mkdir(parents=True, exist_ok=True)

        # Copy all files from legacy to canonical
        for item in self.legacy_path.rglob("*"):
            if item.is_file():
                relative = item.relative_to(self.legacy_path)
                target = self.canonical_path / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    def create_migration_log(self) -> dict[str, Any]:
        """Create migration log entry for audit trail.

        Returns:
            Dictionary with migration details
        """
        return {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "from": str(self.legacy_path),
            "to": str(self.canonical_path),
            "status": "pending",
            "backup": str(self.backup_path) if self.backup_path else None,
        }

    def finalize_migration(self) -> None:
        """Finalize migration after verification, persisting audit trail."""
        log = self.create_migration_log()
        log["status"] = "completed"
        self.migration_log = log

        # Persist log to audit trail for data integrity and compliance
        self.canonical_path.mkdir(parents=True, exist_ok=True)
        audit_file = self.canonical_path / ".migration-audit.json"
        audit_file.write_text(json.dumps(log, indent=2, default=str))

        # Could optionally remove legacy path here
        # For now, leave it with backup created for safety


def resolve_legacy_path(new_dir: Path, legacy_dir: Path) -> Path:
    """Return *new_dir* when it already contains data, otherwise fall back to *legacy_dir*.

    This provides a seamless upgrade experience: users who have existing data
    under the old hardcoded location (e.g. ``~/.file_organizer/``) will
    continue to see it until a full migration is performed.  New installs
    get the platform-appropriate XDG/``platformdirs`` path immediately.

    Args:
        new_dir: The new canonical directory (from ``get_data_dir()`` /
            ``get_config_dir()``).
        legacy_dir: The old hardcoded directory that may contain user data.

    Returns:
        *new_dir* if it exists and is non-empty **or** *legacy_dir* does not
        exist / is empty; *legacy_dir* otherwise.
    """
    try:
        if new_dir.exists() and any(new_dir.iterdir()):
            return new_dir
    except OSError:
        pass

    try:
        if legacy_dir.exists() and any(legacy_dir.iterdir()):
            return legacy_dir
    except OSError:
        pass

    return new_dir
