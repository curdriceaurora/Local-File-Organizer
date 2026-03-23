"""Integration tests for services/copilot and services/analytics modules.

Covers:
- CopilotEngine: chat (template fallback), chat (with mock LLM), session property,
  conversation property, reset, LLM failure fallback, intent parsing round-trip
- AnalyticsService: get_storage_stats, get_duplicate_stats (with and without dups),
  get_quality_metrics, calculate_time_saved, generate_dashboard
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# CopilotEngine
# ---------------------------------------------------------------------------


class TestCopilotEngine:
    def test_chat_template_fallback_returns_string(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        response = engine.chat("help")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_chat_unknown_intent_returns_string(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        response = engine.chat("xyzzy frobulate the quux")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_chat_status_intent(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        response = engine.chat("what is the current status")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_chat_with_llm_calls_text_model(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        mock_model = MagicMock()
        mock_model.generate.return_value = "I can organise your files."

        engine = CopilotEngine(text_model=mock_model)
        response = engine.chat("hello")
        assert isinstance(response, str)
        mock_model.generate.assert_called_once()
        call_prompt = mock_model.generate.call_args[0][0]
        assert isinstance(call_prompt, str)
        assert len(call_prompt) > 0

    def test_chat_llm_exception_falls_back_to_template(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        mock_model = MagicMock()
        mock_model.generate.side_effect = RuntimeError("Ollama unavailable")

        engine = CopilotEngine(text_model=mock_model)
        response = engine.chat("help me")
        mock_model.generate.assert_called()
        assert isinstance(response, str)
        assert len(response) > 0

    def test_session_property_tracks_messages(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        engine.chat("hello")
        engine.chat("help")
        assert len(engine.session.messages) == 4

    def test_conversation_property_accessible(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        engine.chat("hello")
        conv = engine.conversation
        assert conv is not None

    def test_reset_clears_conversation_and_session(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        engine.chat("first message")
        engine.chat("second message")
        assert len(engine.session.messages) == 4

        engine.reset()
        assert len(engine.session.messages) == 0
        assert engine.conversation.get_context_string() == ""

    def test_multiple_turns_builds_context(self) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine()
        engine.chat("Hello")
        engine.chat("What can you do?")
        engine.chat("Tell me more about your features")
        assert len(engine.session.messages) == 6

    def test_working_directory_stored_in_session(self, tmp_path: Path) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine(working_directory=str(tmp_path))
        assert engine.session.working_directory == str(tmp_path)

    def test_chat_with_organise_intent(self, tmp_path: Path) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine(working_directory=str(tmp_path))
        response = engine.chat(f"organise files in {tmp_path}")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_find_intent_without_retriever(self, tmp_path: Path) -> None:
        from file_organizer.services.copilot.engine import CopilotEngine

        engine = CopilotEngine(working_directory=str(tmp_path))
        response = engine.chat("find my tax documents")
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------


class TestAnalyticsService:
    def _make_service(self):
        from file_organizer.services.analytics.analytics_service import AnalyticsService

        return AnalyticsService()

    def _populate_dir(self, tmp_path: Path) -> None:
        (tmp_path / "report.pdf").write_bytes(b"PDF content " * 100)
        (tmp_path / "photo.jpg").write_bytes(b"JPEG data " * 200)
        (tmp_path / "notes.txt").write_text("some notes about things", encoding="utf-8")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "archive.zip").write_bytes(b"zip data " * 50)

    def test_get_storage_stats_returns_storage_stats(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import StorageStats

        self._populate_dir(tmp_path)
        svc = self._make_service()
        stats = svc.get_storage_stats(tmp_path)
        assert isinstance(stats, StorageStats)
        assert stats.file_count == 4
        assert stats.total_size > 0

    def test_get_storage_stats_empty_dir(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import StorageStats

        svc = self._make_service()
        stats = svc.get_storage_stats(tmp_path)
        assert isinstance(stats, StorageStats)
        assert stats.file_count == 0
        assert stats.total_size == 0

    def test_get_duplicate_stats_no_duplicates(self) -> None:
        from file_organizer.models.analytics import DuplicateStats

        svc = self._make_service()
        result = svc.get_duplicate_stats([], total_size=1000)
        assert isinstance(result, DuplicateStats)
        assert result.total_duplicates == 0
        assert result.duplicate_groups == 0
        assert result.space_wasted == 0

    def test_get_duplicate_stats_with_duplicates(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import DuplicateStats

        f1 = tmp_path / "file_a.txt"
        f2 = tmp_path / "file_b.txt"
        f1.write_text("same content", encoding="utf-8")
        f2.write_text("same content", encoding="utf-8")

        svc = self._make_service()
        groups = [{"files": [str(f1), str(f2)], "size": f1.stat().st_size}]
        result = svc.get_duplicate_stats(groups, total_size=f1.stat().st_size * 2)
        assert isinstance(result, DuplicateStats)
        assert result.total_duplicates == 1
        assert result.duplicate_groups == 1
        assert result.space_wasted > 0

    def test_generate_dashboard_returns_dashboard(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import AnalyticsDashboard

        self._populate_dir(tmp_path)
        svc = self._make_service()
        dashboard = svc.generate_dashboard(tmp_path)
        assert isinstance(dashboard, AnalyticsDashboard)
        assert dashboard.storage_stats is not None
        assert dashboard.quality_metrics is not None
        assert dashboard.generated_at is not None

    def test_generate_dashboard_duplicate_groups_propagated(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import AnalyticsDashboard

        f1 = tmp_path / "copy_a.txt"
        f2 = tmp_path / "copy_b.txt"
        f1.write_text("duplicate content", encoding="utf-8")
        f2.write_text("duplicate content", encoding="utf-8")

        svc = self._make_service()
        groups = [{"files": [str(f1), str(f2)], "size": f1.stat().st_size}]
        dashboard = svc.generate_dashboard(tmp_path, duplicate_groups=groups)
        assert isinstance(dashboard, AnalyticsDashboard)
        assert dashboard.duplicate_stats.duplicate_groups == 1

    def test_get_quality_metrics_returns_quality_metrics(self, tmp_path: Path) -> None:
        from file_organizer.models.analytics import QualityMetrics

        self._populate_dir(tmp_path)
        svc = self._make_service()
        metrics = svc.get_quality_metrics(tmp_path)
        assert isinstance(metrics, QualityMetrics)

    def test_calculate_time_saved_returns_time_savings(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        svc = self._make_service()
        result = svc.calculate_time_saved(total_files=100, duplicates_removed=10)
        assert isinstance(result, TimeSavings)
        assert result.estimated_time_saved_seconds == 3500
        assert result.total_operations == 100
