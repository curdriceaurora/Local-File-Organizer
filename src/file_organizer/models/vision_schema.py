"""Structured vision schema for image analysis."""

from __future__ import annotations

from typing import Any

import pydantic


class VisionSchema(pydantic.BaseModel):
    """Pydantic schema for single-call structured image analysis."""

    description: str = pydantic.Field(
        description="A detailed description of the image, focusing on the main subject and important details."
    )
    folder_name: str = pydantic.Field(
        description="A general category or theme best representing the main subject, used as a folder name. Limit to a maximum of 2 words, lowercase, plural, e.g. 'screenshots', 'receipts'."
    )
    filename: str = pydantic.Field(
        description="A specific and descriptive filename based on the image. Limit to 3 words, lowercase, connected with underscores, e.g. 'grocery_receipt_target'."
    )
    has_text: bool = pydantic.Field(
        description="True if there is significant visible text in the image that should be extracted, False otherwise."
    )
    extracted_text: str | None = pydantic.Field(
        default=None,
        description="The exact text extracted from the image if has_text is True. Provide it exactly as it appears.",
    )

    @pydantic.field_validator("extracted_text", mode="before")
    @classmethod
    def normalize_extracted_text(cls, value: Any) -> str | None:
        """Accept common object-shaped OCR responses from local vision models."""
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                return text
            if isinstance(text, list) and all(isinstance(line, str) for line in text):
                return "\n".join(text)
            lines = value.get("lines")
            if isinstance(lines, list) and all(isinstance(line, str) for line in lines):
                return "\n".join(lines)
        if isinstance(value, list) and all(isinstance(line, str) for line in value):
            return "\n".join(value)
        return None


class TaggedVisionSchema(VisionSchema):
    """Pydantic schema for single-call structured image analysis with tags."""

    tags: list[str] = pydantic.Field(
        default_factory=list,
        description="3-8 lowercase descriptive tags (single words or hyphenated phrases) categorizing the image.",
    )
