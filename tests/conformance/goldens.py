"""Loader for serialized conformance golden fixtures (#1659).

Golden expectations live as versioned JSON files under ``tests/conformance/fixtures/``.
This module loads and parses fixture data with session-level LRU caching.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@cache
def load_golden(name: str) -> dict[str, Any]:
    """Load and parse a JSON golden fixture by name.

    :param name: Fixture basename without extension (e.g. ``"traversal_policy"``).
    :return: Parsed JSON fixture structure.
    :raises FileNotFoundError: If the fixture file does not exist.
    :raises json.JSONDecodeError: If the fixture file contains invalid JSON.
    """
    path = _FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Conformance golden fixture missing at '{path}'")
    content = path.read_text(encoding="utf-8")
    result: dict[str, Any] = json.loads(content)
    return result
