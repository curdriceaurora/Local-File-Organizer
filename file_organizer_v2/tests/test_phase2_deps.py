"""Smoke tests for Phase 2 Enhanced UX dependencies.

Verifies that all required Phase 2 dependencies are importable
and meet minimum version requirements.
"""

import sys

# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _pkg_version(package_name: str) -> str:
    """Get installed version of a package via importlib.metadata."""
    from importlib.metadata import version as pkg_version
    return pkg_version(package_name)


def _version_gte(installed: str, minimum: str) -> bool:
    """Return True if *installed* >= *minimum* (PEP 440 comparison)."""
    from packaging.version import Version
    return Version(installed) >= Version(minimum)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestPhase2Imports:
    """Verify Phase 2 dependencies are importable."""

    def test_import_typer(self) -> None:
        import typer  # noqa: F401

    def test_import_textual(self) -> None:
        import textual  # noqa: F401

    def test_import_yaml(self) -> None:
        import yaml  # noqa: F401

    def test_import_rich(self) -> None:
        import rich  # noqa: F401


# ---------------------------------------------------------------------------
# Version checks
# ---------------------------------------------------------------------------

class TestPhase2Versions:
    """Verify Phase 2 dependencies meet minimum version requirements."""

    def test_typer_version(self) -> None:
        ver = _pkg_version("typer")
        assert _version_gte(ver, "0.12.0"), f"typer {ver} < 0.12.0"

    def test_textual_version(self) -> None:
        ver = _pkg_version("textual")
        assert _version_gte(ver, "0.50.0"), f"textual {ver} < 0.50.0"

    def test_pyyaml_version(self) -> None:
        ver = _pkg_version("pyyaml")
        assert _version_gte(ver, "6.0.0"), f"pyyaml {ver} < 6.0.0"

    def test_rich_version(self) -> None:
        ver = _pkg_version("rich")
        assert _version_gte(ver, "13.0.0"), f"rich {ver} < 13.0.0"


# ---------------------------------------------------------------------------
# Basic functionality smoke tests
# ---------------------------------------------------------------------------

class TestPhase2Functionality:
    """Light functionality checks for Phase 2 dependencies."""

    def test_typer_create_app(self) -> None:
        """Typer can create an application instance."""
        import typer

        app = typer.Typer()
        assert app is not None

    def test_textual_create_app(self) -> None:
        """Textual App class is available."""
        from textual.app import App

        assert issubclass(App, App)

    def test_yaml_roundtrip(self) -> None:
        """PyYAML can dump and load a mapping."""
        import yaml

        data = {"phase": 2, "name": "Enhanced UX", "enabled": True}
        dumped = yaml.dump(data, default_flow_style=False)
        loaded = yaml.safe_load(dumped)
        assert loaded == data

    def test_rich_console(self) -> None:
        """Rich Console can be instantiated."""
        from rich.console import Console

        console = Console(file=sys.stderr)
        assert console is not None

    def test_python_version(self) -> None:
        """Python version is 3.9+."""
        assert sys.version_info >= (3, 9), (
            f"Python {sys.version_info.major}.{sys.version_info.minor} < 3.9"
        )
