"""Guards proving one authoritative methodology vocabulary across every surface.

``OrganizationMethodology`` is the canonical value model. Adapters may present methodologies
differently, but none may define, accept, or advertise a value the domain does not recognize.

Most adapters derive their vocabulary from the enum, so drift is impossible by construction. Five
cannot, and are pinned here instead:

* the Pydantic ``Literal`` annotations in the REST and Python SDK models, and the TypeScript union —
  deriving these would change the emitted OpenAPI schema and the generated client surface for no
  behavioral gain;
* the TUI view's ``BINDINGS`` and ``action_set_*`` handlers — Textual resolves both at
  class-definition time and dispatches actions by name, so neither can be generated.

The capability registry is deliberately not cross-checked here. ``methodology.configure`` declares
entry-point strings such as ``fo organize --methodology``; it does not encode methodology values, so
there is no registry-side vocabulary that could drift against the enum.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from file_organizer.api.models import OrganizationOptionsPayload as RestOptionsPayload
from file_organizer.client.models import OrganizationOptionsPayload as SdkOptionsPayload
from file_organizer.config import methodology as config_methodology
from file_organizer.core.organize_options import OrganizationMethodology, OrganizeOptions

pytestmark = [pytest.mark.ci, pytest.mark.unit]

_REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL: tuple[str, ...] = tuple(member.value for member in OrganizationMethodology)


def _literal_values(model: type, field: str) -> tuple[str, ...]:
    """Return the Literal members annotated on ``model.field``."""
    return get_args(model.model_fields[field].annotation)


def test_config_vocabulary_derives_from_the_canonical_enum() -> None:
    assert config_methodology.ORDER == CANONICAL
    assert config_methodology.DEFAULT == OrganizationMethodology.NONE.value
    assert (
        config_methodology.NONE,
        config_methodology.PARA,
        config_methodology.JOHNNY_DECIMAL,
    ) == CANONICAL


def test_every_label_covers_exactly_the_canonical_vocabulary() -> None:
    assert tuple(config_methodology.LABELS) == CANONICAL


def test_every_alias_resolves_to_a_canonical_methodology() -> None:
    assert config_methodology.ALIASES, "alias table must not be silently emptied"
    for alias, target in config_methodology.ALIASES.items():
        resolved = config_methodology.resolve(alias)
        assert resolved is not None, f"alias {alias!r} resolves to nothing"
        assert resolved.value == target
        assert target in CANONICAL, f"alias {alias!r} targets unregistered value {target!r}"


def test_aliases_never_shadow_a_canonical_value() -> None:
    # An alias colliding with a canonical value would make normalization order significant.
    assert not set(config_methodology.ALIASES) & set(CANONICAL)


@pytest.mark.parametrize("value", CANONICAL)
def test_canonical_values_survive_the_config_boundary(value: str) -> None:
    assert config_methodology.normalize(value) == value
    assert OrganizeOptions(methodology=value).effective_methodology.value == value


def test_unrecognized_values_are_lenient_at_the_boundary_and_strict_in_the_domain() -> None:
    # Config and presentation surfaces must not crash on a stale persisted value.
    assert config_methodology.normalize("date_based") == config_methodology.DEFAULT
    assert config_methodology.resolve("date_based") is None

    # The domain rejects it with the documented, vocabulary-derived message.
    with pytest.raises(ValueError, match="methodology must be"):
        OrganizeOptions(methodology="date_based")


def test_domain_error_lists_exactly_the_canonical_vocabulary() -> None:
    # Asserted through the public failure path rather than the private renderer, so the guard
    # pins the message a caller actually sees.
    with pytest.raises(ValueError) as exc_info:
        OrganizeOptions(methodology="date_based")

    assert re.findall(r"'([^']+)'", str(exc_info.value)) == list(CANONICAL)


def test_aliases_are_rejected_by_the_domain() -> None:
    # Aliases are a boundary concession. One reaching OrganizeOptions means an adapter skipped
    # normalization, which must fail loudly rather than be quietly understood.
    for alias in config_methodology.ALIASES:
        with pytest.raises(ValueError, match="methodology must be"):
            OrganizeOptions(methodology=alias)


def test_rest_api_model_vocabulary_matches_the_canonical_enum() -> None:
    assert _literal_values(RestOptionsPayload, "methodology") == CANONICAL


def test_python_sdk_model_vocabulary_matches_the_canonical_enum() -> None:
    assert _literal_values(SdkOptionsPayload, "methodology") == CANONICAL


def test_typescript_sdk_vocabulary_matches_the_canonical_enum() -> None:
    types_ts = _REPO_ROOT / "src" / "file_organizer" / "client" / "typescript" / "types.ts"
    source = types_ts.read_text(encoding="utf-8")
    match = re.search(r"^\s*methodology\??:\s*(.+?);", source, re.MULTILINE)
    assert match, "types.ts no longer declares a methodology field"
    declared = tuple(re.findall(r'"([^"]+)"', match.group(1)))
    assert declared == CANONICAL


def test_cli_config_validator_offers_exactly_the_canonical_vocabulary() -> None:
    from typer.testing import CliRunner

    from file_organizer.cli.config_cli import config_app

    result = CliRunner().invoke(config_app, ["edit", "--methodology", "date_based"])

    assert result.exit_code == 1
    # The rejection lists the accepted vocabulary; it must be the canonical set and nothing else.
    offered = re.search(r"[Vv]alid values:\s*([^\n.]+)", result.output)
    assert offered, f"validator did not list valid values: {result.output!r}"
    listed = tuple(token.strip().strip("'\"") for token in offered.group(1).split(","))
    assert sorted(listed) == sorted(CANONICAL)


def test_tui_methodology_panel_vocabulary_matches_the_canonical_enum() -> None:
    from file_organizer.tui.methodology_view import MethodologySelectorPanel

    assert tuple(MethodologySelectorPanel._METHODS) == CANONICAL
    assert tuple(MethodologySelectorPanel._SHORTCUTS) == CANONICAL
    assert MethodologySelectorPanel._current in CANONICAL


def test_tui_methodology_view_binds_every_canonical_methodology() -> None:
    """Textual cannot generate BINDINGS or action methods from the enum, so pin them here.

    Both are resolved at class-definition time and dispatched by name, which is why the view
    restates the vocabulary. Adding a methodology without a Binding and a matching action would
    otherwise ship a selector the user cannot reach.
    """
    from file_organizer.tui.methodology_view import MethodologySelectorPanel, MethodologyView

    bound_actions = {binding.action for binding in MethodologyView.BINDINGS}
    for value in CANONICAL:
        assert f"set_{value}" in bound_actions, f"no key binding selects methodology {value!r}"
        assert callable(getattr(MethodologyView, f"action_set_{value}", None)), (
            f"no action_set_{value} handler for methodology {value!r}"
        )

    # Every bound shortcut key must match the key the selector panel advertises for that value.
    bindings_by_action = {binding.action: binding.key for binding in MethodologyView.BINDINGS}
    for value, shortcut in MethodologySelectorPanel._SHORTCUTS.items():
        assert bindings_by_action[f"set_{value}"] == shortcut
