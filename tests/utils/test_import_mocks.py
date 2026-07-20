"""Tests for shared import-mocking helpers."""

from __future__ import annotations

import pytest

from tests.utils.import_mocks import make_fake_import


def test_make_fake_import_blocks_exact_and_submodule_names() -> None:
    fake_import = make_fake_import(missing_names=("pydub",))

    with pytest.raises(ImportError, match="no pydub"):
        fake_import("pydub")

    with pytest.raises(ImportError, match="no pydub.effects"):
        fake_import("pydub.effects")


def test_make_fake_import_blocks_substring_matches() -> None:
    fake_import = make_fake_import(missing_substrings=("mutagen",))

    with pytest.raises(ImportError, match="no some_mutagen_plugin"):
        fake_import("some_mutagen_plugin")


def test_make_fake_import_returns_configured_overrides() -> None:
    override = object()
    fake_import = make_fake_import(module_overrides={"tinytag": override})

    assert fake_import("tinytag") is override
    assert fake_import("tinytag.reader") is override


def test_make_fake_import_delegates_unrelated_imports() -> None:
    fake_import = make_fake_import(missing_names=("pydub",))

    assert fake_import("json").loads('{"ok": true}') == {"ok": True}
