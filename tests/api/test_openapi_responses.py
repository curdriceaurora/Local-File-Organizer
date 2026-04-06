"""Unit and regression tests for openapi_responses helpers."""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.api.openapi_responses import (
    api_error_response,
    merge_responses,
    success_response,
)

pytestmark = pytest.mark.unit


class TestApiErrorResponse:
    """Tests for api_error_response()."""

    def test_emits_named_example_keyed_by_error_slug(self) -> None:
        """Result carries examples[error_slug] not a singular example key."""
        result = api_error_response(400, error="invalid_key", message="Bad key")
        examples: dict[str, Any] = result[400]["content"]["application/json"]["examples"]
        assert examples["invalid_key"]["value"]["error"] == "invalid_key"

    def test_custom_example_name_overrides_error_slug(self) -> None:
        """example_name kwarg is used as the key instead of the error slug."""
        result = api_error_response(
            400,
            error="invalid_key",
            message="Bad key",
            example_name="my_variant",
        )
        examples: dict[str, Any] = result[400]["content"]["application/json"]["examples"]
        assert "my_variant" in examples
        assert "invalid_key" not in examples

    def test_details_included_when_provided(self) -> None:
        """details kwarg is attached under value['details']."""
        result = api_error_response(
            400,
            error="invalid_key",
            message="Bad key",
            details={"field": "x"},
        )
        value = result[400]["content"]["application/json"]["examples"]["invalid_key"]["value"]
        assert value["details"] == {"field": "x"}

    def test_no_details_key_when_absent(self) -> None:
        """When details is not provided the key must be absent from value."""
        result = api_error_response(400, error="invalid_key", message="Bad key")
        value = result[400]["content"]["application/json"]["examples"]["invalid_key"]["value"]
        assert "details" not in value


class TestMergeResponses:
    """Tests for merge_responses()."""

    def test_merge_different_status_codes(self) -> None:
        """Two sets with distinct status codes produce a dict with both keys."""
        r400 = api_error_response(400, error="bad_request", message="Bad")
        r404 = api_error_response(404, error="not_found", message="Not found")
        merged = merge_responses(r400, r404)
        assert 400 in merged
        assert 404 in merged

    def test_merge_same_status_preserves_both_named_examples(self) -> None:
        """Two api_error_response entries sharing a status code are merged at the examples level."""
        r1 = api_error_response(400, error="invalid_key", message="A")
        r2 = api_error_response(400, error="invalid_path", message="B")
        merged = merge_responses(r1, r2)
        examples: dict[str, Any] = merged[400]["content"]["application/json"]["examples"]
        assert "invalid_key" in examples
        assert "invalid_path" in examples

    def test_merge_same_status_regression_later_does_not_erase_earlier(self) -> None:
        """Merging a second same-status error must not overwrite the first variant."""
        r1 = api_error_response(400, error="invalid_key", message="A")
        r2 = api_error_response(400, error="invalid_path", message="B")
        merged = merge_responses(r1, r2)
        examples: dict[str, Any] = merged[400]["content"]["application/json"]["examples"]
        # The first variant must survive after the second is merged in.
        assert "invalid_key" in examples
        assert examples["invalid_key"]["value"]["error"] == "invalid_key"

    def test_merge_success_response_uses_last_wins(self) -> None:
        """success_response uses singular 'example'; last entry wins when status codes collide."""
        r1 = success_response("First", example={"status": "first"}, status_code=200)
        r2 = success_response("Second", example={"status": "second"}, status_code=200)
        merged = merge_responses(r1, r2)
        # Only one key 200 exists and it is the last-merged entry.
        assert merged[200]["content"]["application/json"]["example"] == {"status": "second"}

    def test_merge_empty_inputs(self) -> None:
        """Calling merge_responses() with no arguments returns an empty dict."""
        assert merge_responses() == {}

    def test_merge_single_input(self) -> None:
        """A single response set is returned structurally unchanged."""
        r = api_error_response(401, error="unauthorized", message="X")
        merged = merge_responses(r)
        examples: dict[str, Any] = merged[401]["content"]["application/json"]["examples"]
        assert "unauthorized" in examples
        assert examples["unauthorized"]["value"]["message"] == "X"

    def test_merge_same_status_description_honors_last_wins(self) -> None:
        """Non-example fields (description) use the later entry's values."""
        first = api_error_response(400, error="err_a", message="First", description="desc-first")
        second = api_error_response(400, error="err_b", message="Second", description="desc-second")
        merged = merge_responses(first, second)
        # Both examples preserved
        examples: dict[str, Any] = merged[400]["content"]["application/json"]["examples"]
        assert "err_a" in examples
        assert "err_b" in examples
        # Description from the later entry wins
        assert merged[400]["description"] == "desc-second"

    def test_merge_responses_does_not_mutate_inputs(self) -> None:
        """merge_responses() must not mutate any of its input dicts."""
        import copy

        first = api_error_response(400, error="err_a", message="First")
        second = api_error_response(400, error="err_b", message="Second")
        first_copy = copy.deepcopy(first)
        second_copy = copy.deepcopy(second)

        merge_responses(first, second)

        assert first == first_copy, "first input was mutated"
        assert second == second_copy, "second input was mutated"
