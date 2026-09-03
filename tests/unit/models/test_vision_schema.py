"""Unit tests for VisionSchema and TaggedVisionSchema."""

from __future__ import annotations

import pytest

from file_organizer.models.vision_schema import TaggedVisionSchema, VisionSchema

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_vision_schema_fields() -> None:
    schema = VisionSchema(
        description="A nice photo",
        folder_name="landscapes",
        filename="mountains_sunset",
        has_text=False,
    )
    assert schema.description == "A nice photo"
    assert schema.folder_name == "landscapes"
    assert schema.filename == "mountains_sunset"
    assert schema.has_text is False
    assert schema.extracted_text is None


def test_tagged_vision_schema_default_tags() -> None:
    schema = TaggedVisionSchema(
        description="A nice photo",
        folder_name="landscapes",
        filename="mountains_sunset",
        has_text=False,
    )
    assert isinstance(schema, VisionSchema)
    assert schema.tags == []


def test_tagged_vision_schema_with_tags() -> None:
    schema = TaggedVisionSchema(
        description="A nice photo",
        folder_name="landscapes",
        filename="mountains_sunset",
        has_text=False,
        tags=["nature", "mountains", "sunset"],
    )
    assert schema.tags == ["nature", "mountains", "sunset"]


@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        (None, None),
        ("simple text", "simple text"),
        ({"text": "hello"}, "hello"),
        ({"text": ["hello", "world"]}, "hello\nworld"),
        ({"lines": ["foo", "bar"]}, "foo\nbar"),
        ({"other": 123}, None),
        (["line 1", "line 2"], "line 1\nline 2"),
        (["line 1", 2], None),
        (12345, None),
    ],
)
def test_normalize_extracted_text(input_val: object, expected: str | None) -> None:
    schema = TaggedVisionSchema(
        description="desc",
        folder_name="folder",
        filename="file",
        has_text=True,
        extracted_text=input_val,  # type: ignore[arg-type]
    )
    assert schema.extracted_text == expected
