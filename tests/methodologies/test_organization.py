"""Tests for canonical organization methodology routing."""

from pathlib import Path

import pytest

from file_organizer.core.organize_options import OrganizationMethodology
from file_organizer.methodologies import apply_organization_methodology
from file_organizer.services.text_processor import ProcessedFile

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _processed(source: Path, folder: str = "Documents") -> ProcessedFile:
    return ProcessedFile(
        file_path=source,
        description=f"Categorized into {folder}",
        folder_name=folder,
        filename=source.stem,
    )


def test_none_preserves_classifier_destination(tmp_path: Path) -> None:
    result = _processed(tmp_path / "notes.txt")

    routed = apply_organization_methodology(
        [result], input_root=tmp_path, methodology=OrganizationMethodology.NONE
    )

    assert routed == [result]


@pytest.mark.parametrize(
    ("source", "folder", "expected"),
    [
        ("Projects/plan.txt", "Documents", "Projects/Documents"),
        ("notes.txt", "Documents", "Resources/Documents"),
        ("notes.txt", "Archive/Old", "Archive/Old"),
        ("notes.txt", "../escape", "Resources/Unsorted"),
    ],
)
def test_para_uses_canonical_categories(
    tmp_path: Path, source: str, folder: str, expected: str
) -> None:
    routed = apply_organization_methodology(
        [_processed(tmp_path / source, folder)],
        input_root=tmp_path,
        methodology=OrganizationMethodology.PARA,
    )

    assert routed[0].folder_name == expected


@pytest.mark.parametrize(
    ("source", "folder", "expected"),
    [
        ("Finance/budget.xlsx", "Spreadsheets", "10 Finance & Administration/10.01 Spreadsheets"),
        ("notes.txt", "Documents", "30 Operations & Projects/30.01 Documents"),
        ("notes.txt", "11.04 Existing", "11.04 Existing"),
        ("notes.txt", "/escape", "30 Operations & Projects/30.01 Unsorted"),
    ],
)
def test_johnny_decimal_uses_default_scheme(
    tmp_path: Path, source: str, folder: str, expected: str
) -> None:
    routed = apply_organization_methodology(
        [_processed(tmp_path / source, folder)],
        input_root=tmp_path,
        methodology=OrganizationMethodology.JOHNNY_DECIMAL,
    )

    assert routed[0].folder_name == expected
