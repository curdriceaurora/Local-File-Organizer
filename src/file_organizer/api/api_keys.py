"""API key helpers for external integrations."""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from passlib.context import CryptContext

_API_KEY_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key(prefix: str = "fo") -> str:
    """Generate a new API key."""
    key_id = secrets.token_hex(4)
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{key_id}_{token}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return cast(str, _API_KEY_CONTEXT.hash(api_key))


def match_api_key_hash(api_key: str, hashes: Iterable[str]) -> str | None:
    """Return the stored hash matching an API key, if any."""
    for stored in hashes:
        try:
            if _API_KEY_CONTEXT.verify(api_key, stored):
                return stored
        except (ValueError, TypeError):
            continue
    return None


def verify_api_key(api_key: str, hashes: Iterable[str]) -> bool:
    """Verify an API key against stored hashes."""
    return match_api_key_hash(api_key, hashes) is not None


def api_key_identifier(api_key: str, hashes: Iterable[str]) -> str | None:
    """Return a stable identifier derived from the stored hash."""
    matched = match_api_key_hash(api_key, hashes)
    if not matched:
        return None
    parts = api_key.split("_", 2)
    if len(parts) == 3 and parts[1]:
        return parts[1]
    return matched[-12:]


def _write_key(path: Path, api_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(api_key)


def _print_usage() -> None:
    print("Usage: python -m file_organizer.api.api_keys --output PATH [--prefix PREFIX]")


def _main(argv: list[str]) -> int:
    prefix = "fo"
    output_path: Path | None = None
    if "--help" in argv or "-h" in argv:
        _print_usage()
        return 0
    if "--prefix" in argv:
        try:
            prefix = argv[argv.index("--prefix") + 1]
        except (ValueError, IndexError):
            _print_usage()
            return 1
    if "--output" in argv:
        try:
            # CLI output path is an explicit user selection for local key storage.
            output_path = Path(argv[argv.index("--output") + 1]).expanduser()  # codeql[py/path-injection]
        except (ValueError, IndexError):
            _print_usage()
            return 1
    if output_path is None:
        _print_usage()
        print("Missing --output PATH to safely store the generated API key.")
        return 1
    api_key = generate_api_key(prefix=prefix)
    _write_key(output_path, api_key)
    print("API key saved to:", output_path)
    print("Bcrypt hash:", hash_api_key(api_key))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
