"""Release automation script for File Organizer.

Provides utilities for version bumping, changelog generation,
release note creation, and pre-release validation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Project root is two levels above file_organizer_v2/scripts/
_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parents[1]
_V2_ROOT = _SCRIPTS_DIR.parent
_PYPROJECT_TOML = _V2_ROOT / "pyproject.toml"
_VERSION_FILE = _V2_ROOT / "src" / "file_organizer" / "version.py"
_INIT_FILE = _V2_ROOT / "src" / "file_organizer" / "__init__.py"
_CHANGELOG = _PROJECT_ROOT / "CHANGELOG.md"


@dataclass
class ValidationResult:
    """Result of a release validation check."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def _read_current_version_from_pyproject() -> str:
    """Read the current version from pyproject.toml."""
    content = _PYPROJECT_TOML.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find version in pyproject.toml")
    return match.group(1)


def _run_command(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or _PROJECT_ROOT,
    )


def bump_version(part: str) -> str:
    """Bump the version in pyproject.toml, version.py, and __init__.py.

    Args:
        part: Which part to bump: "major", "minor", or "patch".

    Returns:
        The new version string.

    Raises:
        ValueError: If part is not major/minor/patch.
        RuntimeError: If version cannot be read or updated.
    """
    if part not in ("major", "minor", "patch"):
        raise ValueError(f"Invalid version part: {part!r}. Must be 'major', 'minor', or 'patch'.")

    # Import version utilities from the package
    sys.path.insert(0, str(_V2_ROOT / "src"))
    from file_organizer.version import bump_version as _bump
    from file_organizer.version import parse_version

    current = _read_current_version_from_pyproject()
    # Strip pre-release for bumping, treating base version as the starting point
    info = parse_version(current)
    base_current = info.base_version
    new_version = _bump(base_current, part)

    # Update pyproject.toml
    _update_file_version(_PYPROJECT_TOML, current, new_version, pattern="version")

    # Update version.py
    _update_version_py(_VERSION_FILE, new_version)

    # Update __init__.py
    _update_init_py(_INIT_FILE, new_version)

    return new_version


def _update_file_version(filepath: Path, old_version: str, new_version: str, pattern: str) -> None:
    """Update a version string in a file."""
    content = filepath.read_text()
    if pattern == "version":
        # Match version = "X.Y.Z" or version = "X.Y.Z-pre"
        updated = re.sub(
            r'(version\s*=\s*")[^"]+(")',
            rf"\g<1>{new_version}\2",
            content,
            count=1,
        )
    else:
        updated = content.replace(old_version, new_version)

    if updated == content:
        raise RuntimeError(f"Failed to update version in {filepath}")
    filepath.write_text(updated)


def _update_version_py(filepath: Path, new_version: str) -> None:
    """Update __version__ in version.py."""
    content = filepath.read_text()
    updated = re.sub(
        r'(__version__\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        content,
        count=1,
    )
    if updated == content:
        raise RuntimeError(f"Failed to update __version__ in {filepath}")
    filepath.write_text(updated)


def _update_init_py(filepath: Path, new_version: str) -> None:
    """Update __version__ in __init__.py."""
    content = filepath.read_text()
    updated = re.sub(
        r'(__version__\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        content,
        count=1,
    )
    if updated == content:
        raise RuntimeError(f"Failed to update __version__ in {filepath}")
    filepath.write_text(updated)


def generate_changelog(from_tag: str, to_tag: str) -> str:
    """Generate a changelog from git log between two tags.

    Args:
        from_tag: Starting tag (exclusive).
        to_tag: Ending tag or "HEAD" (inclusive).

    Returns:
        Formatted changelog string with categorized commits.
    """
    # Get commits between tags
    result = _run_command(
        [
            "git",
            "log",
            f"{from_tag}..{to_tag}",
            "--pretty=format:%s|%h|%an",
            "--no-merges",
        ]
    )

    if result.returncode != 0:
        return f"Error generating changelog: {result.stderr.strip()}"

    if not result.stdout.strip():
        return "No changes found."

    # Categorize commits by conventional commit prefixes
    categories: dict[str, list[str]] = {
        "Added": [],
        "Changed": [],
        "Fixed": [],
        "Removed": [],
        "Security": [],
        "Other": [],
    }

    _CATEGORY_MAP = {
        "feat": "Added",
        "add": "Added",
        "fix": "Fixed",
        "bugfix": "Fixed",
        "change": "Changed",
        "update": "Changed",
        "refactor": "Changed",
        "remove": "Removed",
        "delete": "Removed",
        "security": "Security",
        "sec": "Security",
    }

    for line in result.stdout.strip().split("\n"):
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        message = parts[0].strip()
        commit_hash = parts[1].strip()

        # Detect category from message prefix
        category = "Other"
        lower_msg = message.lower()
        for prefix, cat in _CATEGORY_MAP.items():
            if lower_msg.startswith(prefix + ":") or lower_msg.startswith(prefix + "("):
                category = cat
                break
        # Also check Issue # prefix pattern
        if lower_msg.startswith("issue #"):
            # Try to detect from the rest of the message
            remainder = re.sub(r"^issue\s*#\d+:\s*", "", message, flags=re.IGNORECASE)
            remainder_lower = remainder.lower()
            for prefix, cat in _CATEGORY_MAP.items():
                if remainder_lower.startswith(prefix) or prefix in remainder_lower:
                    category = cat
                    break

        categories[category].append(f"- {message} ({commit_hash})")

    # Build changelog text
    lines: list[str] = []
    for cat, entries in categories.items():
        if entries:
            lines.append(f"### {cat}")
            lines.extend(entries)
            lines.append("")

    return "\n".join(lines).strip()


def create_release_notes(version: str, changelog: str) -> str:
    """Create formatted release notes for a version.

    Args:
        version: The version being released (e.g., "2.1.0").
        changelog: The changelog content for this release.

    Returns:
        Formatted release notes string.
    """
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    notes = f"""# Release v{version}

**Release Date:** {today}

## What's Changed

{changelog}

## Installation

```bash
pip install file-organizer=={version}
```

## Full Changelog

See [CHANGELOG.md](CHANGELOG.md) for the complete history of changes.
"""
    return notes.strip()


def validate_release() -> list[str]:
    """Validate that the repository is ready for a release.

    Performs the following checks:
    - No uncommitted changes
    - On a release branch or main
    - Tests pass
    - Version is consistent across files
    - CHANGELOG.md exists and has an Unreleased section

    Returns:
        A list of error messages. Empty list means validation passed.
    """
    errors: list[str] = []

    # Check for uncommitted changes
    result = _run_command(["git", "status", "--porcelain"])
    if result.returncode != 0:
        errors.append("Failed to check git status")
    elif result.stdout.strip():
        errors.append("Uncommitted changes found. Commit or stash before releasing.")

    # Check branch
    result = _run_command(["git", "branch", "--show-current"])
    if result.returncode == 0:
        branch = result.stdout.strip()
        valid_branches = ("main", "master")
        is_release_branch = branch.startswith("release/") or branch in valid_branches
        if not is_release_branch:
            errors.append(
                f"Not on a release branch (current: {branch}). "
                f"Expected 'main', 'master', or 'release/*'."
            )

    # Check version consistency
    try:
        pyproject_version = _read_current_version_from_pyproject()

        # Check version.py
        version_py_content = _VERSION_FILE.read_text()
        version_py_match = re.search(r'__version__\s*=\s*"([^"]+)"', version_py_content)
        if version_py_match:
            version_py_ver = version_py_match.group(1)
            if version_py_ver != pyproject_version:
                errors.append(
                    f"Version mismatch: pyproject.toml={pyproject_version}, "
                    f"version.py={version_py_ver}"
                )
        else:
            errors.append("Could not read version from version.py")

        # Check __init__.py
        init_content = _INIT_FILE.read_text()
        init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_content)
        if init_match:
            init_ver = init_match.group(1)
            if init_ver != pyproject_version:
                errors.append(
                    f"Version mismatch: pyproject.toml={pyproject_version}, __init__.py={init_ver}"
                )
        else:
            errors.append("Could not read version from __init__.py")
    except (RuntimeError, FileNotFoundError) as exc:
        errors.append(f"Version check failed: {exc}")

    # Check CHANGELOG.md exists
    if not _CHANGELOG.exists():
        errors.append("CHANGELOG.md not found at project root")

    # Run tests
    result = _run_command(
        [sys.executable, "-m", "pytest", "--tb=short", "-q", "tests/"],
        cwd=_V2_ROOT,
    )
    if result.returncode != 0:
        errors.append(f"Tests failed:\n{result.stdout}\n{result.stderr}")

    return errors


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Release automation for File Organizer")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # bump command
    bump_parser = subparsers.add_parser("bump", help="Bump version")
    bump_parser.add_argument("part", choices=["major", "minor", "patch"])

    # changelog command
    changelog_parser = subparsers.add_parser("changelog", help="Generate changelog")
    changelog_parser.add_argument("from_tag", help="Starting tag")
    changelog_parser.add_argument("to_tag", nargs="?", default="HEAD", help="Ending tag")

    # validate command
    subparsers.add_parser("validate", help="Validate release readiness")

    args = parser.parse_args()

    if args.command == "bump":
        new_ver = bump_version(args.part)
        print(f"Version bumped to {new_ver}")
    elif args.command == "changelog":
        log = generate_changelog(args.from_tag, args.to_tag)
        print(log)
    elif args.command == "validate":
        errs = validate_release()
        if errs:
            print("Release validation FAILED:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("Release validation passed.")
    else:
        parser.print_help()
