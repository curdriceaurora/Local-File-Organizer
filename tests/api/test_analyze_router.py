"""Tests for the analyze API router."""

from __future__ import annotations
import pytest

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.analyze import router


def _build_app() -> tuple[FastAPI, TestClient]:
    """Create a minimal FastAPI app with the analyze router.

    Note: The analyze router does NOT use get_current_active_user dependency,
    so we only override get_settings.
    """
    settings = ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=["/tmp"],
        auth_jwt_secret="test-secret",
        rate_limit_enabled=False,
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


# ---------------------------------------------------------------------------
# analyze endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyze:
    """Tests for POST /api/v1/analyze."""

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_text_content(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "technical",  # generate_category call
            "A technical document about programming.",  # generate_description call
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "Python is a programming language used for web development."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "technical"
        assert "programming" in body["description"].lower()
        assert 0.0 < body["confidence"] <= 1.0

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_file_upload(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "business",
            "A business document about quarterly earnings.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            files={"file": ("report.txt", b"Quarterly earnings report Q1 2025", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "business"

    def test_analyze_no_input(self) -> None:
        _, client = _build_app()

        resp = client.post("/api/v1/analyze")
        assert resp.status_code == 400

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_empty_content(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "general",
            "Document content analysis",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": ""},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "general"

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_long_content_truncated(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "technical",
            "A technical document.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        # Content longer than MAX_CONTENT_LENGTH (2000)
        long_content = "x" * 5000
        resp = client.post(
            "/api/v1/analyze",
            params={"content": long_content},
        )
        assert resp.status_code == 200

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_import_error(self, mock_get_model) -> None:
        mock_get_model.side_effect = ImportError("ollama not installed")
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "some text"},
        )
        assert resp.status_code == 503

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_generic_error_caught_by_service(self, mock_get_model) -> None:
        """When model.generate raises, the service layer catches it and returns defaults."""
        mock_model = MagicMock()
        mock_model.generate.side_effect = RuntimeError("model crashed")
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "some text"},
        )
        # generate_category and generate_description catch Exception internally
        # and return fallback values, so the endpoint returns 200
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "general"
        assert body["description"] == "Document content analysis"

    @patch("file_organizer.api.routers.analyze.calculate_confidence")
    @patch("file_organizer.api.routers.analyze.generate_description")
    @patch("file_organizer.api.routers.analyze.generate_category")
    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_unhandled_exception_returns_500(
        self, mock_get_model, mock_cat, mock_desc, mock_conf
    ) -> None:
        """An unexpected error in the endpoint logic itself returns 500."""
        mock_get_model.return_value = MagicMock()
        mock_cat.return_value = "technical"
        mock_desc.return_value = "A description"
        mock_conf.side_effect = TypeError("unexpected error")
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "some text"},
        )
        assert resp.status_code == 500

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_invalid_category_fallback(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "not_a_valid_category garbage text",  # invalid category
            "A document about miscellaneous topics.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "some random text about various things"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should fall back to "general" since the model returned invalid category
        assert body["category"] == "general"

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_category_in_middle_of_response(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "I think this is technical in nature",  # "technical" found in middle
            "A document about coding best practices.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "def hello():\n    print('hello world')"},
        )
        assert resp.status_code == 200
        assert resp.json()["category"] == "technical"

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_confidence_short_content(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "general",
            "Brief note.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "hi"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Short content should have lower confidence
        assert body["confidence"] <= 0.5

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_confidence_long_content(self, mock_get_model) -> None:
        mock_model = MagicMock()
        long_desc = "A comprehensive technical analysis " * 5
        mock_model.generate.side_effect = [
            "technical",
            long_desc,
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "x " * 600},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Long content + long description should have higher confidence
        assert body["confidence"] >= 0.7

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_description_prefix_stripped(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "education",
            "Description: A tutorial on machine learning basics.",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "Machine learning tutorial chapter 1"},
        )
        assert resp.status_code == 200
        desc = resp.json()["description"]
        assert not desc.lower().startswith("description:")

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_empty_description_fallback(self, mock_get_model) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "general",
            "",  # Empty description
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "test content"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Document content analysis"

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_category_error_falls_back(self, mock_get_model) -> None:
        """When generate_category errors, it falls back to 'general'."""
        mock_model = MagicMock()
        # First call (category) raises, second call (description) succeeds
        mock_model.generate.side_effect = [
            Exception("model error"),
            "Some description",
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "test"},
        )
        # generate_category catches Exception and returns "general"
        # but generate_description may also fail since generate was already called
        # Actually the side_effect list will provide one value per call
        assert resp.status_code == 200
        assert resp.json()["category"] == "general"

    @patch("file_organizer.api.routers.analyze.get_text_model")
    def test_analyze_description_error_falls_back(self, mock_get_model) -> None:
        """When generate_description errors, it falls back to default."""
        mock_model = MagicMock()
        mock_model.generate.side_effect = [
            "technical",
            Exception("description error"),
        ]
        mock_get_model.return_value = mock_model
        _, client = _build_app()

        resp = client.post(
            "/api/v1/analyze",
            params={"content": "Python programming tutorial"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "technical"
        assert body["description"] == "Document content analysis"


# ---------------------------------------------------------------------------
# get_text_model helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetTextModel:
    """Tests for the get_text_model singleton."""

    @patch("file_organizer.api.routers.analyze.TextModel")
    def test_get_text_model_initializes_once(self, mock_text_model_cls) -> None:
        import file_organizer.api.routers.analyze as analyze_mod

        # Reset the global to None
        original = analyze_mod._text_model
        analyze_mod._text_model = None

        mock_instance = MagicMock()
        mock_text_model_cls.return_value = mock_instance
        mock_text_model_cls.get_default_config.return_value = MagicMock()

        try:
            model1 = analyze_mod.get_text_model()
            model2 = analyze_mod.get_text_model()
            # Should only initialize once
            mock_instance.initialize.assert_called_once()
            assert model1 is model2
        finally:
            analyze_mod._text_model = original
