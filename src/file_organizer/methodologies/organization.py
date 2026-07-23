"""Canonical destination adapters for organization methodologies.

The standalone PARA and Johnny Decimal packages contain the vocabulary and
folder/numbering primitives. This module is the single bridge from processed
organization results into those packages; presentation layers must select a
methodology through :class:`OrganizeOptions` instead of remapping plans.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from file_organizer.core.organize_options import OrganizationMethodology
from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    JohnnyDecimalNumber,
    get_default_scheme,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator
from file_organizer.services import ProcessedFile, ProcessedImage

ProcessedResult = ProcessedFile | ProcessedImage

_PARA_SOURCE_NAMES: dict[str, PARACategory] = {
    "project": PARACategory.PROJECT,
    "projects": PARACategory.PROJECT,
    "area": PARACategory.AREA,
    "areas": PARACategory.AREA,
    "resource": PARACategory.RESOURCE,
    "resources": PARACategory.RESOURCE,
    "archive": PARACategory.ARCHIVE,
    "archives": PARACategory.ARCHIVE,
}

# Johnny Decimal reserves categories 00-99 within an area. Allocation starts at 01 so a single
# classifier keeps the number it has always been given, and 99 is held back as the catch-all only
# when an area genuinely overflows.
_JD_FIRST_CATEGORY = 1
_JD_LAST_CATEGORY = 99
_JD_CATCH_ALL_NAME = "Other"


def apply_organization_methodology(
    processed: Iterable[ProcessedResult],
    *,
    input_root: Path,
    methodology: OrganizationMethodology,
) -> list[ProcessedResult]:
    """Return processed results routed through the selected methodology."""
    results = list(processed)
    if methodology == OrganizationMethodology.NONE:
        return results

    allocation = (
        _allocate_johnny_decimal_categories(results, input_root)
        if methodology == OrganizationMethodology.JOHNNY_DECIMAL
        else {}
    )

    remapped: list[ProcessedResult] = []
    for result in results:
        if methodology == OrganizationMethodology.PARA:
            folder = _para_destination(result, input_root)
        else:
            folder = _johnny_decimal_destination(result, input_root, allocation)
        remapped.append(replace(result, folder_name=folder))
    return remapped


def _allocate_johnny_decimal_categories(
    results: list[ProcessedResult],
    input_root: Path,
) -> dict[tuple[int, str], tuple[int, bool]]:
    """Assign a distinct category number to each classifier folder within an area.

    Johnny Decimal requires distinct categories inside an area, so ``10.01 Taxes`` and
    ``10.01 Receipts`` are not a valid pair even though the paths do not collide.

    Classifiers are sorted before numbering, which makes the result depend only on the set of
    classifiers an area receives and not on the order files were traversed. The same corpus and
    options therefore always produce the same numbering.

    An area holding more distinct classifiers than it has category numbers collapses the tail into
    a single catch-all category rather than failing the plan: this organizes files, and an area with
    a hundred classifier folders is a pathological input, not a reason to refuse the run.

    Returns:
        A map from ``(area, classifier)`` to its category number and whether that number is the
        shared catch-all.
    """
    classifiers_by_area: dict[int, set[str]] = {}
    for result in results:
        routed = _johnny_decimal_classifier(result, input_root)
        if routed is None:
            continue
        area, classifier = routed
        classifiers_by_area.setdefault(area.area_range_start, set()).add(classifier)

    capacity = _JD_LAST_CATEGORY - _JD_FIRST_CATEGORY + 1
    allocation: dict[tuple[int, str], tuple[int, bool]] = {}
    for area_start, classifiers in classifiers_by_area.items():
        ordered = sorted(classifiers, key=lambda name: (name.casefold(), name))
        if len(ordered) <= capacity:
            for offset, classifier in enumerate(ordered):
                allocation[(area_start, classifier)] = (_JD_FIRST_CATEGORY + offset, False)
            continue
        # Reserve the final category as the catch-all and number everything before it uniquely.
        for offset, classifier in enumerate(ordered[: capacity - 1]):
            allocation[(area_start, classifier)] = (_JD_FIRST_CATEGORY + offset, False)
        for classifier in ordered[capacity - 1 :]:
            allocation[(area_start, classifier)] = (_JD_LAST_CATEGORY, True)
    return allocation


def _johnny_decimal_classifier(
    result: ProcessedResult,
    input_root: Path,
) -> tuple[AreaDefinition, str] | None:
    """Return the area and classifier folder for a result, or ``None`` if already numbered."""
    existing = _safe_folder(result.folder_name)
    existing_parts = Path(existing).parts
    first_part = existing_parts[0] if existing_parts else ""
    if _has_johnny_decimal_prefix(first_part):
        return None

    try:
        relative_source = result.file_path.relative_to(input_root).as_posix()
    except ValueError:
        relative_source = result.file_path.name
    searchable = f"{relative_source} {existing} {result.filename}".casefold()
    return _select_johnny_decimal_area(searchable), existing


def _para_destination(result: ProcessedResult, input_root: Path) -> str:
    """Map one result using canonical PARA category primitives."""
    existing = _safe_folder(result.folder_name)
    existing_parts = Path(existing).parts
    if existing_parts:
        existing_category = _PARA_SOURCE_NAMES.get(existing_parts[0].casefold())
        if existing_category is not None:
            canonical_root = _para_root(existing_category)
            return Path(canonical_root, *existing_parts[1:]).as_posix()

    category = _source_para_category(result.file_path, input_root)
    canonical_root = _para_root(category)
    return (Path(canonical_root) / existing).as_posix()


def _source_para_category(source: Path, input_root: Path) -> PARACategory:
    """Infer a PARA category from source ancestors, defaulting to Resources."""
    try:
        parent_parts = source.relative_to(input_root).parts[:-1]
    except ValueError:
        parent_parts = source.parts[:-1]
    for part in parent_parts:
        category = _PARA_SOURCE_NAMES.get(part.casefold())
        if category is not None:
            return category
    return PARACategory.RESOURCE


def _para_root(category: PARACategory) -> str:
    """Return the canonical root folder generated by the PARA package."""
    generator = PARAFolderGenerator()
    return generator.get_category_path(category, Path()).as_posix()


def _johnny_decimal_destination(
    result: ProcessedResult,
    input_root: Path,
    allocation: dict[tuple[int, str], tuple[int, bool]],
) -> str:
    """Map one result into the existing default Johnny Decimal scheme."""
    routed = _johnny_decimal_classifier(result, input_root)
    if routed is None:
        return _safe_folder(result.folder_name)

    area, classifier = routed
    category, is_catch_all = allocation.get(
        (area.area_range_start, classifier), (_JD_FIRST_CATEGORY, False)
    )
    number = JohnnyDecimalNumber(area=area.area_range_start, category=category)
    area_folder = f"{area.area_range_start:02d} {area.name}"
    if is_catch_all:
        # The catch-all is one category shared by many classifiers, so the classifier survives as a
        # plain folder beneath it. Numbering stays valid and the grouping is not thrown away.
        catch_all_folder = f"{number.formatted_number} {_JD_CATCH_ALL_NAME}"
        return (Path(area_folder) / catch_all_folder / classifier).as_posix()
    category_folder = f"{number.formatted_number} {classifier}"
    return (Path(area_folder) / category_folder).as_posix()


def _select_johnny_decimal_area(searchable: str) -> AreaDefinition:
    """Select the best matching area from the default Johnny Decimal scheme."""
    scheme = get_default_scheme()
    unique_areas = {definition.area_range_start: definition for definition in scheme.areas.values()}
    scored = [
        (
            sum(1 for keyword in definition.keywords if keyword.casefold() in searchable),
            -definition.area_range_start,
            definition,
        )
        for definition in unique_areas.values()
    ]
    matches, _, selected = max(scored, key=lambda item: (item[0], item[1]))
    if matches:
        return selected
    # Preserve the former dashboard's honest default for uncategorized input.
    fallback = scheme.get_area(30)
    if fallback is None:  # pragma: no cover - invariant of the default scheme
        raise RuntimeError("Default Johnny Decimal scheme has no operations area")
    return fallback


def _has_johnny_decimal_prefix(folder: str) -> bool:
    """Return whether a folder already starts with a Johnny Decimal number."""
    if len(folder) < 2 or not folder[:2].isdigit():
        return False
    return len(folder) == 2 or folder[2] in {" ", "."}


def _safe_folder(folder: str) -> str:
    """Return a safe relative classifier folder or the Unsorted fallback."""
    candidate = Path(folder)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        return "Unsorted"
    return candidate.as_posix()
