"""Tests for Ollama response helpers (Stream 1 of #717)."""

from __future__ import annotations

import pytest

from file_organizer.models._ollama_response import (
    compute_retry_num_predict,
    format_exhaustion_diagnostics,
    is_token_exhausted,
)
from file_organizer.models.base import (
    MAX_NUM_PREDICT,
    MIN_USEFUL_RESPONSE_LENGTH,
    TokenExhaustionError,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestIsTokenExhausted:
    """Tests for is_token_exhausted()."""

    def test_empty_response_with_length_reason(self) -> None:
        resp = {"response": "", "done_reason": "length"}
        assert is_token_exhausted(resp) is True

    def test_short_response_with_length_reason(self) -> None:
        resp = {"response": "hi", "done_reason": "length"}
        assert is_token_exhausted(resp) is True

    def test_adequate_response_with_length_reason(self) -> None:
        resp = {"response": "A" * 50, "done_reason": "length"}
        assert is_token_exhausted(resp) is False

    def test_empty_response_with_stop_reason(self) -> None:
        resp = {"response": "", "done_reason": "stop"}
        assert is_token_exhausted(resp) is False

    def test_missing_done_reason(self) -> None:
        resp = {"response": ""}
        assert is_token_exhausted(resp) is False

    def test_none_response_with_length_reason(self) -> None:
        resp = {"response": None, "done_reason": "length"}
        assert is_token_exhausted(resp) is True

    def test_whitespace_only_response(self) -> None:
        resp = {"response": "   \n\t  ", "done_reason": "length"}
        assert is_token_exhausted(resp) is True

    def test_custom_min_length(self) -> None:
        resp = {"response": "A" * 20, "done_reason": "length"}
        assert is_token_exhausted(resp, min_length=50) is True
        assert is_token_exhausted(resp, min_length=10) is False

    def test_default_min_length_matches_constant(self) -> None:
        text = "A" * (MIN_USEFUL_RESPONSE_LENGTH - 1)
        resp = {"response": text, "done_reason": "length"}
        assert is_token_exhausted(resp) is True

        text = "A" * MIN_USEFUL_RESPONSE_LENGTH
        resp = {"response": text, "done_reason": "length"}
        assert is_token_exhausted(resp) is False


class TestComputeRetryNumPredict:
    """Tests for compute_retry_num_predict()."""

    def test_doubles_current_value(self) -> None:
        assert compute_retry_num_predict(3000) == 6000

    def test_caps_at_max(self) -> None:
        assert compute_retry_num_predict(10000) == MAX_NUM_PREDICT

    def test_already_at_cap(self) -> None:
        assert compute_retry_num_predict(MAX_NUM_PREDICT) == MAX_NUM_PREDICT

    def test_above_cap(self) -> None:
        assert compute_retry_num_predict(MAX_NUM_PREDICT + 1000) == MAX_NUM_PREDICT

    def test_custom_cap(self) -> None:
        assert compute_retry_num_predict(3000, cap=4000) == 4000

    def test_small_value(self) -> None:
        assert compute_retry_num_predict(100) == 200


class TestFormatExhaustionDiagnostics:
    """Tests for format_exhaustion_diagnostics()."""

    def test_contains_model_name(self) -> None:
        resp = {"done_reason": "length", "response": ""}
        result = format_exhaustion_diagnostics(resp, "qwen3-vl:8b")
        assert "qwen3-vl:8b" in result

    def test_contains_done_reason(self) -> None:
        resp = {"done_reason": "length", "response": ""}
        result = format_exhaustion_diagnostics(resp, "test-model")
        assert "done_reason=length" in result

    def test_contains_eval_count(self) -> None:
        resp = {"done_reason": "length", "response": "", "eval_count": 3000}
        result = format_exhaustion_diagnostics(resp, "test-model")
        assert "eval_count=3000" in result

    def test_contains_response_length(self) -> None:
        resp = {"done_reason": "length", "response": "short"}
        result = format_exhaustion_diagnostics(resp, "test-model")
        assert "response_length=5" in result

    def test_handles_missing_fields(self) -> None:
        resp = {"done_reason": "length"}
        result = format_exhaustion_diagnostics(resp, "test-model")
        assert "response_length=0" in result
        assert "eval_count=N/A" in result


class TestTokenExhaustionError:
    """Tests for the TokenExhaustionError exception class."""

    def test_is_runtime_error_subclass(self) -> None:
        assert issubclass(TokenExhaustionError, RuntimeError)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(TokenExhaustionError, match="budget"):
            raise TokenExhaustionError("Token budget exhausted")

    def test_caught_as_runtime_error(self) -> None:
        with pytest.raises(RuntimeError):
            raise TokenExhaustionError("test")
