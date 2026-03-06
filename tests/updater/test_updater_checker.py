"""Tests for file_organizer.updater.checker module.

Covers _parse_version, AssetInfo, ReleaseInfo, UpdateChecker.check,
get_latest_release, _fetch_latest_release, _parse_release, _detect_version.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.updater.checker import (
    AssetInfo,
    ReleaseInfo,
    UpdateChecker,
    _parse_version,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseVersion:
    """Test _parse_version function."""

    def test_simple(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert _parse_version("v2.0.0") == (2, 0, 0)

    def test_with_prerelease(self):
        assert _parse_version("2.0.0-alpha.1") == (2, 0, 0)

    def test_single_number(self):
        assert _parse_version("5") == (5,)

    def test_empty_string(self):
        assert _parse_version("") == (0,)

    def test_non_numeric(self):
        assert _parse_version("abc") == (0,)

    def test_mixed_segments(self):
        assert _parse_version("1.2.abc") == (1, 2)


# ---------------------------------------------------------------------------
# AssetInfo / ReleaseInfo
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDataclasses:
    """Test data model dataclasses."""

    def test_asset_info_defaults(self):
        a = AssetInfo(name="app.bin", url="https://example.com/app.bin")
        assert a.size == 0
        assert a.content_type == ""

    def test_release_info_defaults(self):
        r = ReleaseInfo()
        assert r.tag == ""
        assert r.version == ""
        assert r.prerelease is False
        assert r.assets == []
        assert r.body == ""


# ---------------------------------------------------------------------------
# UpdateChecker — check
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateCheckerCheck:
    """Test UpdateChecker.check method."""

    @patch("file_organizer.updater.checker.httpx")
    def test_no_update(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.0.0",
            "prerelease": False,
            "body": "notes",
            "assets": [],
            "published_at": "2025-01-01",
            "html_url": "https://github.com",
        }
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="2.0.0")
        result = checker.check()
        assert result is None

    @patch("file_organizer.updater.checker.httpx")
    def test_update_available(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v3.0.0",
            "prerelease": False,
            "body": "notes",
            "assets": [
                {
                    "name": "app.bin",
                    "browser_download_url": "https://example.com/app.bin",
                    "size": 1000,
                    "content_type": "application/octet-stream",
                }
            ],
            "published_at": "2025-06-01",
            "html_url": "https://github.com/release/v3",
        }
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0")
        result = checker.check()
        assert result is not None
        assert result.version == "3.0.0"
        assert len(result.assets) == 1

    @patch("file_organizer.updater.checker.httpx")
    def test_check_exception(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("network error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0")
        result = checker.check()
        assert result is None


# ---------------------------------------------------------------------------
# UpdateChecker — get_latest_release
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLatestRelease:
    """Test get_latest_release method."""

    @patch("file_organizer.updater.checker.httpx")
    def test_success(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "body": "",
            "assets": [],
            "published_at": "",
            "html_url": "",
        }
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0")
        result = checker.get_latest_release()
        assert result is not None
        assert result.version == "2.0.0"

    @patch("file_organizer.updater.checker.httpx")
    def test_failure(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("fail")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0")
        result = checker.get_latest_release()
        assert result is None


# ---------------------------------------------------------------------------
# _fetch_latest_release — prerelease mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchLatestReleasePrerelease:
    """Test _fetch_latest_release with include_prereleases."""

    @patch("file_organizer.updater.checker.httpx")
    def test_prerelease_returns_first_nondraft(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "tag_name": "v2.0.0-rc1",
                "draft": False,
                "prerelease": True,
                "body": "",
                "assets": [],
                "published_at": "",
                "html_url": "",
            },
        ]
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=True)
        result = checker._fetch_latest_release()
        assert result is not None
        assert result.version == "2.0.0-rc1"

    @patch("file_organizer.updater.checker.httpx")
    def test_prerelease_skips_drafts(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "tag_name": "v3.0.0",
                "draft": True,
                "prerelease": False,
                "body": "",
                "assets": [],
                "published_at": "",
                "html_url": "",
            },
        ]
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=True)
        result = checker._fetch_latest_release()
        assert result is None

    @patch("file_organizer.updater.checker.httpx")
    def test_prerelease_404(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=True)
        result = checker._fetch_latest_release()
        assert result is None

    @patch("file_organizer.updater.checker.httpx")
    def test_prerelease_not_list(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "unexpected"}
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=True)
        result = checker._fetch_latest_release()
        assert result is None

    @patch("file_organizer.updater.checker.httpx")
    def test_latest_404(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=False)
        result = checker._fetch_latest_release()
        assert result is None

    @patch("file_organizer.updater.checker.httpx")
    def test_latest_not_dict(self, mock_httpx):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = ["unexpected"]
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_httpx.Client.return_value = mock_client

        checker = UpdateChecker(current_version="1.0.0", include_prereleases=False)
        result = checker._fetch_latest_release()
        assert result is None


# ---------------------------------------------------------------------------
# _parse_release
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseRelease:
    """Test _parse_release static method."""

    def test_full_release(self):
        data = {
            "tag_name": "v2.5.1",
            "prerelease": False,
            "body": "Release notes",
            "assets": [
                {
                    "name": "app-linux.bin",
                    "browser_download_url": "https://example.com/app.bin",
                    "size": 5000,
                    "content_type": "application/octet-stream",
                }
            ],
            "published_at": "2025-06-01T00:00:00Z",
            "html_url": "https://github.com/releases/v2.5.1",
        }
        release = UpdateChecker._parse_release(data)
        assert release.tag == "v2.5.1"
        assert release.version == "2.5.1"
        assert release.prerelease is False
        assert len(release.assets) == 1
        assert release.assets[0].name == "app-linux.bin"

    def test_empty_data(self):
        release = UpdateChecker._parse_release({})
        assert release.tag == ""
        assert release.version == ""
        assert release.assets == []


# ---------------------------------------------------------------------------
# _detect_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectVersion:
    """Test _detect_version static method."""

    @patch("file_organizer.updater.checker.UpdateChecker._detect_version", return_value="0.0.0")
    def test_fallback(self, mock_detect):
        checker = UpdateChecker()
        assert checker.current_version == "0.0.0"

    def test_detect_import_error(self):
        with patch.dict("sys.modules", {"file_organizer.version": None}):
            result = UpdateChecker._detect_version()
            assert result == "0.0.0"
