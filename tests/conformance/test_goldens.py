"""Unit tests for the conformance golden fixture loader (#1659)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tests.conformance.goldens import load_golden


def test_load_golden_valid() -> None:
    """Valid golden fixture loads successfully as a dictionary."""
    data = load_golden("traversal_policy")
    assert isinstance(data, dict)
    assert "cases" in data


def test_load_golden_missing_raises_file_not_found() -> None:
    """Missing fixture file raises FileNotFoundError with descriptive message."""
    with pytest.raises(FileNotFoundError, match="Conformance golden fixture missing at"):
        load_golden("non_existent_fixture_spec")


def test_load_golden_malformed_json_raises_json_decode_error(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Malformed JSON fixture raises json.JSONDecodeError."""
    bad_fixture = tmp_path / "bad_fixture.json"
    bad_fixture.write_text("{invalid json:", encoding="utf-8")

    with patch("tests.conformance.goldens._FIXTURES_DIR", tmp_path):
        load_golden.cache_clear()
        with pytest.raises(json.JSONDecodeError):
            load_golden("bad_fixture")
