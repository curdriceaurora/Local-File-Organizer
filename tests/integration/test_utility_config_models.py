"""Integration tests for small utility/config/model modules.

Covers:
  - daemon/config.py               — DaemonConfig
  - events/config.py               — EventConfig
  - plugins/sdk/testing.py         — PluginTestCase
  - client/exceptions.py           — ClientError, AuthenticationError, etc.
  - models/_openai_response.py     — is_openai_token_exhausted
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from file_organizer.daemon.config import DaemonConfig
from file_organizer.events.config import EventConfig
from file_organizer.models._openai_response import is_openai_token_exhausted
from file_organizer.plugins.sdk.testing import PluginTestCase

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# DaemonConfig
# ---------------------------------------------------------------------------


class TestDaemonConfigInit:
    def test_default_created(self) -> None:
        cfg = DaemonConfig()
        assert cfg is not None

    def test_default_dry_run(self) -> None:
        assert DaemonConfig().dry_run is True

    def test_default_poll_interval(self) -> None:
        assert DaemonConfig().poll_interval == 1.0

    def test_default_max_concurrent(self) -> None:
        assert DaemonConfig().max_concurrent == 4

    def test_watch_dirs_normalized(self, tmp_path: Path) -> None:
        cfg = DaemonConfig(watch_directories=[str(tmp_path)])
        assert isinstance(cfg.watch_directories[0], Path)

    def test_output_dir_normalized(self, tmp_path: Path) -> None:
        cfg = DaemonConfig(output_directory=str(tmp_path))
        assert isinstance(cfg.output_directory, Path)

    def test_pid_file_normalized(self, tmp_path: Path) -> None:
        cfg = DaemonConfig(pid_file=str(tmp_path / "daemon.pid"))
        assert isinstance(cfg.pid_file, Path)

    def test_log_file_normalized(self, tmp_path: Path) -> None:
        cfg = DaemonConfig(log_file=str(tmp_path / "daemon.log"))
        assert isinstance(cfg.log_file, Path)

    def test_zero_poll_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="poll_interval"):
            DaemonConfig(poll_interval=0)

    def test_negative_poll_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="poll_interval"):
            DaemonConfig(poll_interval=-1.0)

    def test_zero_max_concurrent_raises(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent"):
            DaemonConfig(max_concurrent=0)

    def test_negative_max_concurrent_raises(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent"):
            DaemonConfig(max_concurrent=-1)


# ---------------------------------------------------------------------------
# EventConfig
# ---------------------------------------------------------------------------


class TestEventConfigInit:
    def test_created(self) -> None:
        cfg = EventConfig()
        assert cfg is not None

    def test_default_redis_url(self) -> None:
        cfg = EventConfig()
        assert "redis" in cfg.redis_url.lower()

    def test_default_stream_prefix(self) -> None:
        cfg = EventConfig()
        assert isinstance(cfg.stream_prefix, str)
        assert len(cfg.stream_prefix) > 0

    def test_custom_values(self) -> None:
        cfg = EventConfig(redis_url="redis://custom:6380/1", batch_size=20)
        assert cfg.batch_size == 20
        assert "custom" in cfg.redis_url


class TestEventConfigGetStreamName:
    def test_returns_prefixed_name(self) -> None:
        cfg = EventConfig(stream_prefix="myapp")
        result = cfg.get_stream_name("events")
        assert result == "myapp:events"

    def test_custom_prefix(self) -> None:
        cfg = EventConfig(stream_prefix="test")
        result = cfg.get_stream_name("files")
        assert result == "test:files"

    def test_returns_string(self) -> None:
        cfg = EventConfig()
        result = cfg.get_stream_name("anything")
        assert result == "fileorg:anything"


# ---------------------------------------------------------------------------
# PluginTestCase
# ---------------------------------------------------------------------------


class TestPluginTestCaseLifecycle:
    def test_setUp_creates_test_dir(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        try:
            assert tc.test_dir.exists()
        finally:
            tc.tearDown()

    def test_create_test_file_creates_file(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        try:
            f = tc.create_test_file("subdir/file.txt", content="hello")
            assert f.exists()
            assert f.read_text(encoding="utf-8") == "hello"
        finally:
            tc.tearDown()

    def test_create_test_file_returns_path(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        try:
            result = tc.create_test_file("f.txt")
            assert isinstance(result, Path)
        finally:
            tc.tearDown()

    def test_assert_file_exists_passes(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        try:
            f = tc.create_test_file("f.txt", "x")
            tc.assert_file_exists(f)
        finally:
            tc.tearDown()

    def test_assert_file_not_exists_passes(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        try:
            missing = tc.test_dir / "missing.txt"
            tc.assert_file_not_exists(missing)
        finally:
            tc.tearDown()

    def test_teardown_cleans_up(self) -> None:
        tc = PluginTestCase()
        tc.setUp()
        test_dir = tc.test_dir
        tc.create_test_file("f.txt", "x")
        tc.tearDown()
        assert not test_dir.exists()


# ---------------------------------------------------------------------------
# ClientError hierarchy
# ---------------------------------------------------------------------------


class TestClientError:
    def test_is_exception(self) -> None:
        err = ClientError("bad request")
        assert isinstance(err, Exception)

    def test_message(self) -> None:
        err = ClientError("bad request")
        assert str(err) == "bad request"

    def test_status_code(self) -> None:
        err = ClientError("bad request", status_code=400)
        assert err.status_code == 400

    def test_detail(self) -> None:
        err = ClientError("bad", detail="extra info")
        assert err.detail == "extra info"

    def test_default_status_code(self) -> None:
        assert ClientError("x").status_code == 0

    def test_default_detail(self) -> None:
        assert ClientError("x").detail == ""


class TestClientErrorSubclasses:
    def test_authentication_error_is_client_error(self) -> None:
        err = AuthenticationError("unauthorized", status_code=401)
        assert isinstance(err, ClientError)
        assert err.status_code == 401

    def test_not_found_error_is_client_error(self) -> None:
        err = NotFoundError("not found", status_code=404)
        assert isinstance(err, ClientError)

    def test_server_error_is_client_error(self) -> None:
        err = ServerError("internal error", status_code=500)
        assert isinstance(err, ClientError)

    def test_validation_error_is_client_error(self) -> None:
        err = ValidationError("invalid", status_code=422)
        assert isinstance(err, ClientError)

    def test_raise_and_catch_authentication(self) -> None:
        with pytest.raises(ClientError):
            raise AuthenticationError("unauthorized")

    def test_raise_and_catch_specific(self) -> None:
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("unauthorized")


# ---------------------------------------------------------------------------
# is_openai_token_exhausted
# ---------------------------------------------------------------------------


def _make_response(finish_reason: str, content: str) -> object:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(finish_reason=finish_reason, message=message)
    return SimpleNamespace(choices=[choice])


class TestIsOpenAITokenExhausted:
    def test_length_reason_short_content_returns_true(self) -> None:
        response = _make_response("length", "ok")
        assert is_openai_token_exhausted(response) is True

    def test_stop_reason_returns_false(self) -> None:
        response = _make_response("stop", "ok")
        assert is_openai_token_exhausted(response) is False

    def test_length_reason_long_content_returns_false(self) -> None:
        response = _make_response("length", "x" * 200)
        assert is_openai_token_exhausted(response) is False

    def test_empty_choices_returns_false(self) -> None:
        response = SimpleNamespace(choices=[])
        assert is_openai_token_exhausted(response) is False

    def test_none_content_short(self) -> None:
        message = SimpleNamespace(content=None)
        choice = SimpleNamespace(finish_reason="length", message=message)
        response = SimpleNamespace(choices=[choice])
        assert is_openai_token_exhausted(response) is True

    def test_custom_min_length(self) -> None:
        response = _make_response("length", "x" * 10)
        assert is_openai_token_exhausted(response, min_length=5) is False
        assert is_openai_token_exhausted(response, min_length=20) is True
