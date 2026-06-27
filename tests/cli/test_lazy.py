"""Tests for the lazy CLI command loading infrastructure."""

from __future__ import annotations

import types
from unittest.mock import patch

import click
import pytest

from file_organizer.cli.lazy import LazyCommandProxy

pytestmark = [pytest.mark.ci, pytest.mark.unit, pytest.mark.integration]


def test_load_returns_non_typer_command_as_is() -> None:
    """A LazyCommandProxy whose target attribute is a plain click.Command
    (not a typer.Typer) is used directly, without conversion."""
    real_command = click.Command(name="real", callback=lambda: None)
    fake_module = types.SimpleNamespace(real_cmd=real_command)

    proxy = LazyCommandProxy("real", "fake.module.path", "real_cmd", "help text")

    with patch("importlib.import_module", return_value=fake_module) as mock_import:
        loaded = proxy._load()

    mock_import.assert_called_once_with("fake.module.path")
    assert loaded is real_command


def test_load_caches_result_across_calls() -> None:
    """Subsequent _load() calls reuse the cached command without re-importing."""
    real_command = click.Command(name="real", callback=lambda: None)
    fake_module = types.SimpleNamespace(real_cmd=real_command)

    proxy = LazyCommandProxy("real", "fake.module.path", "real_cmd", "help text")

    with patch("importlib.import_module", return_value=fake_module) as mock_import:
        first = proxy._load()
        second = proxy._load()

    mock_import.assert_called_once()
    assert first is second is real_command
