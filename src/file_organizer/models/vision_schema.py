"""Structured vision schema for image analysis."""

from __future__ import annotations

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
