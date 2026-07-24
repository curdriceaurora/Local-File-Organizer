"""Canonical destination adapters for organization methodologies.

The standalone PARA and Johnny Decimal packages contain the vocabulary and
folder/numbering primitives. This module is the single bridge from processed
organization results into those packages; presentation layers must select a
methodology through :class:`OrganizeOptions` instead of remapping plans.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NamedTuple

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


class _JohnnyDecimalRoute(NamedTuple):
    """Where one result lands before its category number is known.

    A classifier folder may be nested, e.g. ``Invoices/2024``. Only the top-level segment earns a
    category number: numbering the whole path would give ``Invoices/2024`` and ``Invoices/2025``
    different numbers and split one logical classifier across sibling ``NN Invoices`` directories.
    """

    area: AreaDefinition
    classifier: str
    nested: tuple[str, ...] = ()


class _CategoryAssignment(NamedTuple):
    """One allocated category, and whether it is the shared catch-all."""

    category: int
    is_catch_all: bool


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

    if methodology == OrganizationMethodology.PARA:
        return [
            replace(result, folder_name=_para_destination(result, input_root)) for result in results
        ]

    # Route once and reuse. Area selection rebuilds the default scheme on every call, so resolving
    # it separately for allocation and for rendering would double the cost of Johnny Decimal
    # routing across the batch.
    routes = [_johnny_decimal_classifier(result, input_root) for result in results]
    allocation = _allocate_johnny_decimal_categories(routes)
    return [
        replace(result, folder_name=_johnny_decimal_destination(result, route, allocation))
        for result, route in zip(results, routes, strict=True)
    ]


def _allocate_johnny_decimal_categories(
    routes: list[_JohnnyDecimalRoute | None],
) -> dict[tuple[int, str], _CategoryAssignment]:
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
    for route in routes:
        if route is None:
            continue
        classifiers_by_area.setdefault(route.area.area_range_start, set()).add(route.classifier)

    capacity = _JD_LAST_CATEGORY - _JD_FIRST_CATEGORY + 1
    allocation: dict[tuple[int, str], _CategoryAssignment] = {}
    for area_start, classifiers in classifiers_by_area.items():
        ordered = sorted(classifiers, key=lambda name: (name.casefold(), name))
        if len(ordered) <= capacity:
            for offset, classifier in enumerate(ordered):
                allocation[(area_start, classifier)] = _CategoryAssignment(
                    _JD_FIRST_CATEGORY + offset, False
                )
            continue
        # Reserve the final category as the catch-all and number everything before it uniquely.
        for offset, classifier in enumerate(ordered[: capacity - 1]):
            allocation[(area_start, classifier)] = _CategoryAssignment(
                _JD_FIRST_CATEGORY + offset, False
            )
        for classifier in ordered[capacity - 1 :]:
            allocation[(area_start, classifier)] = _CategoryAssignment(_JD_LAST_CATEGORY, True)
    return allocation


def _johnny_decimal_classifier(
    result: ProcessedResult,
    input_root: Path,
) -> _JohnnyDecimalRoute | None:
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
    return _JohnnyDecimalRoute(
        _select_johnny_decimal_area(searchable), first_part, tuple(existing_parts[1:])
    )


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
    route: _JohnnyDecimalRoute | None,
    allocation: dict[tuple[int, str], _CategoryAssignment],
) -> str:
    """Map one result into the existing default Johnny Decimal scheme."""
    if route is None:
        return _safe_folder(result.folder_name)

    area, classifier = route.area, route.classifier
    # Every routed classifier was allocated above, so a missing key would be a logic error rather
    # than a case to paper over with a default.
    category, is_catch_all = allocation[(area.area_range_start, classifier)]
    number = JohnnyDecimalNumber(area=area.area_range_start, category=category)
    area_folder = f"{area.area_range_start:02d} {area.name}"
    if is_catch_all:
        # The catch-all is one category shared by many classifiers, so the classifier survives as a
        # plain folder beneath it. Numbering stays valid and the grouping is not thrown away.
        catch_all_folder = f"{number.formatted_number} {_JD_CATCH_ALL_NAME}"
        destination = Path(area_folder) / catch_all_folder / classifier
    else:
        destination = Path(area_folder) / f"{number.formatted_number} {classifier}"
    # Segments below the top-level classifier keep their shape beneath the numbered folder.
    return destination.joinpath(*route.nested).as_posix()


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
    """Return a safe relative classifier folder or the Unsorted fallback.

    ``folder`` is classifier-proposed, so this is the guard that keeps a
    destination inside the output root. It is evaluated under *both* path
    flavours rather than the host's ``Path``, which is platform-dependent
    and leaves a gap in either direction: ``WindowsPath("/escape")`` is not
    absolute (it has no drive), while ``PosixPath("C:/escape")`` is not
    absolute either. A plan may also be built on one platform and executed
    on another, so neither flavour alone is sufficient.
    """
    # ``anchor`` (drive + root) rather than ``is_absolute()``: it catches a
    # rooted-but-driveless Windows path such as "/escape", which is exactly
    # the case ``WindowsPath.is_absolute()`` reports as False.
    for flavour in (PurePosixPath, PureWindowsPath):
        candidate = flavour(folder)
        if candidate.anchor or ".." in candidate.parts:
            return "Unsorted"
    relative = PurePosixPath(folder)
    if not relative.parts:
        return "Unsorted"
    return relative.as_posix()
