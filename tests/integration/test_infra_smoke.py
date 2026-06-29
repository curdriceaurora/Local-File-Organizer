"""Smoke tests validating integration test fixtures.

One test per layer confirms each fixture wires up correctly.  These are
deliberately minimal: proving the CLI invocation and model interface work
end-to-end — not exercising full business logic.

Layers covered:
  - CLI                       → ``cli_runner`` fixture
  - Model integrations        → ``fake_text_model`` fixture
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app as cli_app
from tests.integration.conftest import FakeTextModel, make_text_config

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Layer: CLI (cli_runner)
# ---------------------------------------------------------------------------


class TestCliRunnerFixture:
    """Smoke tests for the ``cli_runner`` fixture.

    Verifies that the Typer CliRunner can invoke the CLI app and that basic
    commands succeed without needing a live model or file system.
    """

    def test_help_exits_zero(self, cli_runner: CliRunner) -> None:
        """``--help`` exits with code 0."""
        result = cli_runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0

    def test_help_mentions_app_name(self, cli_runner: CliRunner) -> None:
        """Help text includes the application name."""
        result = cli_runner.invoke(cli_app, ["--help"])
        assert "fo" in result.output.lower()

    def test_successive_invocations_are_independent(self, cli_runner: CliRunner) -> None:
        """Multiple invocations on the same runner are independent (no state leak)."""
        r1 = cli_runner.invoke(cli_app, ["--help"])
        r2 = cli_runner.invoke(cli_app, ["--help"])
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.output == r2.output


# ---------------------------------------------------------------------------
# Layer: Model integrations (fake_text_model)
# ---------------------------------------------------------------------------


class TestFakeTextModelFixture:
    """Smoke tests for the ``fake_text_model`` fixture.

    Verifies that ``FakeTextModel`` satisfies the ``BaseModel`` interface and
    returns deterministic responses matching ``_TEXT_RESPONSES``.
    """

    def test_is_initialized_after_fixture(self, fake_text_model: FakeTextModel) -> None:
        """Fixture delivers a pre-initialized model."""
        assert fake_text_model.is_initialized is True

    def test_generate_categorize_keyword(self, fake_text_model: FakeTextModel) -> None:
        """``categorize`` keyword → Software Documentation."""
        result = fake_text_model.generate("please categorize this document")
        assert result == "Software Documentation"

    def test_generate_filename_keyword(self, fake_text_model: FakeTextModel) -> None:
        """``filename`` keyword → Software_Architecture_Guide."""
        result = fake_text_model.generate("generate a filename for this file")
        assert result == "Software_Architecture_Guide"

    def test_generate_describe_keyword(self, fake_text_model: FakeTextModel) -> None:
        """``describe`` keyword → description response."""
        result = fake_text_model.generate("describe the contents of this document")
        assert result == "A document about software architecture and design patterns."

    def test_generate_default_response(self, fake_text_model: FakeTextModel) -> None:
        """Unknown prompt → default stub response."""
        result = fake_text_model.generate("some unrecognized prompt xyz")
        assert result == "Deterministic stub response for integration tests."

    def test_cleanup_deinitializes_and_rejects_generate(
        self, fake_text_model: FakeTextModel
    ) -> None:
        """``cleanup()`` marks the model as shut down and subsequent ``generate()`` raises."""
        fake_text_model.cleanup()
        assert fake_text_model.is_initialized is False
        with pytest.raises(RuntimeError, match="Model is shutting down"):
            fake_text_model.generate("any prompt")

    def test_uninitialized_model_is_not_initialized(self) -> None:
        """A freshly constructed (not initialized) FakeTextModel is not ready."""
        model = FakeTextModel(make_text_config())
        assert model.is_initialized is False
