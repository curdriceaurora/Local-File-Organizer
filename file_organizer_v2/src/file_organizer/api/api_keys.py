"""API key helpers for external integrations."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sys
from collections.abc import Iterable


def generate_api_key(prefix: str = "fo") -> str:
    """Generate a new API key."""
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{token}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(api_key: str, hashes: Iterable[str]) -> bool:
    """Verify an API key against stored hashes."""
    candidate = hash_api_key(api_key)
    return any(hmac.compare_digest(candidate, stored) for stored in hashes)


def _print_usage() -> None:
    print("Usage: python -m file_organizer.api.api_keys [--prefix PREFIX]")


def _main(argv: list[str]) -> int:
    prefix = "fo"
    if "--help" in argv or "-h" in argv:
        _print_usage()
        return 0
    if "--prefix" in argv:
        try:
            prefix = argv[argv.index("--prefix") + 1]
        except (ValueError, IndexError):
            _print_usage()
            return 1
    api_key = generate_api_key(prefix=prefix)
    print("API key:", api_key)
    print("SHA-256:", hash_api_key(api_key))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
