"""Tests for LazyModelLoader - proxy pattern with deferred loading."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from file_organizer.optimization.lazy_loader import LazyModelLoader


def _make_config(name: str = "test-model") -> ModelConfig:
    """Create a test ModelConfig."""
    return ModelConfig(name=name, model_type=ModelType.TEXT, framework="test")


def _make_mock_model(name: str = "test-model") -> MagicMock:
    """Create a mock BaseModel."""
    mock = MagicMock(spec=BaseModel)
    mock.config = _make_config(name)
    mock.cleanup = MagicMock()
    mock.initialize = MagicMock()
    return mock


@pytest.mark.unit
class TestLazyModelLoaderInit:
    """Tests for LazyModelLoader initialization."""

    def test_not_loaded_initially(self) -> None:
        """Test that the model is not loaded on construction."""
        config = _make_config()
        lazy = LazyModelLoader(config, loader=lambda c: _make_mock_model())
        assert lazy.is_loaded is False

    def test_config_accessible(self) -> None:
        """Test that config is accessible without loading."""
        config = _make_config("my-model")
        lazy = LazyModelLoader(config, loader=lambda c: _make_mock_model())
        assert lazy.config is config
        assert lazy.config.name == "my-model"
        assert lazy.is_loaded is False

    def test_repr_not_loaded(self) -> None:
        """Test repr when model is not loaded."""
        config = _make_config("my-model")
        lazy = LazyModelLoader(config, loader=lambda c: _make_mock_model())
        repr_str = repr(lazy)
        assert "my-model" in repr_str
        assert "not loaded" in repr_str


@pytest.mark.unit
class TestLazyModelLoaderLoading:
    """Tests for the model loading behavior."""

    def test_loads_on_first_access(self) -> None:
        """Test that the model is loaded on first property access."""
        config = _make_config()
        mock_model = _make_mock_model()
        loader = MagicMock(return_value=mock_model)

        lazy = LazyModelLoader(config, loader=loader)
        model = lazy.model

        assert model is mock_model
        assert lazy.is_loaded is True
        loader.assert_called_once_with(config)

    def test_second_access_does_not_reload(self) -> None:
        """Test that subsequent accesses return the same model without reloading."""
        config = _make_config()
        mock_model = _make_mock_model()
        loader = MagicMock(return_value=mock_model)

        lazy = LazyModelLoader(config, loader=loader)
        model1 = lazy.model
        model2 = lazy.model

        assert model1 is model2
        loader.assert_called_once()

    def test_loader_receives_config(self) -> None:
        """Test that the loader callable receives the ModelConfig."""
        config = _make_config("special-model")
        loader = MagicMock(return_value=_make_mock_model())

        lazy = LazyModelLoader(config, loader=loader)
        lazy.model  # noqa: B018 - trigger loading

        loader.assert_called_once_with(config)

    def test_loading_failure_raises_runtime_error(self) -> None:
        """Test that loading failure wraps exception in RuntimeError."""
        config = _make_config()
        loader = MagicMock(side_effect=ConnectionError("cannot connect"))

        lazy = LazyModelLoader(config, loader=loader)

        with pytest.raises(RuntimeError, match="Failed to load model"):
            lazy.model  # noqa: B018

    def test_loading_failure_preserves_not_loaded_state(self) -> None:
        """Test that a failed load keeps is_loaded as False."""
        config = _make_config()
        loader = MagicMock(side_effect=ValueError("bad config"))

        lazy = LazyModelLoader(config, loader=loader)

        with pytest.raises(RuntimeError):
            lazy.model  # noqa: B018

        assert lazy.is_loaded is False

    def test_repr_after_loading(self) -> None:
        """Test repr when model is loaded."""
        config = _make_config("my-model")
        lazy = LazyModelLoader(config, loader=lambda c: _make_mock_model())
        lazy.model  # noqa: B018 - trigger loading

        repr_str = repr(lazy)
        assert "my-model" in repr_str
        assert "loaded" in repr_str
        assert "not loaded" not in repr_str


@pytest.mark.unit
class TestLazyModelLoaderUnload:
    """Tests for unloading models."""

    def test_unload_loaded_model(self) -> None:
        """Test unloading a loaded model calls cleanup."""
        config = _make_config()
        mock_model = _make_mock_model()
        lazy = LazyModelLoader(config, loader=lambda c: mock_model)

        lazy.model  # noqa: B018 - trigger loading
        assert lazy.is_loaded is True

        lazy.unload()

        assert lazy.is_loaded is False
        mock_model.cleanup.assert_called_once()

    def test_unload_not_loaded_model(self) -> None:
        """Test unloading when model was never loaded is a no-op."""
        config = _make_config()
        lazy = LazyModelLoader(config, loader=lambda c: _make_mock_model())

        lazy.unload()  # Should not raise
        assert lazy.is_loaded is False

    def test_reload_after_unload(self) -> None:
        """Test that the model can be re-loaded after unload."""
        config = _make_config()
        load_count = 0

        def counting_loader(cfg: ModelConfig) -> MagicMock:
            nonlocal load_count
            load_count += 1
            return _make_mock_model()

        lazy = LazyModelLoader(config, loader=counting_loader)

        # First load
        lazy.model  # noqa: B018
        assert load_count == 1

        # Unload
        lazy.unload()
        assert lazy.is_loaded is False

        # Re-load
        lazy.model  # noqa: B018
        assert load_count == 2
        assert lazy.is_loaded is True

    def test_unload_cleanup_error_handled(self) -> None:
        """Test that cleanup errors during unload are handled gracefully."""
        config = _make_config()
        mock_model = _make_mock_model()
        mock_model.cleanup.side_effect = RuntimeError("cleanup failed")

        lazy = LazyModelLoader(config, loader=lambda c: mock_model)
        lazy.model  # noqa: B018 - trigger loading

        # Should not raise even though cleanup fails
        lazy.unload()
        assert lazy.is_loaded is False


@pytest.mark.unit
class TestLazyModelLoaderThreadSafety:
    """Tests for thread-safe loading."""

    def test_concurrent_first_access(self) -> None:
        """Test that concurrent first access only loads once."""
        config = _make_config()
        load_count = 0
        lock = threading.Lock()

        def slow_loader(cfg: ModelConfig) -> MagicMock:
            nonlocal load_count
            import time

            time.sleep(0.05)
            with lock:
                load_count += 1
            return _make_mock_model()

        lazy = LazyModelLoader(config, loader=slow_loader)
        barrier = threading.Barrier(3)
        results: list[BaseModel] = []
        results_lock = threading.Lock()

        def worker() -> None:
            barrier.wait(timeout=5)
            model = lazy.model
            with results_lock:
                results.append(model)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Only one load should have occurred
        assert load_count == 1
        # All threads should get the same model
        assert len(results) == 3
        assert all(r is results[0] for r in results)


@pytest.mark.unit
class TestLazyModelLoaderDefaultLoader:
    """Tests for framework-based default loader routing."""

    def test_default_loader_routes_mlx_to_provider_factory(self) -> None:
        cfg = ModelConfig(name="mlx-lm", model_type=ModelType.TEXT, framework="mlx", provider="mlx")
        mock_model = _make_mock_model("mlx-lm")
        mock_model.initialize = MagicMock()

        with patch(
            "file_organizer.models.provider_factory.get_text_model",
            return_value=mock_model,
        ) as mock_get_text_model:
            model = LazyModelLoader._default_loader(cfg)

        mock_get_text_model.assert_called_once_with(cfg)
        mock_model.initialize.assert_called_once_with()
        assert model is mock_model
