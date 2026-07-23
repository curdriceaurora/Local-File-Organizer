"""Configuration and presentation vocabulary for organization methodologies.

The canonical value model is :class:`~file_organizer.core.organize_options.OrganizationMethodology`.
Every constant here derives from that enum, so this module cannot introduce a methodology the
domain does not recognize. It adds two things the domain deliberately does not carry:

* display labels, which are a presentation concern;
* legacy aliases, which are accepted only at configuration and transport boundaries.

Aliases are resolved on the way in and never written back out. The domain contract stays strict:
``OrganizeOptions`` accepts canonical values only, so an alias reaching it means an adapter failed
to normalize rather than a value the domain should quietly understand.

Historically the web layer defined its own partially incompatible vocabulary (``content_based`` /
``date_based`` instead of ``none``), with no implementation ever backing ``date_based`` — see #1538.
``date_based`` is therefore deliberately absent from the alias table: there is no canonical value to
map it to.
"""

from __future__ import annotations

from file_organizer.core.organize_options import OrganizationMethodology

NONE = OrganizationMethodology.NONE.value
PARA = OrganizationMethodology.PARA.value
JOHNNY_DECIMAL = OrganizationMethodology.JOHNNY_DECIMAL.value

DEFAULT = OrganizationMethodology.NONE.value

ORDER: tuple[str, ...] = tuple(member.value for member in OrganizationMethodology)

LABELS: dict[str, str] = {
    NONE: "None (flat / content-based)",
    PARA: "PARA",
    JOHNNY_DECIMAL: "Johnny Decimal",
}

ALIASES: dict[str, str] = {
    "content_based": NONE,
    "johnny_decimal": JOHNNY_DECIMAL,
}


def resolve(value: object) -> OrganizationMethodology | None:
    """Return the canonical methodology for ``value``, or ``None`` if unrecognized.

    Args:
        value: Candidate methodology from any surface (form field, API request,
            persisted config or settings file).

    Returns:
        The matching :class:`OrganizationMethodology`, or ``None`` when ``value`` is
        neither a canonical value nor a known legacy alias.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    try:
        return OrganizationMethodology(candidate)
    except ValueError:
        aliased = ALIASES.get(candidate)
        return OrganizationMethodology(aliased) if aliased is not None else None


def normalize(value: object, *, default: str = DEFAULT) -> str:
    """Return a canonical methodology value, mapping known legacy aliases.

    Deliberately lenient: an unrecognized value yields *default* rather than raising, because
    callers read persisted configuration and user-supplied form fields where a stale value must not
    crash the surface. Paths that require strictness construct an
    :class:`~file_organizer.core.organize_options.OrganizeOptions`, which rejects anything
    non-canonical.

    Args:
        value: Candidate methodology value from any surface (form field,
            API request, persisted config/settings).
        default: Value to return when *value* is unrecognized.

    Returns:
        One of :data:`ORDER`, or *default* if *value* is not a canonical
        value or a known legacy alias.
    """
    resolved = resolve(value)
    return resolved.value if resolved is not None else default
