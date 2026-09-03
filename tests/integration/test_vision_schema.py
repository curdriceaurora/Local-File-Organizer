"""Integration coverage for local vision model schema normalization."""

from __future__ import annotations

import pytest

from file_organizer.models.base import parse_structured_json
from file_organizer.models.vision_schema import TaggedVisionSchema, VisionSchema

pytestmark = [pytest.mark.integration, pytest.mark.ci]


def _parse_vision_schema(extracted_text: str) -> VisionSchema:
    result = parse_structured_json(
        (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": true, '
            f'"extracted_text": {extracted_text}}}'
        ),
        VisionSchema,
    )
    assert isinstance(result, VisionSchema)
    return result


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('"Payment process"', "Payment process"),
        ("null", None),
        ('{"text": "Payment process"}', "Payment process"),
        ('{"text": ["Payment", "process"]}', "Payment\nprocess"),
        ('{"lines": ["Payment", "process"]}', "Payment\nprocess"),
        ('["Payment", "process"]', "Payment\nprocess"),
        ('{"confidence": 0.7}', None),
        ('{"text": ["Payment", 3]}', None),
        ('{"lines": ["Payment", 3]}', None),
        ('["Payment", 3]', None),
    ],
)
def test_vision_schema_normalizes_model_ocr_shapes(
    payload: str,
    expected: str | None,
) -> None:
    assert _parse_vision_schema(payload).extracted_text == expected


def test_tagged_vision_schema_defaults_tags_to_empty() -> None:
    result = parse_structured_json(
        (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": false}'
        ),
        TaggedVisionSchema,
    )
    assert isinstance(result, TaggedVisionSchema)
    assert result.tags == []


def test_tagged_vision_schema_parses_tags() -> None:
    result = parse_structured_json(
        (
            '{"description": "desc", "folder_name": "screenshots", '
            '"filename": "payment_process", "has_text": false, '
            '"tags": ["invoice", "receipt", "october"]}'
        ),
        TaggedVisionSchema,
    )
    assert isinstance(result, TaggedVisionSchema)
    assert result.tags == ["invoice", "receipt", "october"]
