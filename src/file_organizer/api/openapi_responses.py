"""Shared OpenAPI response metadata for REST endpoints."""

from __future__ import annotations

import copy
import http
from typing import Any

from file_organizer.api.models import (
    ApiErrorResponse,
    HttpDetailErrorResponse,
    ValidationErrorResponse,
)

OpenAPIResponses = dict[int | str, dict[str, Any]]


def _json_content(model: type[Any], example: Any) -> dict[str, Any]:
    """Build the `content` block for an OpenAPI JSON response with the given example."""
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
    example_name: str | None = None,
) -> OpenAPIResponses:
    """Build an ApiError-style response entry with a named OpenAPI example.

    Args:
        status_code: HTTP status code for this response variant.
        error: Machine-readable error slug (also used as the default example name).
        message: Human-readable description of the error.
        description: Optional override for the response-level description line.
        details: Optional extra payload attached under ``"details"``.
        example_name: Key used in the ``examples`` map.  Defaults to ``error``.

    Returns:
        Single-entry ``OpenAPIResponses`` dict whose example is keyed by
        ``example_name`` so that :func:`merge_responses` can preserve multiple
        same-status variants side-by-side.
    """
    payload: dict[str, Any] = {"error": error, "message": message}
    if details is not None:
        payload["details"] = details
    name = example_name or error
    schema = ApiErrorResponse.model_json_schema()
    return {
        status_code: {
            "description": description or message,
            "content": {
                "application/json": {
                    "schema": schema,
                    "examples": {name: {"value": payload}},
                }
            },
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
    """Merge multiple OpenAPI response maps, preserving same-status variants.

    For each status code:

    - If only one response set defines it, the entry is used as-is.
    - If multiple sets define the same status code **and** both entries carry
      a ``content["application/json"]["examples"]`` dict (as produced by
      :func:`api_error_response`), their example dicts are merged so that
      every named variant is retained.
    - Otherwise (e.g. a ``success_response`` that uses ``"example"`` singular)
      the later entry wins, matching the previous ``dict.update`` semantics.

    Args:
        *response_sets: Zero or more ``OpenAPIResponses`` dicts to merge in
            order.  Later entries take precedence for non-example conflicts.

    Returns:
        A single merged ``OpenAPIResponses`` dict.
    """
    merged: OpenAPIResponses = {}
    for response_set in response_sets:
        for status_code, incoming in response_set.items():
            if status_code not in merged:
                # Deep-copy so mutations to merged never affect caller's dicts.
                merged[status_code] = copy.deepcopy(incoming)
                continue
            # Attempt two-level examples merge for api_error_response entries.
            try:
                existing_examples: dict[str, Any] = merged[status_code]["content"][
                    "application/json"
                ]["examples"]
                incoming_examples: dict[str, Any] = incoming["content"]["application/json"][
                    "examples"
                ]
                # Start from a deep copy of *incoming* so that non-example
                # top-level fields (description, schema, …) honor last-wins.
                merged_entry = copy.deepcopy(incoming)
                # Combine examples: existing first, then incoming overwrites
                # duplicate keys so the later definition wins within examples too.
                merged_examples = {
                    **copy.deepcopy(existing_examples),
                    **copy.deepcopy(incoming_examples),
                }
                merged_entry["content"]["application/json"]["examples"] = merged_examples
                # Use a neutral description so the merged response is not
                # mislabelled with one variant's specific message.
                # int() normalises both int and numeric-string keys; ValueError
                # for non-standard codes falls through to the outer except.
                merged_entry["description"] = http.HTTPStatus(int(status_code)).phrase
                merged[status_code] = merged_entry
            except (KeyError, TypeError, ValueError):
                # One or both entries use "example" singular (success/detail
                # responses) — fall back to last-wins, still deep-copied.
                merged[status_code] = copy.deepcopy(incoming)
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
