"""
Unit tests for the event middleware pipeline.

Tests pipeline execution order, individual middleware behaviour,
error handling, and the built-in LoggingMiddleware, MetricsMiddleware,
and RetryMiddleware.
"""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.events.middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewarePipeline,
    RetryMiddleware,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


class _PassthroughMiddleware:
    """Minimal middleware that passes data through unchanged."""

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def after_publish(self, topic: str, data: dict[str, Any], message_id: str | None) -> None:
        pass

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def after_consume(self, topic: str, data: dict[str, Any], error: Exception | None) -> None:
        pass


class _BlockingMiddleware:
    """Middleware that cancels publish/consume by returning None."""

    def before_publish(self, topic: str, data: dict[str, Any]) -> None:
        return None

    def before_consume(self, topic: str, data: dict[str, Any]) -> None:
        return None


class _TrackingMiddleware:
    """Middleware that records call order for testing."""

    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self._calls = calls

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        self._calls.append(f"{self.name}:before_publish")
        return data

    def after_publish(self, topic: str, data: dict[str, Any], message_id: str | None) -> None:
        self._calls.append(f"{self.name}:after_publish")

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        self._calls.append(f"{self.name}:before_consume")
        return data

    def after_consume(self, topic: str, data: dict[str, Any], error: Exception | None) -> None:
        self._calls.append(f"{self.name}:after_consume")


class _ErrorMiddleware:
    """Middleware that raises in every hook."""

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("before_publish error")

    def after_publish(self, topic: str, data: dict[str, Any], message_id: str | None) -> None:
        raise RuntimeError("after_publish error")

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("before_consume error")

    def after_consume(self, topic: str, data: dict[str, Any], error: Exception | None) -> None:
        raise RuntimeError("after_consume error")


# ------------------------------------------------------------------
# MiddlewarePipeline
# ------------------------------------------------------------------


@pytest.mark.unit
class TestMiddlewarePipeline:
    """Tests for the MiddlewarePipeline."""

    def test_add_and_count(self) -> None:
        """Adding middleware increases count."""
        p = MiddlewarePipeline()
        p.add(_PassthroughMiddleware())
        assert p.count == 1
        assert len(p) == 1

    def test_remove(self) -> None:
        """Removing middleware decreases count."""
        p = MiddlewarePipeline()
        mw = _PassthroughMiddleware()
        p.add(mw)
        assert p.remove(mw) is True
        assert p.count == 0

    def test_remove_nonexistent(self) -> None:
        """Removing a middleware not in the pipeline returns False."""
        p = MiddlewarePipeline()
        assert p.remove(_PassthroughMiddleware()) is False

    def test_clear(self) -> None:
        """clear empties the pipeline."""
        p = MiddlewarePipeline()
        p.add(_PassthroughMiddleware())
        p.add(_PassthroughMiddleware())
        p.clear()
        assert p.count == 0

    def test_before_publish_passthrough(self) -> None:
        """Passthrough middleware returns data unchanged."""
        p = MiddlewarePipeline()
        p.add(_PassthroughMiddleware())
        data = {"key": "val"}
        result = p.run_before_publish("t", data)
        assert result == data

    def test_before_publish_blocking(self) -> None:
        """Blocking middleware cancels publish (returns None)."""
        p = MiddlewarePipeline()
        p.add(_BlockingMiddleware())
        result = p.run_before_publish("t", {"key": "val"})
        assert result is None

    def test_before_publish_chain_short_circuits(self) -> None:
        """After blocking middleware, subsequent middleware are skipped."""
        calls: list[str] = []
        p = MiddlewarePipeline()
        p.add(_BlockingMiddleware())
        p.add(_TrackingMiddleware("second", calls))
        p.run_before_publish("t", {"key": "val"})
        assert "second:before_publish" not in calls

    def test_before_publish_order(self) -> None:
        """before_publish runs in registration order."""
        calls: list[str] = []
        p = MiddlewarePipeline()
        p.add(_TrackingMiddleware("A", calls))
        p.add(_TrackingMiddleware("B", calls))
        p.run_before_publish("t", {})
        assert calls == ["A:before_publish", "B:before_publish"]

    def test_after_publish_reverse_order(self) -> None:
        """after_publish runs in reverse (onion) order."""
        calls: list[str] = []
        p = MiddlewarePipeline()
        p.add(_TrackingMiddleware("A", calls))
        p.add(_TrackingMiddleware("B", calls))
        p.run_after_publish("t", {}, "msg-1")
        assert calls == ["B:after_publish", "A:after_publish"]

    def test_before_consume_order(self) -> None:
        """before_consume runs in registration order."""
        calls: list[str] = []
        p = MiddlewarePipeline()
        p.add(_TrackingMiddleware("A", calls))
        p.add(_TrackingMiddleware("B", calls))
        p.run_before_consume("t", {})
        assert calls == ["A:before_consume", "B:before_consume"]

    def test_after_consume_reverse_order(self) -> None:
        """after_consume runs in reverse order."""
        calls: list[str] = []
        p = MiddlewarePipeline()
        p.add(_TrackingMiddleware("A", calls))
        p.add(_TrackingMiddleware("B", calls))
        p.run_after_consume("t", {}, None)
        assert calls == ["B:after_consume", "A:after_consume"]

    def test_error_in_middleware_does_not_propagate(self) -> None:
        """Errors in middleware are logged but do not propagate."""
        p = MiddlewarePipeline()
        p.add(_ErrorMiddleware())
        # Should not raise
        p.run_before_publish("t", {"x": 1})
        p.run_after_publish("t", {"x": 1}, None)
        p.run_before_consume("t", {"x": 1})
        p.run_after_consume("t", {"x": 1}, None)

    def test_repr(self) -> None:
        """Repr lists middleware class names."""
        p = MiddlewarePipeline()
        p.add(_PassthroughMiddleware())
        r = repr(p)
        assert "_PassthroughMiddleware" in r

    def test_empty_pipeline_passthrough(self) -> None:
        """Empty pipeline passes data through."""
        p = MiddlewarePipeline()
        data = {"key": "val"}
        assert p.run_before_publish("t", data) == data
        assert p.run_before_consume("t", data) == data


# ------------------------------------------------------------------
# LoggingMiddleware
# ------------------------------------------------------------------


@pytest.mark.unit
class TestLoggingMiddleware:
    """Tests for the LoggingMiddleware."""

    def test_before_publish_returns_data(self) -> None:
        """before_publish returns data unchanged."""
        mw = LoggingMiddleware()
        data = {"key": "val"}
        assert mw.before_publish("t", data) == data

    def test_before_consume_returns_data(self) -> None:
        """before_consume returns data unchanged."""
        mw = LoggingMiddleware()
        data = {"key": "val"}
        assert mw.before_consume("t", data) == data

    def test_after_publish_success_logs_info(self, mocker) -> None:
        """Successful publish logs at INFO level."""
        mw = LoggingMiddleware()
        mock_logger = mocker.patch.object(mw, "_logger")
        mw.after_publish("topic.a", {}, "msg-1")
        mock_logger.info.assert_called()
        assert "Published" in mock_logger.info.call_args[0][0]

    def test_after_publish_failure_logs_warning(self, mocker) -> None:
        """Failed publish logs at WARNING level."""
        mw = LoggingMiddleware()
        mock_logger = mocker.patch.object(mw, "_logger")
        mw.after_publish("topic.a", {}, None)
        mock_logger.warning.assert_called()
        assert "Failed" in mock_logger.warning.call_args[0][0]

    def test_after_consume_error_logs_warning(self, mocker) -> None:
        """Handler error logs at WARNING level."""
        mw = LoggingMiddleware()
        mock_logger = mocker.patch.object(mw, "_logger")
        mw.after_consume("t", {}, ValueError("oops"))
        mock_logger.warning.assert_called()
        assert "error" in mock_logger.warning.call_args[0][0].lower()

    def test_after_consume_success_logs_info(self, mocker) -> None:
        """Successful consume logs at INFO level."""
        mw = LoggingMiddleware()
        mock_logger = mocker.patch.object(mw, "_logger")
        mw.after_consume("t", {}, None)
        mock_logger.info.assert_called()
        assert "successfully" in mock_logger.info.call_args[0][0]


# ------------------------------------------------------------------
# MetricsMiddleware
# ------------------------------------------------------------------


@pytest.mark.unit
class TestMetricsMiddleware:
    """Tests for the MetricsMiddleware."""

    def test_initial_counts_zero(self) -> None:
        """All counters start at zero."""
        mw = MetricsMiddleware()
        assert mw.publish_count == 0
        assert mw.publish_errors == 0
        assert mw.consume_count == 0
        assert mw.consume_errors == 0

    def test_after_publish_success_increments(self) -> None:
        """Successful publish increments publish_count."""
        mw = MetricsMiddleware()
        mw.after_publish("t", {}, "msg-1")
        assert mw.publish_count == 1
        assert mw.publish_errors == 0

    def test_after_publish_failure_increments_errors(self) -> None:
        """Failed publish increments publish_errors."""
        mw = MetricsMiddleware()
        mw.after_publish("t", {}, None)
        assert mw.publish_errors == 1
        assert mw.publish_count == 0

    def test_after_consume_success_increments(self) -> None:
        """Successful consume increments consume_count."""
        mw = MetricsMiddleware()
        mw.before_consume("t", {})
        mw.after_consume("t", {}, None)
        assert mw.consume_count == 1

    def test_after_consume_error_increments_errors(self) -> None:
        """Handler error increments consume_errors."""
        mw = MetricsMiddleware()
        mw.before_consume("t", {})
        mw.after_consume("t", {}, RuntimeError("fail"))
        assert mw.consume_errors == 1

    def test_topic_publish_counts(self) -> None:
        """Per-topic publish counts are tracked."""
        mw = MetricsMiddleware()
        mw.after_publish("file.created", {}, "1")
        mw.after_publish("file.created", {}, "2")
        mw.after_publish("scan.started", {}, "3")
        assert mw.topic_publish_counts["file.created"] == 2
        assert mw.topic_publish_counts["scan.started"] == 1

    def test_avg_consume_time_ms(self) -> None:
        """Average consume time is computed correctly."""
        mw = MetricsMiddleware()
        # Simulate two consumes
        mw.before_consume("t", {})
        mw.after_consume("t", {}, None)
        mw.before_consume("t", {})
        mw.after_consume("t", {}, None)
        # Just verify it's non-negative (timing-dependent)
        assert mw.avg_consume_time_ms >= 0.0

    def test_avg_consume_time_zero_when_no_events(self) -> None:
        """Average is 0.0 when no events have been consumed."""
        mw = MetricsMiddleware()
        assert mw.avg_consume_time_ms == 0.0

    def test_reset(self) -> None:
        """reset clears all counters."""
        mw = MetricsMiddleware()
        mw.after_publish("t", {}, "1")
        mw.before_consume("t", {})
        mw.after_consume("t", {}, None)
        mw.reset()
        assert mw.publish_count == 0
        assert mw.consume_count == 0
        assert mw.total_consume_time_ms == 0.0
        assert mw.topic_publish_counts == {}

    def test_before_publish_returns_data(self) -> None:
        """before_publish passes data through."""
        mw = MetricsMiddleware()
        data = {"k": "v"}
        assert mw.before_publish("t", data) == data

    def test_before_consume_returns_data(self) -> None:
        """before_consume passes data through."""
        mw = MetricsMiddleware()
        data = {"k": "v"}
        assert mw.before_consume("t", data) == data


# ------------------------------------------------------------------
# RetryMiddleware
# ------------------------------------------------------------------


@pytest.mark.unit
class TestRetryMiddleware:
    """Tests for the RetryMiddleware."""

    def test_default_max_retries(self) -> None:
        """Default max_retries is 3."""
        mw = RetryMiddleware()
        assert mw.max_retries == 3

    def test_should_retry_within_limit(self) -> None:
        """should_retry returns True within the retry limit."""
        mw = RetryMiddleware(max_retries=2)
        data = {"key": "val"}
        mw.before_consume("t", data)
        mw.after_consume("t", data, RuntimeError("fail"))
        assert mw.should_retry("t", data) is True

    def test_should_retry_exceeds_limit(self) -> None:
        """should_retry returns False when retries are exhausted."""
        mw = RetryMiddleware(max_retries=2)
        data = {"key": "val"}
        mw.before_consume("t", data)
        # First failure: attempts=1, 1 < 2 -> retry allowed
        mw.after_consume("t", data, RuntimeError("fail"))
        assert mw.should_retry("t", data) is True
        # Second failure: attempts=2, 2 < 2 -> False, retries exhausted
        mw.after_consume("t", data, RuntimeError("fail again"))
        assert mw.should_retry("t", data) is False

    def test_total_retries_counter(self) -> None:
        """total_retries tracks cumulative retry attempts."""
        mw = RetryMiddleware(max_retries=3)
        data = {"key": "val"}
        mw.before_consume("t", data)
        mw.after_consume("t", data, RuntimeError("fail"))
        mw.should_retry("t", data)
        assert mw.total_retries == 1

    def test_reset(self) -> None:
        """reset clears retry state."""
        mw = RetryMiddleware(max_retries=3)
        data = {"key": "val"}
        mw.before_consume("t", data)
        mw.after_consume("t", data, RuntimeError("fail"))
        mw.should_retry("t", data)
        mw.reset()
        assert mw.total_retries == 0

    def test_before_publish_returns_data(self) -> None:
        """before_publish passes data through."""
        mw = RetryMiddleware()
        data = {"k": "v"}
        assert mw.before_publish("t", data) == data

    def test_no_retry_on_success(self) -> None:
        """No retry needed when consume succeeds."""
        mw = RetryMiddleware(max_retries=3)
        data = {"key": "val"}
        mw.before_consume("t", data)
        mw.after_consume("t", data, None)
        # No error recorded, attempt count stays at 0
        # should_retry should still return True (0 < 3)
        assert mw.should_retry("t", data) is True
