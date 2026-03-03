"""Tests for client exception classes: ClientError, AuthenticationError, NotFoundError, ServerError, ValidationError."""

from __future__ import annotations

import pytest

from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)


@pytest.mark.unit
class TestClientError:
    """Tests for ClientError base exception."""

    def test_create_basic_error(self) -> None:
        """Test creating a basic ClientError."""
        error = ClientError("Test error message")

        assert str(error) == "Test error message"
        assert error.status_code == 0
        assert error.detail == ""

    def test_create_with_status_code(self) -> None:
        """Test creating ClientError with status code."""
        error = ClientError("Test error", status_code=400)

        assert error.status_code == 400
        assert error.detail == ""

    def test_create_with_detail(self) -> None:
        """Test creating ClientError with detail message."""
        error = ClientError(
            "Test error",
            status_code=400,
            detail="Invalid request body",
        )

        assert error.status_code == 400
        assert error.detail == "Invalid request body"

    def test_error_inheritance(self) -> None:
        """Test that ClientError inherits from Exception."""
        error = ClientError("Test")
        assert isinstance(error, Exception)

    def test_error_can_be_raised(self) -> None:
        """Test that ClientError can be raised and caught."""
        with pytest.raises(ClientError):
            raise ClientError("Test error")

    def test_error_message_preserved(self) -> None:
        """Test that error message is preserved."""
        message = "This is a detailed error message"
        error = ClientError(message)
        assert str(error) == message

    def test_error_with_all_fields(self) -> None:
        """Test ClientError with all fields populated."""
        error = ClientError(
            message="Request failed",
            status_code=500,
            detail="Internal server error occurred",
        )

        assert str(error) == "Request failed"
        assert error.status_code == 500
        assert error.detail == "Internal server error occurred"

    def test_error_attributes_accessible(self) -> None:
        """Test that error attributes are accessible."""
        error = ClientError(
            "Error message",
            status_code=418,
            detail="I'm a teapot",
        )

        assert hasattr(error, "status_code")
        assert hasattr(error, "detail")
        assert error.status_code == 418
        assert error.detail == "I'm a teapot"


@pytest.mark.unit
class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_create_auth_error(self) -> None:
        """Test creating an AuthenticationError."""
        error = AuthenticationError("Unauthorized access", status_code=401)

        assert str(error) == "Unauthorized access"
        assert error.status_code == 401

    def test_auth_error_inheritance(self) -> None:
        """Test that AuthenticationError inherits from ClientError."""
        error = AuthenticationError("Unauthorized")
        assert isinstance(error, ClientError)
        assert isinstance(error, Exception)

    def test_auth_error_401(self) -> None:
        """Test AuthenticationError for 401 Unauthorized."""
        error = AuthenticationError(
            "Invalid credentials",
            status_code=401,
            detail="Invalid API key",
        )

        assert error.status_code == 401
        assert error.detail == "Invalid API key"

    def test_auth_error_403(self) -> None:
        """Test AuthenticationError for 403 Forbidden."""
        error = AuthenticationError(
            "Forbidden access",
            status_code=403,
            detail="Insufficient permissions",
        )

        assert error.status_code == 403
        assert error.detail == "Insufficient permissions"

    def test_auth_error_can_be_caught_as_client_error(self) -> None:
        """Test that AuthenticationError can be caught as ClientError."""
        with pytest.raises(ClientError):
            raise AuthenticationError("Auth failed")

    def test_auth_error_can_be_caught_specifically(self) -> None:
        """Test that AuthenticationError can be caught specifically."""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Auth failed")


@pytest.mark.unit
class TestNotFoundError:
    """Tests for NotFoundError exception."""

    def test_create_not_found_error(self) -> None:
        """Test creating a NotFoundError."""
        error = NotFoundError("Resource not found", status_code=404)

        assert str(error) == "Resource not found"
        assert error.status_code == 404

    def test_not_found_error_inheritance(self) -> None:
        """Test that NotFoundError inherits from ClientError."""
        error = NotFoundError("Not found")
        assert isinstance(error, ClientError)
        assert isinstance(error, Exception)

    def test_not_found_error_404(self) -> None:
        """Test NotFoundError for 404 Not Found."""
        error = NotFoundError(
            "File not found",
            status_code=404,
            detail="The requested file does not exist",
        )

        assert error.status_code == 404
        assert error.detail == "The requested file does not exist"

    def test_not_found_error_can_be_caught_as_client_error(self) -> None:
        """Test that NotFoundError can be caught as ClientError."""
        with pytest.raises(ClientError):
            raise NotFoundError("File not found")

    def test_not_found_error_can_be_caught_specifically(self) -> None:
        """Test that NotFoundError can be caught specifically."""
        with pytest.raises(NotFoundError):
            raise NotFoundError("File not found")


@pytest.mark.unit
class TestServerError:
    """Tests for ServerError exception."""

    def test_create_server_error(self) -> None:
        """Test creating a ServerError."""
        error = ServerError("Internal server error", status_code=500)

        assert str(error) == "Internal server error"
        assert error.status_code == 500

    def test_server_error_inheritance(self) -> None:
        """Test that ServerError inherits from ClientError."""
        error = ServerError("Server error")
        assert isinstance(error, ClientError)
        assert isinstance(error, Exception)

    def test_server_error_500(self) -> None:
        """Test ServerError for 500 Internal Server Error."""
        error = ServerError(
            "Server error",
            status_code=500,
            detail="Something went wrong",
        )

        assert error.status_code == 500
        assert error.detail == "Something went wrong"

    def test_server_error_502(self) -> None:
        """Test ServerError for 502 Bad Gateway."""
        error = ServerError(
            "Bad gateway",
            status_code=502,
            detail="Upstream service unavailable",
        )

        assert error.status_code == 502

    def test_server_error_503(self) -> None:
        """Test ServerError for 503 Service Unavailable."""
        error = ServerError(
            "Service unavailable",
            status_code=503,
            detail="Server is overloaded",
        )

        assert error.status_code == 503

    def test_server_error_can_be_caught_as_client_error(self) -> None:
        """Test that ServerError can be caught as ClientError."""
        with pytest.raises(ClientError):
            raise ServerError("Server error")

    def test_server_error_can_be_caught_specifically(self) -> None:
        """Test that ServerError can be caught specifically."""
        with pytest.raises(ServerError):
            raise ServerError("Server error")


@pytest.mark.unit
class TestValidationError:
    """Tests for ValidationError exception."""

    def test_create_validation_error(self) -> None:
        """Test creating a ValidationError."""
        error = ValidationError("Validation failed", status_code=422)

        assert str(error) == "Validation failed"
        assert error.status_code == 422

    def test_validation_error_inheritance(self) -> None:
        """Test that ValidationError inherits from ClientError."""
        error = ValidationError("Validation failed")
        assert isinstance(error, ClientError)
        assert isinstance(error, Exception)

    def test_validation_error_422(self) -> None:
        """Test ValidationError for 422 Unprocessable Entity."""
        error = ValidationError(
            "Invalid input",
            status_code=422,
            detail="Field 'name' is required",
        )

        assert error.status_code == 422
        assert error.detail == "Field 'name' is required"

    def test_validation_error_can_be_caught_as_client_error(self) -> None:
        """Test that ValidationError can be caught as ClientError."""
        with pytest.raises(ClientError):
            raise ValidationError("Invalid")

    def test_validation_error_can_be_caught_specifically(self) -> None:
        """Test that ValidationError can be caught specifically."""
        with pytest.raises(ValidationError):
            raise ValidationError("Invalid")


@pytest.mark.unit
class TestExceptionHierarchy:
    """Tests for exception hierarchy and catching."""

    def test_catch_authentication_error(self) -> None:
        """Test catching specific AuthenticationError."""
        try:
            raise AuthenticationError("Auth failed", status_code=401)
        except AuthenticationError as e:
            assert e.status_code == 401
        except ClientError:
            pytest.fail("Should catch as AuthenticationError first")

    def test_catch_by_client_error(self) -> None:
        """Test catching any ClientError subclass as ClientError."""
        errors = [
            AuthenticationError("Auth", status_code=401),
            NotFoundError("Not found", status_code=404),
            ServerError("Error", status_code=500),
            ValidationError("Invalid", status_code=422),
        ]

        for error in errors:
            try:
                raise error
            except ClientError as e:
                assert e.status_code > 0

    def test_exception_chaining(self) -> None:
        """Test exception chaining with context."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise ClientError("Wrapped error", status_code=500) from e
        except ClientError as e:
            assert e.status_code == 500
            assert e.__cause__ is not None

    def test_status_code_range_coverage(self) -> None:
        """Test exceptions cover various HTTP status codes."""
        exceptions = [
            (AuthenticationError("", 401), 401),
            (AuthenticationError("", 403), 403),
            (NotFoundError("", 404), 404),
            (ValidationError("", 422), 422),
            (ServerError("", 500), 500),
            (ServerError("", 502), 502),
            (ServerError("", 503), 503),
        ]

        for exc, expected_code in exceptions:
            assert exc.status_code == expected_code
