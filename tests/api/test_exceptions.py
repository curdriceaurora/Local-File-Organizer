"""Tests for file_organizer.api.exceptions module."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.exceptions import ApiError, setup_exception_handlers
from file_organizer.core.errors import optional_feature_unavailable


class TestApiErrorInit:
    """Tests for ApiError initialization and field access."""

    def test_fields_set_correctly(self) -> None:
        err = ApiError(status_code=400, error="bad_request", message="Invalid input")
        assert err.status_code == 400
        assert err.error == "bad_request"
        assert err.message == "Invalid input"

    def test_details_default_none(self) -> None:
        err = ApiError(status_code=500, error="server_error", message="Oops")
        assert err.details is None

    def test_details_stored(self) -> None:
        detail_data = {"field": "name", "reason": "too_short"}
        err = ApiError(
            status_code=422,
            error="validation_error",
            message="Validation failed",
            details=detail_data,
        )
        assert err.details == detail_data


class TestApiErrorMessage:
    """Tests for ApiError string representation."""

    def test_str_format(self) -> None:
        err = ApiError(status_code=404, error="not_found", message="Resource missing")
        assert str(err) == "404 not_found: Resource missing"

    def test_str_format_with_details(self) -> None:
        err = ApiError(
            status_code=403,
            error="forbidden",
            message="Access denied",
            details=["a", "b"],
        )
        # details do not affect the string representation
        assert str(err) == "403 forbidden: Access denied"


class TestApiErrorInheritance:
    """Tests for ApiError exception hierarchy."""

    def test_is_exception_subclass(self) -> None:
        assert issubclass(ApiError, Exception)

    def test_instance_is_exception(self) -> None:
        err = ApiError(status_code=500, error="internal", message="fail")
        assert isinstance(err, Exception)


class TestApiErrorRaiseCatch:
    """Tests for raising and catching ApiError."""

    def test_raise_and_catch_as_api_error(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            raise ApiError(status_code=409, error="conflict", message="Duplicate")
        assert exc_info.value.status_code == 409
        assert exc_info.value.error == "conflict"

    def test_catch_as_exception(self) -> None:
        with pytest.raises(Exception, match="500 boom") as exc_info:
            raise ApiError(status_code=500, error="boom", message="Unexpected")
        assert isinstance(exc_info.value, ApiError)

    def test_caught_exception_preserves_fields(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            raise ApiError(
                status_code=418,
                error="teapot",
                message="I'm a teapot",
                details={"brew": "earl_grey"},
            )
        assert isinstance(exc_info.value, ApiError)
        assert exc_info.value.status_code == 418
        assert exc_info.value.details == {"brew": "earl_grey"}


def test_domain_error_handler_preserves_stable_contract() -> None:
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/optional")
    def optional_route() -> None:
        raise optional_feature_unavailable("transcription", "Install the audio extra.")

    response = TestClient(app).get("/optional")

    assert response.status_code == 503
    assert response.json() == {
        "error": "optional_feature_unavailable",
        "code": "optional_feature_unavailable",
        "message": "Install the audio extra.",
        "retryable": False,
        "details": {"feature": "transcription"},
    }
