"""Test that config edit errors include valid-values hints.

Step 3 replaced bare "must be one of [...]" messages with the new
`format_validation_error` helper, which adds a "did you mean" suggestion
when the input is a near-typo. Pins both:
- The valid-values list appears verbatim (so `_VALID_*` constant
  additions automatically flow into the message).
- A near-typo gets a `'did you mean ...'` suggestion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config from the real user config dir.

    Bypass the global setup gate too — this test is about validation
    error formatting, not the gate.
    """
    monkeypatch.setattr("file_organizer.config.manager.DEFAULT_CONFIG_DIR", tmp_path)
    monkeypatch.setattr("file_organizer.cli.organize._check_setup_completed", lambda: True)
    return tmp_path


@pytest.mark.integration
@pytest.mark.ci
def test_config_edit_invalid_device_includes_valid_values(
    isolated_config: Path,
) -> None:
    """A typo'd `--device cdua` produces a hint-rich error listing ALL valid devices.

    Rich wraps long error strings across newlines on narrow terminals;
    normalize whitespace + check word components individually so the
    assertions are wrap-immune. All five values from ``_VALID_DEVICES``
    must appear so a future removal would fail this test.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["config", "edit", "--device", "cdua"])
    assert result.exit_code != 0, result.output
    normalized = " ".join(result.output.lower().split())
    # Every value in _VALID_DEVICES must be present in the error message.
    for value in ("auto", "cpu", "cuda", "metal", "mps"):
        assert value in normalized, f"missing valid device '{value}' in error output"
    # And the close-match suggestion fires for the typo.
    assert "did" in normalized
    assert "you mean" in normalized
    assert "'cuda'" in normalized  # the suggested correction (quoted)


@pytest.mark.integration
@pytest.mark.ci
def test_config_edit_invalid_methodology_includes_valid_values(
    isolated_config: Path,
) -> None:
    """Methodology error lists ALL valid methodology values.

    Use ``parq`` (one-char typo of ``para``, edit-distance 1) so the
    difflib 0.6 cutoff fires reliably. Shorter typos like ``pra`` fall
    below the threshold and return no suggestion — that's a feature
    of the helper (silent on uncertain matches), pinned in
    ``test_no_suggestion_when_input_is_distant_from_all_valid``.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["config", "edit", "--methodology", "parq"])
    assert result.exit_code != 0, result.output
    normalized = " ".join(result.output.lower().split())
    # Every value in _VALID_METHODOLOGIES must appear.
    for value in ("none", "para", "jd"):
        assert value in normalized, f"missing valid methodology '{value}' in error output"
    # Rich may wrap "Did you mean" across a newline; check word
    # components individually for wrap-immunity.
    assert "did" in normalized
    assert "you mean" in normalized
    assert "'para'" in normalized  # suggested correction (quoted)


@pytest.mark.integration
@pytest.mark.ci
def test_config_edit_distant_value_no_suggestion(isolated_config: Path) -> None:
    """When the input is too far from any valid value, no 'did you mean'
    appears — better to say nothing than to suggest something obviously
    wrong."""
    runner = CliRunner()
    result = runner.invoke(app, ["config", "edit", "--device", "zzzzzz"])
    assert result.exit_code != 0, result.output
    normalized = " ".join(result.output.lower().split())
    assert "auto" in normalized  # valid-values list still appears
    # The "Did you mean" clause must NOT appear at all (any word order
    # / wrap permutation). The most reliable check: the suggestion
    # phrase requires "you mean" right after "did" — both absent
    # together is the contract.
    assert "you mean" not in normalized
