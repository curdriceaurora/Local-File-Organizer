"""Integration tests for daemon/service.py and cli/autotag.py.

Covers:
- DaemonConfig: defaults, custom params
- DaemonService: constructor, is_running/uptime/files_processed/scheduler properties,
  on_start/on_stop callbacks, start_background + stop lifecycle, restart,
  double-start raises RuntimeError, pid_file written/removed, stop when not running
- setup_autotag_parser: argument structure, subcommands
- handle_autotag_command: dispatches to subcommands, no subcommand exits 1
- handle_suggest: missing file stderr, json output, text output (mocked service)
- handle_apply: missing file exits 1, success (mocked service)
- handle_popular: empty data, with data (mocked service)
- handle_recent: empty data, with data (mocked service)
- handle_analyze: missing file exits 1, with keywords, with entities (mocked service)
- handle_batch: not a directory, no files, with files (mocked service)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# DaemonConfig
# ---------------------------------------------------------------------------


class TestDaemonConfig:
    def test_default_values(self) -> None:
        from file_organizer.daemon.config import DaemonConfig

        cfg = DaemonConfig()
        assert cfg.watch_directories == []
        assert cfg.output_directory == Path("organized_files")
        assert cfg.pid_file is None
        assert cfg.dry_run is True

    def test_custom_pid_file(self, tmp_path: Path) -> None:
        from file_organizer.daemon.config import DaemonConfig

        cfg = DaemonConfig(pid_file=tmp_path / "daemon.pid")
        assert cfg.pid_file == tmp_path / "daemon.pid"

    def test_custom_watch_directories(self, tmp_path: Path) -> None:
        from file_organizer.daemon.config import DaemonConfig

        cfg = DaemonConfig(watch_directories=[tmp_path / "a", tmp_path / "b"])
        assert len(cfg.watch_directories) == 2


# ---------------------------------------------------------------------------
# DaemonService properties (no start)
# ---------------------------------------------------------------------------


class TestDaemonServiceProperties:
    def test_is_running_false_before_start(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        assert daemon.is_running is False

    def test_uptime_seconds_zero_before_start(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        assert daemon.uptime_seconds == 0.0

    def test_files_processed_zero_initially(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        assert daemon.files_processed == 0

    def test_scheduler_property_accessible(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        assert daemon.scheduler is not None

    def test_on_start_registers_callback(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        callback = MagicMock()
        daemon.on_start(callback)
        assert daemon._on_start_callback is callback

    def test_on_stop_registers_callback(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        callback = MagicMock()
        daemon.on_stop(callback)
        assert daemon._on_stop_callback is callback


# ---------------------------------------------------------------------------
# DaemonService lifecycle (start_background + stop)
# ---------------------------------------------------------------------------


class TestDaemonServiceLifecycle:
    def test_start_background_marks_running(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_stop_marks_not_running(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        daemon.stop()
        assert daemon.is_running is False

    def test_uptime_seconds_positive_while_running(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        try:
            assert daemon.uptime_seconds >= 0.0
        finally:
            daemon.stop()

    def test_uptime_zero_after_stop(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        daemon.stop()
        assert daemon.uptime_seconds == 0.0

    def test_pid_file_written_and_removed(self, tmp_path: Path) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        pid_file = tmp_path / "daemon.pid"
        daemon = DaemonService(DaemonConfig(pid_file=pid_file))
        daemon.start_background()
        try:
            assert pid_file.exists()
        finally:
            daemon.stop()
        assert not pid_file.exists()

    def test_double_start_raises_runtime_error(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        try:
            with pytest.raises(RuntimeError):
                daemon.start_background()
        finally:
            daemon.stop()

    def test_stop_when_not_running_is_safe(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.stop()  # should not raise

    def test_on_start_callback_called(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        callback = MagicMock()
        daemon.on_start(callback)
        daemon.start_background()
        try:
            callback.assert_called_once()
        finally:
            daemon.stop()

    def test_on_stop_callback_called(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        callback = MagicMock()
        daemon.on_stop(callback)
        daemon.start_background()
        daemon.stop()
        callback.assert_called_once()

    def test_restart_cycles_the_daemon(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.start_background()
        daemon.restart()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_failing_on_start_callback_doesnt_crash(self) -> None:
        from file_organizer.daemon.config import DaemonConfig
        from file_organizer.daemon.service import DaemonService

        daemon = DaemonService(DaemonConfig())
        daemon.on_start(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        daemon.start_background()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()


# ---------------------------------------------------------------------------
# setup_autotag_parser
# ---------------------------------------------------------------------------


def _make_autotag_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("other")
    from file_organizer.cli.autotag import setup_autotag_parser

    setup_autotag_parser(sub)
    return parser


class TestSetupAutotagParser:
    def test_suggest_subcommand_parses(self, tmp_path: Path) -> None:
        parser = _make_autotag_parser()
        f = tmp_path / "doc.txt"
        f.write_text("x")
        args = parser.parse_args(["autotag", "suggest", str(f)])
        assert args.autotag_command == "suggest"
        assert str(f) in args.files

    def test_suggest_json_flag(self, tmp_path: Path) -> None:
        parser = _make_autotag_parser()
        f = tmp_path / "doc.txt"
        f.write_text("x")
        args = parser.parse_args(["autotag", "suggest", "--json", str(f)])
        assert args.json is True

    def test_apply_subcommand_parses(self, tmp_path: Path) -> None:
        parser = _make_autotag_parser()
        args = parser.parse_args(["autotag", "apply", "some_file.txt", "tag1", "tag2"])
        assert args.autotag_command == "apply"
        assert args.tags == ["tag1", "tag2"]

    def test_popular_subcommand_has_limit(self) -> None:
        parser = _make_autotag_parser()
        args = parser.parse_args(["autotag", "popular", "--limit", "5"])
        assert args.limit == 5

    def test_recent_subcommand_has_days(self) -> None:
        parser = _make_autotag_parser()
        args = parser.parse_args(["autotag", "recent", "--days", "7"])
        assert args.days == 7

    def test_batch_subcommand_has_directory(self, tmp_path: Path) -> None:
        parser = _make_autotag_parser()
        args = parser.parse_args(["autotag", "batch", str(tmp_path)])
        assert args.autotag_command == "batch"

    def test_analyze_subcommand_has_keywords(self, tmp_path: Path) -> None:
        parser = _make_autotag_parser()
        args = parser.parse_args(["autotag", "analyze", "--keywords", "doc.txt"])
        assert args.keywords is True


# ---------------------------------------------------------------------------
# handle_autotag_command dispatch
# ---------------------------------------------------------------------------


class TestHandleAutotagCommand:
    def test_no_subcommand_exits_1(self, capsys) -> None:
        from file_organizer.cli.autotag import handle_autotag_command

        args = SimpleNamespace(autotag_command=None)
        with pytest.raises(SystemExit) as exc:
            handle_autotag_command(args)
        assert exc.value.code == 1

    def test_dispatches_to_suggest(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag import handle_autotag_command

        f = tmp_path / "f.txt"
        f.write_text("x")
        args = SimpleNamespace(
            autotag_command="suggest",
            files=[str(f)],
            existing_tags=None,
            top_n=5,
            min_confidence=0.0,
            json=False,
        )
        with patch("file_organizer.cli.autotag.AutoTaggingService") as MockSvc:
            svc = MockSvc.return_value
            rec = MagicMock()
            rec.suggestions = []
            svc.suggest_tags.return_value = rec
            handle_autotag_command(args)
        svc.suggest_tags.assert_called_once()


# ---------------------------------------------------------------------------
# handle_suggest
# ---------------------------------------------------------------------------


class TestHandleSuggest:
    def _make_args(
        self,
        files: list[str],
        *,
        existing_tags=None,
        top_n: int = 5,
        min_confidence: float = 0.0,
        json_out: bool = False,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            files=files,
            existing_tags=existing_tags,
            top_n=top_n,
            min_confidence=min_confidence,
            json=json_out,
        )

    def test_missing_file_writes_to_stderr(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_suggest

        svc = MagicMock()
        args = self._make_args([str(tmp_path / "ghost.txt")])
        handle_suggest(svc, args)
        err = capsys.readouterr().err
        assert "not found" in err.lower() or "Error" in err

    def test_existing_file_json_output(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_suggest

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        suggestion = MagicMock()
        suggestion.confidence = 80.0
        suggestion.to_dict.return_value = {"tag": "finance", "confidence": 80.0}
        rec = MagicMock()
        rec.suggestions = [suggestion]
        svc.suggest_tags.return_value = rec

        args = self._make_args([str(f)], json_out=True)
        handle_suggest(svc, args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_text_output_when_no_json(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_suggest

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        suggestion = MagicMock()
        suggestion.confidence = 80.0
        suggestion.tag = "finance"
        suggestion.source = "test"
        suggestion.reasoning = "reason"
        rec = MagicMock()
        rec.suggestions = [suggestion]
        svc.suggest_tags.return_value = rec

        args = self._make_args([str(f)])
        handle_suggest(svc, args)
        out = capsys.readouterr().out
        assert "finance" in out

    def test_no_suggestions_message(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_suggest

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        rec = MagicMock()
        rec.suggestions = []
        svc.suggest_tags.return_value = rec

        args = self._make_args([str(f)], min_confidence=100.0)
        handle_suggest(svc, args)
        out = capsys.readouterr().out
        assert "No suggestions" in out


# ---------------------------------------------------------------------------
# handle_apply
# ---------------------------------------------------------------------------


class TestHandleApply:
    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag import handle_apply

        svc = MagicMock()
        args = SimpleNamespace(file=str(tmp_path / "ghost.txt"), tags=["t1"])
        with pytest.raises(SystemExit) as exc:
            handle_apply(svc, args)
        assert exc.value.code == 1

    def test_existing_file_records_tags(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_apply

        f = tmp_path / "doc.txt"
        f.write_text("x")
        svc = MagicMock()
        args = SimpleNamespace(file=str(f), tags=["tag1", "tag2"])
        handle_apply(svc, args)
        svc.record_tag_usage.assert_called_once_with(f.resolve(), ["tag1", "tag2"])
        out = capsys.readouterr().out
        assert "tag1" in out


# ---------------------------------------------------------------------------
# handle_popular
# ---------------------------------------------------------------------------


class TestHandlePopular:
    def test_empty_popular_prints_no_data_message(self, capsys) -> None:
        from file_organizer.cli.autotag import handle_popular

        svc = MagicMock()
        svc.get_popular_tags.return_value = []
        args = SimpleNamespace(limit=20)
        handle_popular(svc, args)
        out = capsys.readouterr().out
        assert "No tag usage" in out

    def test_popular_with_data_prints_tags(self, capsys) -> None:
        from file_organizer.cli.autotag import handle_popular

        svc = MagicMock()
        svc.get_popular_tags.return_value = [("finance", 5), ("work", 3)]
        args = SimpleNamespace(limit=5)
        handle_popular(svc, args)
        out = capsys.readouterr().out
        assert "finance" in out
        assert "work" in out


# ---------------------------------------------------------------------------
# handle_recent
# ---------------------------------------------------------------------------


class TestHandleRecent:
    def test_empty_recent_prints_message(self, capsys) -> None:
        from file_organizer.cli.autotag import handle_recent

        svc = MagicMock()
        svc.get_recent_tags.return_value = []
        args = SimpleNamespace(days=30, limit=20)
        handle_recent(svc, args)
        out = capsys.readouterr().out
        assert "No tags" in out

    def test_recent_with_data_prints_tags(self, capsys) -> None:
        from file_organizer.cli.autotag import handle_recent

        svc = MagicMock()
        svc.get_recent_tags.return_value = ["finance", "work"]
        args = SimpleNamespace(days=7, limit=10)
        handle_recent(svc, args)
        out = capsys.readouterr().out
        assert "finance" in out


# ---------------------------------------------------------------------------
# handle_analyze
# ---------------------------------------------------------------------------


class TestHandleAnalyze:
    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag import handle_analyze

        svc = MagicMock()
        args = SimpleNamespace(file=str(tmp_path / "ghost.txt"), keywords=False, entities=False)
        with pytest.raises(SystemExit) as exc:
            handle_analyze(svc, args)
        assert exc.value.code == 1

    def test_analyze_prints_tags(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_analyze

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        svc.content_analyzer.analyze_file.return_value = ["finance", "report"]
        args = SimpleNamespace(file=str(f), keywords=False, entities=False)
        handle_analyze(svc, args)
        out = capsys.readouterr().out
        assert "finance" in out

    def test_analyze_with_keywords(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_analyze

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        svc.content_analyzer.analyze_file.return_value = []
        svc.content_analyzer.extract_keywords.return_value = [("budget", 0.9), ("plan", 0.7)]
        args = SimpleNamespace(file=str(f), keywords=True, entities=False)
        handle_analyze(svc, args)
        out = capsys.readouterr().out
        assert "budget" in out

    def test_analyze_with_entities(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_analyze

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        svc.content_analyzer.analyze_file.return_value = []
        svc.content_analyzer.extract_entities.return_value = ["Acme Corp", "2025"]
        args = SimpleNamespace(file=str(f), keywords=False, entities=True)
        handle_analyze(svc, args)
        out = capsys.readouterr().out
        assert "Acme Corp" in out


# ---------------------------------------------------------------------------
# handle_batch
# ---------------------------------------------------------------------------


class TestHandleBatch:
    def test_not_a_directory_exits_1(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag import handle_batch

        svc = MagicMock()
        args = SimpleNamespace(
            directory=str(tmp_path / "ghost_dir"),
            pattern="*",
            recursive=False,
            output=None,
        )
        with pytest.raises(SystemExit) as exc:
            handle_batch(svc, args)
        assert exc.value.code == 1

    def test_no_files_found_prints_message(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_batch

        svc = MagicMock()
        args = SimpleNamespace(
            directory=str(tmp_path),
            pattern="*.nonexistent",
            recursive=False,
            output=None,
        )
        handle_batch(svc, args)
        out = capsys.readouterr().out
        assert "No files" in out

    def test_batch_with_files_prints_json(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_batch

        f = tmp_path / "doc.txt"
        f.write_text("content")
        svc = MagicMock()
        rec = MagicMock()
        rec.suggestions = []
        svc.recommender.batch_recommend.return_value = {f: rec}
        args = SimpleNamespace(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=False,
            output=None,
        )
        handle_batch(svc, args)
        out = capsys.readouterr().out
        # Output starts with "Processing N files...\n" then JSON
        json_part = out[out.index("[") :]
        data = json.loads(json_part)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_batch_saves_to_output_file(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_batch

        f = tmp_path / "doc.txt"
        f.write_text("content")
        out_file = tmp_path / "results.json"
        svc = MagicMock()
        rec = MagicMock()
        rec.suggestions = []
        svc.recommender.batch_recommend.return_value = {f: rec}
        args = SimpleNamespace(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=False,
            output=str(out_file),
        )
        handle_batch(svc, args)
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert isinstance(data, list)

    def test_batch_recursive_flag(self, tmp_path: Path, capsys) -> None:
        from file_organizer.cli.autotag import handle_batch

        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "nested.txt"
        f.write_text("content")
        svc = MagicMock()
        rec = MagicMock()
        rec.suggestions = []
        svc.recommender.batch_recommend.return_value = {f: rec}
        args = SimpleNamespace(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=True,
            output=None,
        )
        handle_batch(svc, args)
        svc.recommender.batch_recommend.assert_called_once()
