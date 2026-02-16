"""Validation and normalization helpers for marketplace metadata."""
from __future__ import annotations

import re

_PLUGIN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PLUGIN_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def normalize_plugin_name(name: str) -> str:
    """Normalize and validate a plugin name used for metadata and filesystem paths."""
    candidate = name.strip()
    if not _PLUGIN_NAME_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid plugin name: {name!r}")
    return candidate


def normalize_plugin_version(version: str) -> str:
    """Normalize and validate plugin version string used in artifact names."""
    candidate = version.strip()
    if not _PLUGIN_VERSION_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid plugin version: {version!r}")
    if ".." in candidate:
        raise ValueError(f"Invalid plugin version: {version!r}")
    return candidate


def version_sort_key(version: str) -> tuple[tuple[int, str], ...]:
    """Generate stable sort key for semantic-ish version ordering."""
    parts = version.replace("-", ".").split(".")
    key: list[tuple[int, str]] = []
    for part in parts:
        token = part.strip()
        if token.isdigit():
            key.append((0, f"{int(token):08d}"))
        else:
            key.append((1, token.lower()))
    return tuple(key)
