#!/usr/bin/env python3
"""Generates, signs, and locally verifies the release manifest in CI."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import eddsa

# Add src/ to path so we can import trust
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from file_organizer.updater import trust


def sha256_of_file(path: Path) -> str:
    """Calculate the SHA256 digest of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "curdriceaurora/Local-File-Organizer")
    release_tag = os.environ.get("RELEASE_TAG")
    private_key_pem = os.environ.get("RELEASE_SIGNING_KEY")

    if not release_tag:
        print("ERROR: RELEASE_TAG environment variable not set.", file=sys.stderr)
        return 1

    if not private_key_pem:
        print("ERROR: RELEASE_SIGNING_KEY environment variable not set.", file=sys.stderr)
        return 1

    # Define build version
    version = release_tag.lstrip("v")

    artifacts_dir = Path("artifacts")
    if not artifacts_dir.exists():
        print("ERROR: artifacts/ directory does not exist.", file=sys.stderr)
        return 1

    # Find and hash all artifacts (excluding metadata/checksum files)
    assets = []
    ignored_names = {
        "file-organizer-release-manifest.json",
        "file-organizer-release-manifest.json.sig",
        "SHA256SUMS.txt",
    }

    for path in sorted(artifacts_dir.glob("**/*")):
        if path.is_file() and path.name not in ignored_names:
            rel_name = path.relative_to(artifacts_dir).as_posix()
            size = path.stat().st_size
            sha256 = sha256_of_file(path)
            assets.append(
                {
                    "name": rel_name,
                    "size": size,
                    "sha256": sha256,
                }
            )

    if not assets:
        print("ERROR: No assets found in artifacts/ directory to sign.", file=sys.stderr)
        return 1

    # Generate Manifest
    manifest = {
        "schema_version": 1,
        "repo": repo,
        "tag": release_tag,
        "version": version,
        "published_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "assets": assets,
    }

    # Canonicalize and sign
    canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")

    try:
        priv_key = ECC.import_key(private_key_pem)
    except Exception as exc:
        print(f"ERROR: Failed to parse private key: {exc}", file=sys.stderr)
        return 1

    signer = eddsa.new(priv_key, "rfc8032")
    signature = signer.sign(canonical_bytes)
    sig_b64 = base64.b64encode(signature).decode("utf-8")

    # Paths to write
    manifest_path = artifacts_dir / "file-organizer-release-manifest.json"
    sig_path = artifacts_dir / "file-organizer-release-manifest.json.sig"

    # Write output
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sig_path.write_text(sig_b64, encoding="utf-8")

    print(f"Successfully generated signed release manifest for tag {release_tag}.")
    print(f"Manifest path: {manifest_path}")
    print(f"Signature path: {sig_path}")

    # Local Verification Test
    manifest_content = manifest_path.read_text(encoding="utf-8")
    sig_content = sig_path.read_text(encoding="utf-8")

    verified_manifest = trust.verify_release_manifest(
        manifest_content,
        sig_content,
        expected_repo=repo,
        expected_tag=release_tag,
        expected_version=version,
    )

    if verified_manifest is None:
        print(
            "ERROR: Generated manifest failed local verification against pinned public key!",
            file=sys.stderr,
        )
        return 1

    print("Success: Local verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
