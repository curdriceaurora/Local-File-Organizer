#!/usr/bin/env python3
"""Cross-platform build script for creating standalone executables.

Uses PyInstaller to bundle the File Organizer application into a single
executable for the current platform.  Ollama is **not** bundled — users
install it separately.

Usage::

    python scripts/build.py              # Build for current platform
    python scripts/build.py --help       # Show options
    python scripts/build.py --one-dir    # Build as directory (faster debug)
    python scripts/build.py --clean      # Clean before building
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import build_config.
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from build_config import (  # noqa: E402
    DATA_FILES,
    DESKTOP_DATA_FILES,
    BuildConfig,
    DesktopBuildConfig,
    current_platform,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Build File Organizer as a standalone executable.",
    )
    parser.add_argument(
        "--one-dir",
        action="store_true",
        help="Build as a directory instead of a single file (faster, larger).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build and dist directories before building.",
    )
    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Do not strip debug symbols.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build with debug logging enabled.",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help="Generate the spec file without building.",
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Build the pywebview desktop app instead of the CLI.",
    )
    return parser.parse_args()


def check_pyinstaller() -> bool:
    """Verify that PyInstaller is installed.

    Returns:
        True if available.
    """
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def clean_build(config: BuildConfig) -> None:
    """Remove previous build artifacts.

    Args:
        config: Build configuration.
    """
    for d in (config.build_dir, config.dist_dir):
        target = _PROJECT_ROOT / d
        if target.exists():
            print(f"Cleaning {target}")
            shutil.rmtree(target)


def _entry_point(config: BuildConfig) -> Path:
    """Return the source entry point for the given build config.

    Args:
        config: Build configuration.

    Returns:
        Path to the Python entry-point module.
    """
    if isinstance(config, DesktopBuildConfig):
        return _PROJECT_ROOT / "src" / "file_organizer" / "desktop" / "app.py"
    return _PROJECT_ROOT / "src" / "file_organizer" / "cli" / "main.py"


def _spec_path(config: BuildConfig) -> Path:
    """Return the spec file path for the given build config.

    Args:
        config: Build configuration.

    Returns:
        Path to the PyInstaller spec file.
    """
    if isinstance(config, DesktopBuildConfig):
        return _PROJECT_ROOT / "file_organizer_desktop.spec"
    return _PROJECT_ROOT / "file_organizer.spec"


def build_command(config: BuildConfig, *, one_dir: bool = False, debug: bool = False) -> list[str]:
    """Construct the PyInstaller command line.

    Args:
        config: Build configuration.
        one_dir: If True build as directory instead of one-file.
        debug: If True enable debug logging.

    Returns:
        Command as a list of strings.
    """
    spec_file = _spec_path(config)
    if spec_file.exists():
        # Use the spec file if present
        return [sys.executable, "-m", "PyInstaller", str(spec_file)]

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        config.output_name,
        "--console" if config.console else "--windowed",
    ]

    if not one_dir:
        cmd.append("--onefile")

    if config.strip and current_platform() != "windows":
        cmd.append("--strip")

    for imp in config.hidden_imports:
        cmd.extend(["--hidden-import", imp])

    for exc in config.excludes:
        cmd.extend(["--exclude-module", exc])

    if debug:
        cmd.extend(["--log-level", "DEBUG"])

    cmd.append(str(_entry_point(config)))

    return cmd


def generate_spec(config: BuildConfig) -> Path:
    """Generate a PyInstaller spec file.

    Args:
        config: Build configuration.

    Returns:
        Path to the generated spec file.
    """
    spec_file = _spec_path(config)
    entry = _entry_point(config)

    data_files = DESKTOP_DATA_FILES if isinstance(config, DesktopBuildConfig) else DATA_FILES
    datas_lines = "\n        ".join(f"('{src}', '{dst}')," for src, dst in data_files)

    hidden = ",\n    ".join(f"'{h}'" for h in config.hidden_imports)
    excludes = ",\n    ".join(f"'{e}'" for e in config.excludes)

    # Use posix-style path so spec file works on all platforms including Windows.
    entry_rel = entry.relative_to(_PROJECT_ROOT).as_posix()

    spec_content = f"""\
# -*- mode: python ; coding: utf-8 -*-
# Auto-generated by scripts/build.py — edit build_config.py to change settings.

import sys
import platform

block_cipher = None

a = Analysis(
    ['{entry_rel}'],
    pathex=['src'],
    binaries=[],
    datas=[
        {datas_lines}
    ],
    hiddenimports=[
        {hidden}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        {excludes}
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{config.output_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip={config.strip},
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={config.console},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
"""
    try:
        spec_file.write_text(spec_content)
    except OSError as e:
        print(f"ERROR: Failed to write spec file {spec_file}: {e}")
        sys.exit(1)
    print(f"Generated spec file: {spec_file}")
    return spec_file


def run_build(config: BuildConfig, *, one_dir: bool = False, debug: bool = False) -> int:
    """Execute the PyInstaller build.

    Args:
        config: Build configuration.
        one_dir: Build as directory.
        debug: Enable debug logging.

    Returns:
        Exit code (0 on success).
    """
    cmd = build_command(config, one_dir=one_dir, debug=debug)
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(_PROJECT_ROOT))
    return result.returncode


def main() -> None:
    """Entry point for the build script."""
    args = parse_args()
    config: BuildConfig = (
        DesktopBuildConfig(strip=not args.no_strip)
        if args.desktop
        else BuildConfig(strip=not args.no_strip)
    )

    print(f"Build target: {config.output_name}")
    print(f"Platform: {config.platform} ({config.arch})")

    if args.clean:
        clean_build(config)

    if args.spec_only:
        generate_spec(config)
        return

    if not check_pyinstaller():
        print(
            "ERROR: PyInstaller is not installed.\n"
            "Install it with:  pip install pyinstaller\n"
            "Or:  pip install -e '.[build]'"
        )
        sys.exit(1)

    # Generate spec file if it doesn't exist
    if not _spec_path(config).exists():
        generate_spec(config)

    exit_code = run_build(config, one_dir=args.one_dir, debug=args.debug)
    if exit_code == 0:
        print(f"\nBuild successful! Output: {config.dist_dir / config.output_name}")
    else:
        print(f"\nBuild failed with exit code {exit_code}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
