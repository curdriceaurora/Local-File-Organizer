"""Shared OpenAPI response metadata for REST endpoints."""

from __future__ import annotations

from typing import Any

from file_organizer.api.models import (
    ApiErrorResponse,
    HttpDetailErrorResponse,
    ValidationErrorResponse,
)

OpenAPIResponses = dict[int | str, dict[str, Any]]


def _json_content(model: type[Any], example: Any) -> dict[str, Any]:
    return {
        "application/json": {
            "schema": model.model_json_schema(),
            "example": example,
        }
    }


def success_response(
    description: str,
    example: Any,
    *,
    status_code: int = 200,
) -> OpenAPIResponses:
    """Build a documented success response with an example object or array payload."""
    return {
        status_code: {
            "description": description,
            "content": {"application/json": {"example": example}},
        }
    }


def api_error_response(
    status_code: int,
    *,
    error: str,
    message: str,
    description: str | None = None,
    details: Any | None = None,
) -> OpenAPIResponses:
    """Build an ApiError-style response entry."""
    payload: dict[str, Any] = {"error": error, "message": message}
    if details is not None:
        payload["details"] = details
    return {
        status_code: {
            "description": description or message,
            "content": _json_content(ApiErrorResponse, payload),
        }
    }


def detail_error_response(
    status_code: int,
    *,
    detail: str,
    description: str | None = None,
) -> OpenAPIResponses:
    """Build a FastAPI HTTPException-style response entry."""
    return {
        status_code: {
            "description": description or detail,
            "content": _json_content(HttpDetailErrorResponse, {"detail": detail}),
        }
    }


def validation_error_response() -> OpenAPIResponses:
    """Build the standard request validation error response entry."""
    return {
        422: {
            "description": "Request validation error.",
            "content": _json_content(
                ValidationErrorResponse,
                {
                    "error": "validation_error",
                    "message": "Invalid request payload.",
                    "details": [
                        {"loc": ["body", "path"], "msg": "Path must not be empty"},
                    ],
                },
            ),
        }
    }


def merge_responses(*response_sets: OpenAPIResponses) -> OpenAPIResponses:
    """Merge multiple OpenAPI response maps.

    When multiple sets define the same status code, later arguments override
    earlier ones. Callers should order response sets accordingly.
    """
    merged: OpenAPIResponses = {}
    for response_set in response_sets:
        merged.update(response_set)
    return merged


AUTH_401_RESPONSE = api_error_response(
    401,
    error="unauthorized",
    message="Authentication required or token invalid.",
)
ADMIN_403_RESPONSE = api_error_response(
    403,
    error="forbidden",
    message="Administrator privileges required.",
)
INTERNAL_500_RESPONSE = api_error_response(
    500,
    error="internal_server_error",
    message="Unexpected server error.",
)
