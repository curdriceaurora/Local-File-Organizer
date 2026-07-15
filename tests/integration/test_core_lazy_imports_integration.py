"""Integration coverage for lazy ``file_organizer.core`` package exports."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


def test_core_lazy_public_api_and_dir() -> None:
    import file_organizer.core as core

    names = dir(core)

    assert "FileOrganizer" in names
    assert "OrganizationResult" in names
    assert core.FileOrganizer.__name__ == "FileOrganizer"
    assert core.OrganizationResult.__name__ == "OrganizationResult"


def test_core_lazy_unknown_attribute_raises() -> None:
    import file_organizer.core as core

    with pytest.raises(AttributeError, match="DefinitelyNotAnExport"):
        _ = core.DefinitelyNotAnExport
