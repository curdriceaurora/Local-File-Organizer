"""File analysis endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["analyze"])


class AnalyzeResponse(BaseModel):
    """Response from analyze endpoint."""

    description: str
    category: str
    confidence: float


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    content: str | None = None,
    file: UploadFile | None = None,
    settings: ApiSettings = Depends(get_settings),
) -> AnalyzeResponse:
    """Analyze file content and provide description and category.

    Accepts either text content or file upload.
    Returns description, category, and confidence score.
    """
    if content is None and file is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "Either content or file must be provided"},
        )

    if file:
        file_content = await file.read()
        text_content = file_content.decode("utf-8", errors="ignore")
    else:
        text_content = content or ""

    # Simple analysis: determine category based on content
    text_lower = text_content.lower()

    if any(word in text_lower for word in ["machine learning", "neural", "ai", "algorithm"]):
        category = "technical"
        description = "Technical document about machine learning or AI"
    elif any(word in text_lower for word in ["recipe", "cooking", "ingredients"]):
        category = "recipe"
        description = "Recipe or cooking document"
    else:
        category = "general"
        description = "General document"

    confidence = 0.8 if description else 0.5

    return AnalyzeResponse(
        description=description,
        category=category,
        confidence=confidence,
    )
