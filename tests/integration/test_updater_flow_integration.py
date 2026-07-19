"""End-to-end integration tests for the updater check→install→rollback cycle.

A real local HTTP server serves GitHub-Releases-shaped JSON plus real asset
bytes (the platform binary and a signed release manifest). The tests drive
:class:`UpdateChecker`, :class:`UpdateInstaller`, and :class:`UpdateManager`
against it with real HTTP requests, real SHA-256 verification, real
Ed25519 signature verification, and real on-disk atomic install/rollback —
only the pinned public key and GitHub API base URL are redirected.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest
from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import eddsa

from file_organizer.updater import checker as checker_mod
from file_organizer.updater import trust
from file_organizer.updater.checker import UpdateChecker
from file_organizer.updater.installer import (
    UpdateInstaller,
    _get_arch_hints,
    _get_platform_hints,
)
from file_organizer.updater.manager import UpdateManager

pytestmark = [pytest.mark.integration, pytest.mark.ci]

_REPO = "curdriceaurora/Local-File-Organizer"


def _platform_binary_name() -> str:
    """Asset name that ``select_asset`` will match on the running platform."""
    plat = _get_platform_hints()[0]
    arch_hints = _get_arch_hints()
    arch = arch_hints[0] if arch_hints else "x86_64"
    return f"file-organizer-{plat}-{arch}"


@dataclass
class _ReleaseServer:
    """Mutable state served by the fake GitHub/release HTTP server."""

    base_url: str = ""
    release_json: dict | None = None
    assets: dict[str, bytes] = field(default_factory=dict)

    def asset_url(self, name: str) -> str:
        return f"{self.base_url}/dl/{name}"


@pytest.fixture
def release_server() -> Iterator[_ReleaseServer]:
    """Spin up a threaded HTTP server serving release metadata and assets."""
    state = _ReleaseServer()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silence noise
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.endswith("/releases/latest"):
                if state.release_json is None:
                    self._send(404, b'{"message":"Not Found"}', "application/json")
                    return
                self._send(
                    200,
                    json.dumps(state.release_json).encode("utf-8"),
                    "application/json",
                )
                return
            if self.path.startswith("/dl/"):
                name = unquote(self.path[len("/dl/") :])
                blob = state.assets.get(name)
                if blob is None:
                    self._send(404, b"missing", "text/plain")
                    return
                self._send(200, blob, "application/octet-stream")
                return
            self._send(404, b"not found", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> ECC.EccKey:
    """Generate a test Ed25519 key and pin its public half in the trust module."""
    key = ECC.generate(curve="ed25519")
    monkeypatch.setattr(trust, "PINNED_PUBLIC_KEY", key.public_key().export_key(format="PEM"))
    return key


def _sign_manifest(manifest: dict, key: ECC.EccKey) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = eddsa.new(key, "rfc8032").sign(canonical)
    return base64.b64encode(signature).decode("utf-8")


def _publish_release(
    state: _ReleaseServer,
    key: ECC.EccKey,
    *,
    tag: str = "v9.9.9",
    binary_bytes: bytes = b"new-binary-payload-v9",
    corrupt_binary: bool = False,
) -> dict:
    """Register a signed release (binary + manifest + signature) on the server."""
    binary_name = _platform_binary_name()
    version = tag.lstrip("v")

    digest = hashlib.sha256(binary_bytes).hexdigest()
    manifest = {
        "schema_version": 1,
        "repo": _REPO,
        "tag": tag,
        "version": version,
        "published_at": "2026-07-19T00:00:00Z",
        "assets": [{"name": binary_name, "size": len(binary_bytes), "sha256": digest}],
    }
    signature_b64 = _sign_manifest(manifest, key)

    # Corrupt the *content* while preserving the length so the served bytes
    # pass the size check and fail specifically on the SHA-256 comparison.
    served_binary = bytes(b ^ 0xFF for b in binary_bytes) if corrupt_binary else binary_bytes
    state.assets = {
        binary_name: served_binary,
        "file-organizer-release-manifest.json": json.dumps(manifest).encode("utf-8"),
        "file-organizer-release-manifest.json.sig": signature_b64.encode("utf-8"),
    }
    state.release_json = {
        "tag_name": tag,
        "prerelease": False,
        "published_at": "2026-07-19T00:00:00Z",
        "html_url": f"{state.base_url}/release",
        "assets": [
            {"name": name, "browser_download_url": state.asset_url(name), "size": len(blob)}
            for name, blob in state.assets.items()
        ],
    }
    return manifest


@pytest.fixture
def point_checker_at_server(
    release_server: _ReleaseServer, monkeypatch: pytest.MonkeyPatch
) -> _ReleaseServer:
    """Redirect the checker's GitHub API base at the local server."""
    monkeypatch.setattr(checker_mod, "_GITHUB_API", release_server.base_url)
    return release_server


def test_checker_reports_newer_version(
    point_checker_at_server: _ReleaseServer, signing_key: ECC.EccKey
) -> None:
    """UpdateChecker fetches the latest release over real HTTP and compares versions."""
    _publish_release(point_checker_at_server, signing_key, tag="v9.9.9")
    checker = UpdateChecker(repo=_REPO, current_version="1.0.0")

    release = checker.check()
    assert release is not None
    assert release.version == "9.9.9"
    assert release.tag == "v9.9.9"
    assert any(a.name == _platform_binary_name() for a in release.assets)


def test_checker_returns_none_when_up_to_date(
    point_checker_at_server: _ReleaseServer, signing_key: ECC.EccKey
) -> None:
    """No update is reported when the current version is already the latest."""
    _publish_release(point_checker_at_server, signing_key, tag="v2.0.0")
    checker = UpdateChecker(repo=_REPO, current_version="2.0.0")
    assert checker.check() is None


def test_checker_handles_no_release(point_checker_at_server: _ReleaseServer) -> None:
    """A 404 from the releases endpoint yields no update."""
    point_checker_at_server.release_json = None
    checker = UpdateChecker(repo=_REPO, current_version="1.0.0")
    assert checker.check() is None


def test_full_update_cycle_installs_and_rolls_back(
    point_checker_at_server: _ReleaseServer,
    signing_key: ECC.EccKey,
    tmp_path: Path,
) -> None:
    """check → verify manifest → download → verify → install → rollback, end to end."""
    new_bytes = b"the-new-release-binary-contents"
    _publish_release(point_checker_at_server, signing_key, tag="v9.9.9", binary_bytes=new_bytes)

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "file-organizer"
    target.write_bytes(b"the-old-binary")

    manager = UpdateManager(repo=_REPO, current_version="1.0.0", install_dir=install_dir)

    status = manager.check()
    assert status.available is True
    assert status.latest_version == "9.9.9"

    result = manager.update()
    assert result.install_result is not None, result.message
    assert result.install_result.success, result.install_result.message

    # The binary on disk is now the freshly downloaded payload, verified by
    # its manifest SHA-256, and a backup of the old binary was kept.
    assert target.read_bytes() == new_bytes
    backup = install_dir / "file-organizer.bak"
    assert backup.exists()
    assert backup.read_bytes() == b"the-old-binary"

    # Rollback restores the previous binary.
    assert manager.rollback() is True
    assert target.read_bytes() == b"the-old-binary"


def test_dry_run_downloads_but_does_not_install(
    point_checker_at_server: _ReleaseServer,
    signing_key: ECC.EccKey,
    tmp_path: Path,
) -> None:
    """A dry-run update verifies and downloads but leaves the binary untouched."""
    _publish_release(point_checker_at_server, signing_key, tag="v9.9.9")

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "file-organizer"
    target.write_bytes(b"unchanged")

    manager = UpdateManager(repo=_REPO, current_version="1.0.0", install_dir=install_dir)
    result = manager.update(dry_run=True)

    assert result.install_result is not None
    assert result.install_result.success
    assert "Dry run" in result.install_result.message
    assert target.read_bytes() == b"unchanged"
    assert not (install_dir / "file-organizer.bak").exists()


def test_update_aborts_on_corrupt_binary(
    point_checker_at_server: _ReleaseServer,
    signing_key: ECC.EccKey,
    tmp_path: Path,
) -> None:
    """A binary whose bytes don't match the signed manifest digest fails closed."""
    _publish_release(
        point_checker_at_server,
        signing_key,
        tag="v9.9.9",
        binary_bytes=b"legit",
        corrupt_binary=True,  # server returns tampered bytes vs the signed digest
    )

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "file-organizer"
    target.write_bytes(b"still-here")

    manager = UpdateManager(repo=_REPO, current_version="1.0.0", install_dir=install_dir)
    result = manager.update()

    assert result.install_result is not None
    assert result.install_result.success is False
    assert "checksum" in result.install_result.message.lower()
    assert target.read_bytes() == b"still-here"  # nothing installed


def test_update_aborts_when_signature_untrusted(
    point_checker_at_server: _ReleaseServer,
    signing_key: ECC.EccKey,
    tmp_path: Path,
) -> None:
    """A manifest signed by a different key fails trust verification before download."""
    _publish_release(point_checker_at_server, signing_key, tag="v9.9.9")
    # Re-sign the manifest with an unrelated key so it no longer matches the pin.
    rogue = ECC.generate(curve="ed25519")
    manifest = json.loads(
        point_checker_at_server.assets["file-organizer-release-manifest.json"].decode("utf-8")
    )
    point_checker_at_server.assets["file-organizer-release-manifest.json.sig"] = _sign_manifest(
        manifest, rogue
    ).encode("utf-8")

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    manager = UpdateManager(repo=_REPO, current_version="1.0.0", install_dir=install_dir)
    result = manager.update()

    assert result.install_result is not None
    assert result.install_result.success is False
    assert "trust" in result.install_result.message.lower()


def test_installer_select_asset_matches_platform(
    point_checker_at_server: _ReleaseServer, signing_key: ECC.EccKey, tmp_path: Path
) -> None:
    """select_asset picks the platform binary and skips manifest/signature files."""
    _publish_release(point_checker_at_server, signing_key, tag="v9.9.9")
    checker = UpdateChecker(repo=_REPO, current_version="1.0.0")
    release = checker.check()
    assert release is not None

    installer = UpdateInstaller(install_dir=tmp_path)
    asset = installer.select_asset(release)
    assert asset is not None
    assert asset.name == _platform_binary_name()
