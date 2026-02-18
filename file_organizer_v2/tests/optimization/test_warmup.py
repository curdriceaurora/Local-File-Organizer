"""Tests for ModelWarmup - background pre-loading of models."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.optimization.model_cache import ModelCache
from file_organizer.optimization.warmup import ModelWarmup, WarmupResult


def _make_mock_model(name: str = "test-model") -> MagicMock:
    """Create a mock BaseModel instance."""
    mock = MagicMock(spec=BaseModel)
    mock.config = ModelConfig(name=name, model_type=ModelType.TEXT)
    mock.cleanup = MagicMock()
    return mock


class TestWarmupResult:
    """Tests for the WarmupResult dataclass."""

    def test_empty_result(self) -> None:
        """Test default empty WarmupResult."""
        result = WarmupResult()
        assert result.loaded == []
        assert result.failed == []
        assert result.duration_ms == 0.0
        assert result.total_requested == 0
        assert result.success_rate == 1.0

    def test_all_loaded(self) -> None:
        """Test WarmupResult with all models loaded."""
        result = WarmupResult(
            loaded=["model-a", "model-b"],
            failed=[],
            duration_ms=150.0,
        )
        assert result.total_requested == 2
        assert result.success_rate == 1.0

    def test_partial_failure(self) -> None:
        """Test WarmupResult with some failures."""
        result = WarmupResult(
            loaded=["model-a"],
            failed=[("model-b", "connection error")],
            duration_ms=200.0,
        )
        assert result.total_requested == 2
        assert result.success_rate == 0.5

    def test_all_failed(self) -> None:
        """Test WarmupResult with all failures."""
        result = WarmupResult(
            loaded=[],
            failed=[("model-a", "error"), ("model-b", "error")],
            duration_ms=100.0,
        )
        assert result.total_requested == 2
        assert result.success_rate == 0.0


class TestModelWarmupInit:
    """Tests for ModelWarmup initialization."""

    def test_valid_init(self) -> None:
        """Test valid initialization."""
        cache = ModelCache(max_models=5)
        warmup = ModelWarmup(
            cache=cache,
            loader_factory=lambda name: lambda: _make_mock_model(name),
            max_workers=2,
        )
        assert warmup is not None

    def test_invalid_max_workers(self) -> None:
        """Test that max_workers < 1 raises ValueError."""
        cache = ModelCache(max_models=5)
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            ModelWarmup(
                cache=cache,
                loader_factory=lambda name: lambda: _make_mock_model(name),
                max_workers=0,
            )


class TestModelWarmupSync:
    """Tests for synchronous warmup."""

    def test_warmup_empty_list(self) -> None:
        """Test warming up an empty list of models."""
        cache = ModelCache(max_models=5)
        warmup = ModelWarmup(
            cache=cache,
            loader_factory=lambda name: lambda: _make_mock_model(name),
        )

        result = warmup.warmup([])
        assert result.total_requested == 0
        assert result.duration_ms == 0.0

    def test_warmup_single_model(self) -> None:
        """Test warming up a single model."""
        cache = ModelCache(max_models=5)
        models: dict[str, MagicMock] = {}

        def loader_factory(name: str):
            def loader():
                model = _make_mock_model(name)
                models[name] = model
                return model

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        result = warmup.warmup(["model-a"])

        assert "model-a" in result.loaded
        assert len(result.failed) == 0
        assert result.duration_ms > 0
        assert cache.contains("model-a")

    def test_warmup_multiple_models(self) -> None:
        """Test warming up multiple models."""
        cache = ModelCache(max_models=5)

        def loader_factory(name: str):
            return lambda: _make_mock_model(name)

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory, max_workers=3)
        result = warmup.warmup(["model-a", "model-b", "model-c"])

        assert len(result.loaded) == 3
        assert len(result.failed) == 0
        assert cache.size == 3

    def test_warmup_skips_cached_models(self) -> None:
        """Test that already-cached models are skipped during warmup."""
        cache = ModelCache(max_models=5)

        # Pre-load model-a
        cache.get_or_load("model-a", lambda: _make_mock_model("a"))

        load_count = 0

        def loader_factory(name: str):
            def loader():
                nonlocal load_count
                load_count += 1
                return _make_mock_model(name)

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        result = warmup.warmup(["model-a", "model-b"])

        assert "model-a" in result.loaded
        assert "model-b" in result.loaded
        assert load_count == 1  # Only model-b was actually loaded

    def test_warmup_deduplicates_names(self) -> None:
        """Test that duplicate model names are deduplicated."""
        cache = ModelCache(max_models=5)
        load_count = 0

        def loader_factory(name: str):
            def loader():
                nonlocal load_count
                load_count += 1
                return _make_mock_model(name)

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        result = warmup.warmup(["model-a", "model-a", "model-a"])

        assert result.loaded.count("model-a") == 1
        assert load_count == 1

    def test_warmup_handles_loader_failure(self) -> None:
        """Test that loader failures are captured in the result."""
        cache = ModelCache(max_models=5)

        def loader_factory(name: str):
            def loader():
                if name == "bad-model":
                    raise ConnectionError("cannot connect")
                return _make_mock_model(name)

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        result = warmup.warmup(["good-model", "bad-model"])

        assert "good-model" in result.loaded
        assert len(result.failed) == 1
        assert result.failed[0][0] == "bad-model"
        assert "cannot connect" in result.failed[0][1]

    def test_warmup_duration_tracked(self) -> None:
        """Test that duration is properly tracked."""
        cache = ModelCache(max_models=5)

        def loader_factory(name: str):
            def loader():
                time.sleep(0.02)
                return _make_mock_model(name)

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        result = warmup.warmup(["model-a"])

        assert result.duration_ms >= 15  # Allow some margin


class TestModelWarmupAsync:
    """Tests for asynchronous warmup."""

    def test_warmup_async_returns_future(self) -> None:
        """Test that warmup_async returns a Future."""
        cache = ModelCache(max_models=5)

        def loader_factory(name: str):
            return lambda: _make_mock_model(name)

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        future = warmup.warmup_async(["model-a"])

        result = future.result(timeout=10)
        assert isinstance(result, WarmupResult)
        assert "model-a" in result.loaded

    def test_warmup_async_runs_in_background(self) -> None:
        """Test that warmup_async returns immediately."""
        cache = ModelCache(max_models=5)

        def loader_factory(name: str):
            def loader():
                time.sleep(0.1)
                return _make_mock_model(name)

            return loader

        warmup = ModelWarmup(cache=cache, loader_factory=loader_factory)
        start = time.monotonic()
        future = warmup.warmup_async(["model-a"])
        call_duration = (time.monotonic() - start) * 1000

        # The call should return almost immediately
        assert call_duration < 50  # ms

        # But the result takes longer
        result = future.result(timeout=10)
        assert "model-a" in result.loaded
