"""File analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.models.text_model import TextModel
from file_organizer.services.analyzer import (
    MAX_CONTENT_LENGTH,
    calculate_confidence,
    generate_category,
    generate_description,
    truncate_content,
)

# Global model instance
_text_model: TextModel | None = None


def get_text_model() -> TextModel:
    """Get or initialize the text model."""
    global _text_model
    if _text_model is None:
        config = TextModel.get_default_config()
        _text_model = TextModel(config)
        _text_model.initialize()
    model = _text_model
    assert model is not None
    return model


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
    """Analyze file content using AI and provide description and category.

    Accepts either text content or file upload.
    Returns AI-generated description, category, and confidence score.

    Note: Requires Ollama to be installed and running with a text model.
    """
    if content is None and file is None:
        raise HTTPException(
            status_code=400,
            detail="Either content or file must be provided",
        )

    if file:
        file_content = await file.read()
        text_content = file_content.decode("utf-8", errors="ignore")
    else:
        text_content = content or ""

    # Truncate content if too long
    text_content = truncate_content(text_content, MAX_CONTENT_LENGTH)

    try:
        # Initialize text model for AI-based analysis
        model = get_text_model()

        # Generate category using AI
        category = generate_category(model, text_content)

        # Generate description using AI
        description = generate_description(model, text_content)

        # Calculate confidence based on content length and clarity
        confidence = calculate_confidence(text_content, description)

        logger.info(f"Analysis complete: category={category}, confidence={confidence:.2f}")

        return AnalyzeResponse(
            description=description,
            category=category,
            confidence=confidence,
        )

    except ImportError as e:
        logger.warning(f"Ollama not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI analysis unavailable. Please ensure Ollama is installed and running.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to analyze content: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        ) from e
