"""Build configuration for PyInstaller packaging.

Centralises version injection, bundled model list, platform detection,
and excluded modules used by the build script and spec file.
"""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

APP_NAME = "file-organizer"


def _read_pyproject_version() -> str:
    """Read the project version from pyproject.toml.

    Falls back to "0.0.0" if the file or version field is missing.
    """
    project_root = Path(__file__).resolve().parent.parent
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\\s*=\\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


APP_VERSION = _read_pyproject_version()
APP_DESCRIPTION = "AI-powered local file management"

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------


def current_platform() -> str:
    """Return a normalised platform string.

    Returns:
        One of ``'macos'``, ``'windows'``, ``'linux'``.
    """
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def current_arch() -> str:
    """Return the CPU architecture string.

    Returns:
        E.g. ``'x86_64'``, ``'arm64'``.
    """
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


# ---------------------------------------------------------------------------
# Build configuration
# ---------------------------------------------------------------------------

# Hidden imports that PyInstaller cannot detect automatically.
HIDDEN_IMPORTS: list[str] = [
    "ollama",
    "textual",
    "textual.app",
    "textual.widgets",
    "typer",
    "typer.main",
    "click",
    "rich",
    "rich.console",
    "rich.table",
    "rich.panel",
    "rich.progress",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "yaml",
    "pyyaml",
    "nltk",
    "PIL",
    "PIL.Image",
    "loguru",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "file_organizer",
    "file_organizer.cli",
    "file_organizer.cli.main",
    "file_organizer.tui",
    "file_organizer.tui.app",
    "file_organizer.models",
    "file_organizer.models.text_model",
    "file_organizer.models.vision_model",
    "file_organizer.services.copilot",
    "file_organizer.services.copilot.engine",
]

# Modules to exclude from the bundle to reduce size.
EXCLUDES: list[str] = [
    "tkinter",
    "matplotlib",
    "scipy",
    "numpy.testing",
    "IPython",
    "jupyter",
    "notebook",
    "test",
    "unittest",
    "PyQt6",
    "PyQt5",
]

# Data files to include: (source_glob, destination_directory)
DATA_FILES: list[tuple[str, str]] = [
    ("src/file_organizer/config/*.yaml", "file_organizer/config"),
]

# Additional hidden imports for the pywebview desktop build.
# Platform-specific webview backends are added by DesktopBuildConfig based on current_platform().
DESKTOP_HIDDEN_IMPORTS: list[str] = [
    "webview",
    "uvicorn",
    "uvicorn.config",
    "uvicorn.main",
    "uvicorn.lifespan.on",
    "uvicorn.protocols.http.auto",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "jinja2",
    "jinja2.ext",
    "file_organizer.api",
    "file_organizer.api.main",
    "file_organizer.api.routers",
    "file_organizer.desktop",
    "file_organizer.desktop.app",
]

# Platform-specific pywebview backend imports.
_WEBVIEW_PLATFORM_BACKENDS: dict[str, str] = {
    "macos": "webview.platforms.cocoa",
    "linux": "webview.platforms.gtk",
    "windows": "webview.platforms.edgechromium",
}

# Data files for the desktop build (adds web UI templates/static assets).
DESKTOP_DATA_FILES: list[tuple[str, str]] = [
    *DATA_FILES,
    ("src/file_organizer/web/templates", "file_organizer/web/templates"),
    ("src/file_organizer/web/static", "file_organizer/web/static"),
]


@dataclass
class BuildConfig:
    """Complete build configuration."""

    app_name: str = APP_NAME
    version: str = APP_VERSION
    platform: str = field(default_factory=current_platform)
    arch: str = field(default_factory=current_arch)
    hidden_imports: list[str] = field(default_factory=lambda: list(HIDDEN_IMPORTS))
    excludes: list[str] = field(default_factory=lambda: list(EXCLUDES))
    console: bool = True  # CLI app, not windowed
    one_file: bool = True  # Single executable
    strip: bool = True  # Strip debug symbols

    @property
    def output_name(self) -> str:
        """Filename for the built executable.

        Returns:
            E.g. ``'file-organizer-2.0.0-macos-arm64'``.
        """
        suffix = ".exe" if self.platform == "windows" else ""
        return f"{self.app_name}-{self.version}-{self.platform}-{self.arch}{suffix}"

    @property
    def dist_dir(self) -> Path:
        """Path to the distribution output directory."""
        return Path("dist")

    @property
    def build_dir(self) -> Path:
        """Path to the build work directory."""
        return Path("build")


def _desktop_hidden_imports() -> list[str]:
    """Return the combined hidden imports for the desktop build."""
    return list(HIDDEN_IMPORTS) + list(DESKTOP_HIDDEN_IMPORTS)


@dataclass
class DesktopBuildConfig(BuildConfig):
    """Build configuration for the pywebview desktop application.

    Overrides :attr:`BuildConfig.console` to ``False`` (windowed), sets the
    output name to include ``desktop``, and extends hidden imports with
    pywebview platform backends plus uvicorn/fastapi server imports.
    """

    console: bool = False  # Desktop app uses native window, no terminal
    hidden_imports: list[str] = field(default_factory=_desktop_hidden_imports)

    def __post_init__(self) -> None:
        """Extend hidden imports with pywebview platform backend for current platform."""
        backend = _WEBVIEW_PLATFORM_BACKENDS.get(self.platform)
        if backend and backend not in self.hidden_imports:
            self.hidden_imports = list(self.hidden_imports) + [backend]

    @property
    def output_name(self) -> str:
        """Filename for the desktop executable.

        Returns:
            E.g. ``'file-organizer-desktop-2.0.0-macos-arm64'``.
        """
        suffix = ".exe" if self.platform == "windows" else ""
        return f"file-organizer-desktop-{self.version}-{self.platform}-{self.arch}{suffix}"
