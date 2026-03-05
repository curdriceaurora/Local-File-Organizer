"""Coverage tests for file_organizer.cli.__init__ — uncovered lines 60-71."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestLazyImport:
    """Covers __getattr__ lazy import mechanism."""

    def test_lazy_import_known_attribute(self) -> None:
        """Accessing a known lazy attribute triggers import and caching."""
        import file_organizer.cli as cli_mod

        # Access a lazy attribute
        update_app = cli_mod.update_app
        assert update_app is not None
        # Second access should use the cached value
        assert cli_mod.update_app is update_app

    def test_lazy_import_unknown_attribute(self) -> None:
        """Accessing an unknown attribute raises AttributeError."""
        import file_organizer.cli as cli_mod

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = cli_mod.this_does_not_exist_xyz

    def test_lazy_import_copilot_app(self) -> None:
        """Importing copilot_app lazily."""
        import file_organizer.cli as cli_mod

        copilot = cli_mod.copilot_app
        assert copilot is not None

    def test_lazy_import_daemon_app(self) -> None:
        """Importing daemon_app lazily."""
        import file_organizer.cli as cli_mod

        daemon = cli_mod.daemon_app
        assert daemon is not None
