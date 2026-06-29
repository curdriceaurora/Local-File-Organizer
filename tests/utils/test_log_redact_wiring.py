"""Runtime wiring of the credential-redacting log filter (#1269).

Proves `install_on_root()` is installed through the real CLI / API / desktop
startup paths — not only by direct unit-level filter invocation — so production
logs are scrubbed of token/key shapes.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

import pytest
from loguru import logger as loguru_logger

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Save/restore the global LogRecordFactory, root filters, loguru patcher."""
    orig_factory = logging.getLogRecordFactory()
    orig_filters = list(logging.getLogger().filters)
    try:
        yield
    finally:
        logging.setLogRecordFactory(orig_factory)
        root = logging.getLogger()
        for flt in list(root.filters):
            if flt not in orig_filters:
                root.removeFilter(flt)
        loguru_logger.configure(patcher=None)


def test_cli_startup_installs_and_redacts(
    restore_logging: None, caplog: pytest.LogCaptureFixture, tmp_path: object
) -> None:
    """Invoking any command runs main_callback → install_on_root, after which
    both stdlib and loguru messages are redacted."""
    from typer.testing import CliRunner

    from file_organizer.cli.main import app

    # This invocation fails fast at path validation (exit 2) — but the Typer
    # callback (and thus install_on_root) has already run by then.
    result = CliRunner().invoke(
        app, ["organize", str(tmp_path) + "/missing", str(tmp_path) + "/out"]
    )
    assert result.exit_code == 2

    factory = logging.getLogRecordFactory()
    assert getattr(factory, "_fo_log_redact_installed", False) is True

    # stdlib redaction
    with caplog.at_level(logging.INFO):
        logging.getLogger("fo.wiring.stdlib").info("api_key=sk-LIVE-SECRET")
    assert "sk-LIVE-SECRET" not in caplog.text
    assert "[REDACTED]" in caplog.text

    # loguru redaction
    captured: list[str] = []
    sink_id = loguru_logger.add(captured.append, format="{message}")
    try:
        loguru_logger.info("password=hunter2secret")
    finally:
        loguru_logger.remove(sink_id)
    joined = "".join(captured)
    assert "hunter2secret" not in joined
    assert "[REDACTED]" in joined


def test_api_configure_logging_installs_redaction(
    restore_logging: None, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """API logging setup installs the redaction filter."""
    import file_organizer.api.main as apimain

    calls: list[bool] = []
    monkeypatch.setattr(
        "file_organizer.utils.log_redact.install_on_root",
        lambda *a, **k: calls.append(True),
    )
    # Avoid disturbing global loguru sinks / writing real log dirs.
    monkeypatch.setattr(loguru_logger, "remove", lambda *a, **k: None)
    monkeypatch.setattr(loguru_logger, "add", lambda *a, **k: 0)
    monkeypatch.setattr("file_organizer.config.path_manager.get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(apimain, "_LOGGING_CONFIGURED", False)

    apimain.configure_logging(apimain.load_settings())

    assert calls == [True]


def test_desktop_launch_installs_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desktop launch installs the redaction filter before opening the window."""
    import file_organizer.desktop.app as desk

    calls: list[bool] = []
    monkeypatch.setattr(
        "file_organizer.utils.log_redact.install_on_root",
        lambda *a, **k: calls.append(True),
    )
    # Force the webview import inside launch() to fail so we don't start a
    # server; install_on_root runs first, before the import.
    monkeypatch.setitem(sys.modules, "webview", None)

    with pytest.raises(ImportError, match="pywebview is required for the desktop UI"):
        desk.launch()

    assert calls == [True]
