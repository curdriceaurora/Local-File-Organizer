"""Tests for domain-specific model registries and model hot-swap.

Validates that domain registries provide correct metadata, the
unified facade delegates properly, and model swapping works with
drain/rollback semantics.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from file_organizer.models.registry import (
    ModelInfo,
    get_all_models,
    get_audio_models,
    get_text_models,
    get_vision_models,
)

# ---------------------------------------------------------------------------
# Domain registry tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestTextRegistry:
    """Verify TextModelInfo has required domain fields."""

    def test_text_models_have_context_window(self) -> None:
        from file_organizer.models.text_registry import TEXT_MODELS

        for m in TEXT_MODELS:
            assert hasattr(m, "context_window"), f"{m.name} missing context_window"
            assert m.context_window > 0

    def test_text_models_have_max_tokens(self) -> None:
        from file_organizer.models.text_registry import TEXT_MODELS

        for m in TEXT_MODELS:
            assert hasattr(m, "max_tokens"), f"{m.name} missing max_tokens"
            assert m.max_tokens > 0

    def test_text_models_are_model_info_subclass(self) -> None:
        from file_organizer.models.text_registry import TEXT_MODELS, TextModelInfo

        for m in TEXT_MODELS:
            assert isinstance(m, ModelInfo)
            assert isinstance(m, TextModelInfo)
            assert m.model_type == "text"


@pytest.mark.ci
@pytest.mark.unit
class TestVisionRegistry:
    """Verify VisionModelInfo has required domain fields."""

    def test_vision_models_have_supported_formats(self) -> None:
        from file_organizer.models.vision_registry import VISION_MODELS

        for m in VISION_MODELS:
            assert hasattr(m, "supported_formats"), f"{m.name} missing supported_formats"
            assert len(m.supported_formats) > 0

    def test_vision_models_have_max_resolution(self) -> None:
        from file_organizer.models.vision_registry import VISION_MODELS

        for m in VISION_MODELS:
            assert hasattr(m, "max_resolution"), f"{m.name} missing max_resolution"
            assert m.max_resolution[0] > 0
            assert m.max_resolution[1] > 0

    def test_vision_models_are_model_info_subclass(self) -> None:
        from file_organizer.models.vision_registry import VISION_MODELS, VisionModelInfo

        for m in VISION_MODELS:
            assert isinstance(m, ModelInfo)
            assert isinstance(m, VisionModelInfo)
            assert m.model_type == "vision"


@pytest.mark.ci
@pytest.mark.unit
class TestAudioRegistry:
    """Verify AudioModelInfo has required domain fields."""

    def test_audio_models_have_supported_formats(self) -> None:
        from file_organizer.models.audio_registry import AUDIO_MODELS

        for m in AUDIO_MODELS:
            assert hasattr(m, "supported_formats"), f"{m.name} missing supported_formats"
            assert len(m.supported_formats) > 0

    def test_audio_models_have_max_duration(self) -> None:
        from file_organizer.models.audio_registry import AUDIO_MODELS

        for m in AUDIO_MODELS:
            assert hasattr(m, "max_duration_seconds"), f"{m.name} missing max_duration_seconds"
            assert m.max_duration_seconds > 0

    def test_audio_models_are_model_info_subclass(self) -> None:
        from file_organizer.models.audio_registry import AUDIO_MODELS, AudioModelInfo

        for m in AUDIO_MODELS:
            assert isinstance(m, ModelInfo)
            assert isinstance(m, AudioModelInfo)
            assert m.model_type == "audio"


# ---------------------------------------------------------------------------
# Unified facade tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestRegistryFacade:
    """Verify that the unified registry facade delegates correctly."""

    def test_get_text_models_returns_text_only(self) -> None:
        models = get_text_models()
        assert len(models) >= 2
        assert all(m.model_type == "text" for m in models)

    def test_get_vision_models_returns_vision_only(self) -> None:
        models = get_vision_models()
        assert len(models) >= 2
        assert all(m.model_type == "vision" for m in models)

    def test_get_audio_models_returns_audio_only(self) -> None:
        models = get_audio_models()
        assert len(models) >= 2
        assert all(m.model_type == "audio" for m in models)

    def test_get_all_models_includes_all_types(self) -> None:
        models = get_all_models()
        types = {m.model_type for m in models}
        assert "text" in types
        assert "vision" in types
        assert "audio" in types
        assert len(models) >= 6

    def test_available_models_backward_compat(self) -> None:
        from file_organizer.models.registry import AVAILABLE_MODELS

        assert len(AVAILABLE_MODELS) >= 6
        names = {m.name for m in AVAILABLE_MODELS}
        assert "qwen2.5:3b-instruct-q4_K_M" in names


# ---------------------------------------------------------------------------
# Model hot-swap tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestModelHotSwap:
    """Verify ModelManager.swap_model with drain/rollback semantics."""

    def _make_manager(self) -> Any:
        from file_organizer.models.model_manager import ModelManager

        return ModelManager(console=MagicMock())

    def test_swap_succeeds_new_model_active(self) -> None:
        """After successful swap, new model is active."""
        mgr = self._make_manager()

        new_model = MagicMock()
        new_model.initialize = MagicMock()
        factory = MagicMock(return_value=new_model)

        success = mgr.swap_model("text", "new-model", model_factory=factory)
        assert success is True
        assert mgr.get_active_model("text") is new_model
        new_model.initialize.assert_called_once()

    def test_swap_fails_old_model_continues(self) -> None:
        """On init failure, old model remains active (rollback)."""
        mgr = self._make_manager()

        old_model = MagicMock()
        mgr._active_models["text"] = old_model

        factory = MagicMock(side_effect=RuntimeError("init failed"))

        success = mgr.swap_model("text", "bad-model", model_factory=factory)
        assert success is False
        assert mgr.get_active_model("text") is old_model

    def test_swap_drains_old_model(self) -> None:
        """Old model's safe_cleanup is called during swap."""
        mgr = self._make_manager()

        old_model = MagicMock()
        old_model.safe_cleanup = MagicMock()
        mgr._active_models["text"] = old_model

        new_model = MagicMock()
        factory = MagicMock(return_value=new_model)

        success = mgr.swap_model("text", "new-model", model_factory=factory)
        assert success is True
        old_model.safe_cleanup.assert_called_once()

    def test_drain_failure_is_best_effort(self) -> None:
        """Drain failure after swap is logged but does not roll back.

        The reference swap is committed before draining the old model
        so callers never observe a shutting-down model.  If the drain
        raises, the new model is already active and ``True`` is returned.
        """
        mgr = self._make_manager()

        old_model = MagicMock()
        old_model.safe_cleanup = MagicMock(side_effect=RuntimeError("drain error"))
        mgr._active_models["text"] = old_model

        new_model = MagicMock()
        new_model.cleanup = MagicMock()
        factory = MagicMock(return_value=new_model)

        success = mgr.swap_model("text", "new-model", model_factory=factory)
        assert success is True  # swap committed despite drain failure
        assert mgr._active_models["text"] is new_model  # new model is active
        new_model.cleanup.assert_not_called()  # new model not cleaned up

    def test_prewarm_failure_cleans_up_partial_model(self) -> None:
        """If initialize() fails, partially created model is cleaned up."""
        mgr = self._make_manager()

        new_model = MagicMock()
        new_model.initialize = MagicMock(side_effect=RuntimeError("init boom"))
        new_model.cleanup = MagicMock()
        factory = MagicMock(return_value=new_model)

        success = mgr.swap_model("text", "bad-model", model_factory=factory)
        assert success is False
        new_model.cleanup.assert_called_once()

    def test_concurrent_swap_rejected(self) -> None:
        """Second concurrent swap is rejected (lock held)."""
        mgr = self._make_manager()

        # Simulate a slow swap by holding the lock
        mgr._swap_lock.acquire()

        try:
            success = mgr.swap_model("text", "new-model")
            assert success is False
        finally:
            mgr._swap_lock.release()

    def test_swap_without_factory(self) -> None:
        """Swap without factory records the model ID but loads no live instance."""
        mgr = self._make_manager()
        success = mgr.swap_model("text", "recorded-model")
        assert success is True
        # No live model is loaded — get_active_model returns None
        assert mgr.get_active_model("text") is None
        # The selected ID is still tracked via get_active_model_id
        assert mgr.get_active_model_id("text") == "recorded-model"

    def test_concurrent_generate_during_swap(self) -> None:
        """Thread-safety: concurrent generate() calls during swap don't crash."""
        mgr = self._make_manager()

        old_model = MagicMock()
        old_model.safe_cleanup = MagicMock()
        old_model.generate = MagicMock(return_value="response")
        mgr._active_models["text"] = old_model

        errors: list[Exception] = []

        def generate_loop() -> None:
            for _ in range(10):
                try:
                    model = mgr.get_active_model("text")
                    if model and hasattr(model, "generate"):
                        model.generate("test prompt")
                except Exception as e:
                    errors.append(e)
                time.sleep(0.001)

        # Start generate calls in background
        threads = [threading.Thread(target=generate_loop) for _ in range(3)]
        for t in threads:
            t.start()

        # Swap while generates are running
        new_model = MagicMock()
        new_model.generate = MagicMock(return_value="new response")
        factory = MagicMock(return_value=new_model)
        mgr.swap_model("text", "new-model", model_factory=factory)

        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), f"Thread {t.name} did not terminate within 5 s"

        assert len(errors) == 0, f"Got errors during concurrent swap: {errors}"
        # Verify swap actually happened
        factory.assert_called_once()
        old_model.safe_cleanup.assert_called_once()
