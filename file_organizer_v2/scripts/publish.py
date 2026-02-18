"""Publishing helpers for File Organizer.

Provides utilities for building, validating, and publishing
the package to PyPI or Test PyPI.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Project root is two levels above file_organizer_v2/scripts/
_SCRIPTS_DIR = Path(__file__).resolve().parent
_V2_ROOT = _SCRIPTS_DIR.parent


@dataclass(frozen=True)
class PublishConfig:
    """Configuration for package publishing."""

    pypi_url: str = "https://upload.pypi.org/legacy/"
    test_pypi_url: str = "https://test.pypi.org/legacy/"
    token_env_var: str = "PYPI_API_TOKEN"
    test_token_env_var: str = "TEST_PYPI_API_TOKEN"
    dist_dir: str = "dist"


def _run_command(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or _V2_ROOT,
        check=check,
    )


def build_package(clean: bool = True) -> Path:
    """Build the package distribution files.

    Args:
        clean: If True, remove existing dist/ before building.

    Returns:
        Path to the dist/ directory containing built packages.

    Raises:
        RuntimeError: If the build command fails.
    """
    dist_path = _V2_ROOT / "dist"

    if clean and dist_path.exists():
        import shutil

        shutil.rmtree(dist_path)

    result = _run_command(
        [sys.executable, "-m", "build"],
        cwd=_V2_ROOT,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Package build failed:\n{result.stdout}\n{result.stderr}")

    if not dist_path.exists() or not list(dist_path.iterdir()):
        raise RuntimeError("Build completed but no dist/ files were created")

    return dist_path


def check_package(dist_path: Path) -> bool:
    """Validate package distribution files with twine check.

    Args:
        dist_path: Path to the dist/ directory.

    Returns:
        True if all checks pass, False otherwise.

    Raises:
        FileNotFoundError: If dist_path does not exist.
    """
    if not dist_path.exists():
        raise FileNotFoundError(f"Distribution directory not found: {dist_path}")

    dist_files = list(dist_path.glob("*"))
    if not dist_files:
        raise FileNotFoundError(f"No distribution files found in {dist_path}")

    result = _run_command(
        [sys.executable, "-m", "twine", "check", "--strict", str(dist_path / "*")],
    )

    return result.returncode == 0


def publish_pypi(
    dist_path: Path,
    test: bool = True,
    config: PublishConfig | None = None,
) -> bool:
    """Publish package to PyPI or Test PyPI.

    Args:
        dist_path: Path to the dist/ directory.
        test: If True, publish to Test PyPI. If False, publish to production PyPI.
        config: Publishing configuration. Uses defaults if not provided.

    Returns:
        True if publishing succeeded, False otherwise.

    Raises:
        FileNotFoundError: If dist_path does not exist.
    """
    if config is None:
        config = PublishConfig()

    if not dist_path.exists():
        raise FileNotFoundError(f"Distribution directory not found: {dist_path}")

    repository_url = config.test_pypi_url if test else config.pypi_url
    token_env = config.test_token_env_var if test else config.token_env_var

    cmd = [
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--repository-url",
        repository_url,
        "--username",
        "__token__",
        "--password",
        f"${{{token_env}}}",
        str(dist_path / "*"),
    ]

    result = _run_command(cmd)
    return result.returncode == 0


def get_dist_files(dist_path: Path) -> list[Path]:
    """List all distribution files in the dist directory.

    Args:
        dist_path: Path to the dist/ directory.

    Returns:
        List of paths to distribution files (.tar.gz and .whl).
    """
    if not dist_path.exists():
        return []

    return sorted(
        p for p in dist_path.iterdir() if p.suffix in (".gz", ".whl") or p.name.endswith(".tar.gz")
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Publish File Organizer package")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # build command
    build_parser = subparsers.add_parser("build", help="Build package")
    build_parser.add_argument("--no-clean", action="store_true", help="Skip cleaning dist/")

    # check command
    check_parser = subparsers.add_parser("check", help="Check package with twine")
    check_parser.add_argument("--dist", default="dist", help="Path to dist directory")

    # publish command
    pub_parser = subparsers.add_parser("publish", help="Publish to PyPI")
    pub_parser.add_argument("--production", action="store_true", help="Publish to production PyPI")
    pub_parser.add_argument("--dist", default="dist", help="Path to dist directory")

    args = parser.parse_args()

    if args.command == "build":
        dist = build_package(clean=not args.no_clean)
        files = get_dist_files(dist)
        print(f"Built {len(files)} distribution files in {dist}")
        for f in files:
            print(f"  {f.name}")
    elif args.command == "check":
        dist = Path(args.dist)
        ok = check_package(dist)
        print("Package check PASSED" if ok else "Package check FAILED")
        sys.exit(0 if ok else 1)
    elif args.command == "publish":
        dist = Path(args.dist)
        ok = publish_pypi(dist, test=not args.production)
        target = "production PyPI" if args.production else "Test PyPI"
        print(f"Published to {target}" if ok else f"Publishing to {target} FAILED")
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
