"""Signed release metadata trust verification module for the updater.

Verifies release manifest files against a pinned public key.
"""

from __future__ import annotations

import base64
import json
from typing import Any, cast

from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import eddsa
from loguru import logger

PINNED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAnirlcO8/RIANG5F9tLrXR+QJR6Vshpcz+TDnlrV2gIY=
-----END PUBLIC KEY-----"""

# Upper bound on a single release asset size recorded in the manifest (10 GiB).
# Anything larger is treated as malformed metadata and fails closed.
_MAX_ASSET_SIZE = 10 * 1024**3

_SHA256_HEX_LENGTH = 64
_SHA256_HEX_CHARS = frozenset("0123456789abcdef")


def verify_manifest_signature(manifest_content: str, signature_content: str) -> bool:
    """Verify that the manifest JSON matches the base64-encoded signature.

    Args:
        manifest_content: UTF-8 manifest JSON string.
        signature_content: Base64-encoded or raw signature bytes.

    Returns:
        True if the signature is valid.
    """
    try:
        # Load and parse manifest to ensure it is valid JSON
        manifest_data = json.loads(manifest_content)
        # Canonicalize JSON for deterministic serialization
        canonical_bytes = json.dumps(manifest_data, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

        # Load the public key
        pub_key = ECC.import_key(PINNED_PUBLIC_KEY)

        # Decode signature content. Strict base64 only: a malformed or
        # tampered encoding must fail closed rather than be reinterpreted.
        sig_bytes = base64.b64decode(signature_content.strip(), validate=True)

        # Verify using Ed25519 (EdDSA RFC8032)
        verifier = eddsa.new(pub_key, "rfc8032")
        verifier.verify(canonical_bytes, sig_bytes)
        return True
    except Exception as exc:
        logger.error("Signature verification failed: {}", exc)
        return False


def verify_release_manifest(
    manifest_content: str,
    signature_content: str,
    expected_repo: str,
    expected_tag: str,
    expected_version: str,
) -> dict[str, Any] | None:
    """Verify the manifest signature and validate the metadata claims.

    Args:
        manifest_content: Manifest JSON content.
        signature_content: Detached signature content.
        expected_repo: Expected repository identity (e.g. owner/repo).
        expected_tag: Expected Git release tag (e.g. v2.1.0).
        expected_version: Expected normalised version (e.g. 2.1.0).

    Returns:
        The verified manifest data as dict, or None if validation fails.
    """
    if not verify_manifest_signature(manifest_content, signature_content):
        logger.error("Manifest signature verification failed.")
        return None

    try:
        manifest_data = json.loads(manifest_content)
    except Exception as exc:
        logger.error("Failed to parse verified manifest JSON: {}", exc)
        return None

    # A validly signed payload must still be a manifest object, not a bare
    # list/scalar — fail closed instead of crashing on attribute access.
    if not isinstance(manifest_data, dict):
        logger.error("Manifest is not a JSON object: {}", type(manifest_data).__name__)
        return None

    # Validate Schema
    schema_version = manifest_data.get("schema_version")
    if schema_version != 1:
        logger.error("Unsupported manifest schema version: {}", schema_version)
        return None

    # Validate Repo identity
    repo = manifest_data.get("repo")
    if repo != expected_repo:
        logger.error("Manifest repo identity mismatch: expected {}, got {}", expected_repo, repo)
        return None

    # Validate Tag/Version (must match the release we are applying)
    tag = manifest_data.get("tag")
    version = manifest_data.get("version")
    if tag != expected_tag:
        logger.error("Manifest tag mismatch: expected {}, got {}", expected_tag, tag)
        return None
    if version != expected_version:
        logger.error("Manifest version mismatch: expected {}, got {}", expected_version, version)
        return None

    published_at = manifest_data.get("published_at")
    if not isinstance(published_at, str) or not published_at:
        logger.error("Manifest published_at is missing or not a string.")
        return None

    if not _validate_manifest_assets(manifest_data.get("assets")):
        return None

    return cast(dict[str, Any], manifest_data)


def _validate_manifest_assets(assets: object) -> bool:
    """Validate the manifest's asset entries, failing closed on any anomaly.

    Requires a list of uniquely named asset objects, each with a non-empty
    string name, a bounded non-negative integer size, and a 64-character
    lowercase-hex SHA-256 digest.
    """
    if not isinstance(assets, list) or not assets:
        logger.error("Manifest assets must be a non-empty list.")
        return False

    seen_names: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict):
            logger.error("Manifest asset entry is not an object: {!r}", entry)
            return False

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            logger.error("Manifest asset name is missing or not a string.")
            return False
        if name in seen_names:
            logger.error("Manifest contains duplicate asset name: {}", name)
            return False
        seen_names.add(name)

        size = entry.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= _MAX_ASSET_SIZE:
            logger.error("Manifest asset {} has invalid size: {!r}", name, size)
            return False

        sha256 = entry.get("sha256")
        if (
            not isinstance(sha256, str)
            or len(sha256) != _SHA256_HEX_LENGTH
            or not set(sha256) <= _SHA256_HEX_CHARS
        ):
            logger.error("Manifest asset {} has invalid sha256 digest.", name)
            return False

    return True
