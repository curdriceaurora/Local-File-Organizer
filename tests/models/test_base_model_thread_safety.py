"""Tests for BaseModel thread-safety: lifecycle lock and generation guards.

Covers issue #726 — race condition between cleanup() and in-flight generate().
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from file_organizer.models.base import BaseModel, ModelConfig, ModelType

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.smoke]

# ---------------------------------------------------------------------------
# Concrete stub for testing
# ---------------------------------------------------------------------------


class _StubModel(BaseModel):
    """Minimal concrete model for testing BaseModel thread-safety."""

    def __init__(self, config: ModelConfig, generate_delay: float = 0.0) -> None:
        super().__init__(config)
        self.client: Any = None
        self._generate_delay = generate_delay

    def initialize(self) -> None:
        self.client = MagicMock()
        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        self._enter_generate()
        try:
            # Simulate work with configurable delay
            if self._generate_delay > 0:
                time.sleep(self._generate_delay)
            if self.client is None:
                raise RuntimeError("Model not initialized. Call initialize() first.")
            return f"response to: {prompt}"
        finally:
            self._exit_generate()

    def cleanup(self) -> None:
        with self._lifecycle_lock:
            self._initialized = False
            self.client = None


def _make_config() -> ModelConfig:
    return ModelConfig(name="test-model", model_type=ModelType.TEXT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerationGuards:
    """Verify _enter_generate / _exit_generate / safe_cleanup."""

    def test_enter_generate_raises_when_not_initialized(self) -> None:
        model = _StubModel(_make_config())
        with pytest.raises(RuntimeError, match="not initialized"):
            model._enter_generate()

    def test_enter_generate_increments_counter(self) -> None:
        model = _StubModel(_make_config())
        model.initialize()
        model._enter_generate()
        assert model._active_generations == 1
        model._exit_generate()
        assert model._active_generations == 0

    def test_generate_works_normally(self) -> None:
        model = _StubModel(_make_config())
        model.initialize()
        result = model.generate("hello")
        assert result == "response to: hello"
        assert model._active_generations == 0

    def test_safe_cleanup_waits_for_in_flight_generation(self) -> None:
        """safe_cleanup should block until in-flight generate() finishes."""
        model = _StubModel(_make_config(), generate_delay=0.3)
        model.initialize()

        results: list[str] = []
        errors: list[Exception] = []

        def _generate_in_thread() -> None:
            try:
                result = model.generate("slow prompt")
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Start a generation in a background thread
        gen_thread = threading.Thread(target=_generate_in_thread)
        gen_thread.start()

        # Give the thread a moment to enter generate()
        time.sleep(0.05)
        assert model._active_generations == 1

        # safe_cleanup should wait for the generation to finish
        cleanup_start = time.monotonic()
        model.safe_cleanup()
        cleanup_duration = time.monotonic() - cleanup_start

        gen_thread.join(timeout=2.0)

        # Generation should have completed successfully
        assert len(errors) == 0, f"Generate raised: {errors}"
        assert len(results) == 1
        assert results[0] == "response to: slow prompt"

        # Cleanup should have waited (at least partially)
        assert cleanup_duration >= 0.1

        # Model should now be cleaned up
        assert not model.is_initialized
        assert model.client is None

    def test_cleanup_under_lock_prevents_race(self) -> None:
        """cleanup() sets _initialized=False under lock, so concurrent
        _enter_generate() should see the updated state."""
        model = _StubModel(_make_config())
        model.initialize()

        # Cleanup first
        model.cleanup()

        # Now _enter_generate should fail
        with pytest.raises(RuntimeError, match="not initialized"):
            model._enter_generate()

    def test_multiple_concurrent_generations(self) -> None:
        """Multiple threads can generate concurrently."""
        model = _StubModel(_make_config(), generate_delay=0.1)
        model.initialize()

        results: list[str] = []
        lock = threading.Lock()

        def _gen(idx: int) -> None:
            result = model.generate(f"prompt-{idx}")
            with lock:
                results.append(result)

        threads = [threading.Thread(target=_gen, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()

        # All should be in-flight at some point
        time.sleep(0.05)
        assert model._active_generations >= 1

        for t in threads:
            t.join(timeout=5.0)

        assert len(results) == 5
        assert model._active_generations == 0

    def test_safe_cleanup_timeout(self) -> None:
        """safe_cleanup proceeds after timeout even if generation is stuck."""
        model = _StubModel(_make_config(), generate_delay=2.0)
        model.CLEANUP_TIMEOUT = 0.2  # Very short timeout for test
        model.initialize()

        errors: list[Exception] = []

        def _slow_generate() -> None:
            try:
                model.generate("stuck")
            except RuntimeError:
                # Expected: model cleaned up while generating
                errors.append(RuntimeError("expected"))

        # Start a long-running generation
        gen_thread = threading.Thread(target=_slow_generate, daemon=True)
        gen_thread.start()
        time.sleep(0.05)

        # safe_cleanup should timeout and proceed
        start = time.monotonic()
        model.safe_cleanup()
        duration = time.monotonic() - start

        # Should have timed out (not waited full delay)
        assert duration < 1.0
        assert not model.is_initialized

        gen_thread.join(timeout=5.0)

    def test_generate_after_cleanup_raises(self) -> None:
        """generate() raises RuntimeError if called after cleanup."""
        model = _StubModel(_make_config())
        model.initialize()
        model.cleanup()

        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("should fail")

    def test_reinitialize_after_safe_cleanup(self) -> None:
        """Model can be re-initialized and used after safe_cleanup()."""
        model = _StubModel(_make_config())
        model.initialize()
        assert model.generate("first") == "response to: first"

        model.safe_cleanup()
        assert not model.is_initialized
        assert model._shutting_down is True

        # Re-initialize should reset _shutting_down and allow generation
        model.initialize()
        assert model.is_initialized
        assert model._shutting_down is False
        assert model.generate("second") == "response to: second"
