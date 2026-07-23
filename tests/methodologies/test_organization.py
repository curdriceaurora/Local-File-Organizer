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


def _route_jd(tmp_path: Path, batch: list[ProcessedFile]) -> dict[str, str]:
    """Route a batch through Johnny Decimal and index destinations by filename."""
    routed = apply_organization_methodology(
        batch, input_root=tmp_path, methodology=OrganizationMethodology.JOHNNY_DECIMAL
    )
    return {result.filename: result.folder_name for result in routed}


def test_johnny_decimal_gives_distinct_classifiers_distinct_categories(tmp_path: Path) -> None:
    """Two classifiers in one area cannot share a category number (#1617)."""
    destinations = _route_jd(
        tmp_path,
        [
            _processed(tmp_path / "notes.txt", "Documents"),
            _processed(tmp_path / "paper.pdf", "PDFs"),
        ],
    )

    assert destinations["notes"] == "30 Operations & Projects/30.01 Documents"
    assert destinations["paper"] == "30 Operations & Projects/30.02 PDFs"


def test_johnny_decimal_numbers_each_area_independently(tmp_path: Path) -> None:
    """Category numbering restarts per area rather than running across the whole batch."""
    destinations = _route_jd(
        tmp_path,
        [
            _processed(tmp_path / "Finance/budget.xlsx", "Spreadsheets"),
            _processed(tmp_path / "notes.txt", "Documents"),
            _processed(tmp_path / "paper.pdf", "PDFs"),
        ],
    )

    assert destinations["budget"] == "10 Finance & Administration/10.01 Spreadsheets"
    assert destinations["notes"] == "30 Operations & Projects/30.01 Documents"
    assert destinations["paper"] == "30 Operations & Projects/30.02 PDFs"


def test_johnny_decimal_numbering_is_independent_of_traversal_order(tmp_path: Path) -> None:
    """The same corpus produces the same numbering however it was traversed."""
    batch = [
        _processed(tmp_path / "paper.pdf", "PDFs"),
        _processed(tmp_path / "notes.txt", "Documents"),
        _processed(tmp_path / "sheet.csv", "Tables"),
    ]

    assert _route_jd(tmp_path, batch) == _route_jd(tmp_path, list(reversed(batch)))


def test_johnny_decimal_numbering_follows_sorted_classifier_order(tmp_path: Path) -> None:
    """Categories are assigned in sorted classifier order, not set iteration order.

    Classifiers are collected in a set, and set iteration order for strings depends on
    ``PYTHONHASHSEED``. Numbering that relied on it would be stable within one process and differ
    between runs, so comparing two in-process orderings cannot detect the bug. Pinning the expected
    numbers can.
    """
    names = ("Zeta", "Omega", "Kappa", "Delta", "Alpha", "Mu")
    destinations = _route_jd(
        tmp_path, [_processed(tmp_path / f"{name}.txt", name) for name in names]
    )

    numbered = {
        name: destinations[name].rsplit("/", maxsplit=1)[-1].split(" ", maxsplit=1)[0]
        for name in names
    }
    assert [numbered[name] for name in sorted(names)] == [
        "30.01",
        "30.02",
        "30.03",
        "30.04",
        "30.05",
        "30.06",
    ]


def test_johnny_decimal_repeated_classifier_reuses_one_category(tmp_path: Path) -> None:
    """Files sharing a classifier land in the same category rather than consuming two."""
    destinations = _route_jd(
        tmp_path,
        [
            _processed(tmp_path / "notes.txt", "Documents"),
            _processed(tmp_path / "plan.txt", "Documents"),
            _processed(tmp_path / "paper.pdf", "PDFs"),
        ],
    )

    assert destinations["notes"] == destinations["plan"]
    assert destinations["paper"] == "30 Operations & Projects/30.02 PDFs"


def test_johnny_decimal_collapses_the_tail_when_an_area_overflows(tmp_path: Path) -> None:
    """An area with more classifiers than categories collapses the tail into a catch-all.

    Organizing files should not fail because a pathological input produced a hundred classifier
    folders in one area, so the excess shares the final category and keeps its classifier as a
    plain folder beneath it.
    """
    batch = [_processed(tmp_path / f"f{index}.pdf", f"Invoice{index:03d}") for index in range(120)]

    destinations = _route_jd(tmp_path, batch)
    categories = {value.split("/")[1].split(" ")[0] for value in destinations.values()}

    assert len(categories) == 99
    assert min(categories) == "10.01"
    assert max(categories) == "10.99"

    overflowed = [value for value in destinations.values() if "/10.99 Other/" in value]
    assert len(overflowed) == 120 - 98
    assert "10 Finance & Administration/10.99 Other/Invoice119" in overflowed


def test_johnny_decimal_preserves_already_numbered_destinations(tmp_path: Path) -> None:
    """Valid Johnny Decimal prefixes survive untouched and consume no category number."""
    destinations = _route_jd(
        tmp_path,
        [
            _processed(tmp_path / "kept.txt", "11.04 Existing"),
            _processed(tmp_path / "notes.txt", "Documents"),
        ],
    )

    assert destinations["kept"] == "11.04 Existing"
    assert destinations["notes"] == "30 Operations & Projects/30.01 Documents"
