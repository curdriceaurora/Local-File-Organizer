"""File analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.models.text_model import TextModel

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
        return JSONResponse(
            status_code=400,
            content={"detail": "Either content or file must be provided"},
        )

    if file:
        file_content = await file.read()
        text_content = file_content.decode("utf-8", errors="ignore")
    else:
        text_content = content or ""

    # Truncate content if too long (max 2000 chars for analysis)
    max_chars = 2000
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars]
        logger.debug(f"Truncated content to {max_chars} characters for analysis")

    try:
        # Initialize text model for AI-based analysis
        config = TextModel.get_default_config()
        text_model = TextModel(config)
        text_model.initialize()

        # Generate category using AI
        category = _generate_category(text_model, text_content)

        # Generate description using AI
        description = _generate_description(text_model, text_content)

        # Calculate confidence based on content length and clarity
        confidence = _calculate_confidence(text_content, description)

        # Cleanup
        text_model.cleanup()

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


def _generate_category(model: TextModel, content: str) -> str:
    """Generate category using AI model.

    Args:
        model: Initialized text model
        content: Text content to categorize

    Returns:
        Category name
    """
    prompt = f"""Analyze the following text and determine its category. Choose ONE category from this list:
- technical (programming, science, engineering, technology)
- business (finance, marketing, management, entrepreneurship)
- creative (art, design, writing, media)
- education (learning materials, courses, tutorials)
- personal (notes, journals, personal documents)
- legal (contracts, agreements, legal documents)
- medical (health, medical records, research)
- recipe (cooking, food preparation)
- general (anything else)

TEXT:
{content}

Output ONLY the category name, nothing else."""

    try:
        response = model.generate(prompt, temperature=0.3, max_tokens=20)
        category = response.strip().lower()

        # Clean up response - remove any extra text
        category = category.split()[0] if category else "general"

        # Validate category is in our predefined list
        valid_categories = {
            "technical",
            "business",
            "creative",
            "education",
            "personal",
            "legal",
            "medical",
            "recipe",
            "general",
        }

        if category not in valid_categories:
            logger.warning(f"AI returned invalid category '{category}', defaulting to 'general'")
            category = "general"

        return category

    except Exception as e:
        logger.error(f"Failed to generate category: {e}")
        return "general"


def _generate_description(model: TextModel, content: str) -> str:
    """Generate description using AI model.

    Args:
        model: Initialized text model
        content: Text content to describe

    Returns:
        Description text
    """
    prompt = f"""Provide a brief description (1-2 sentences, max 100 words) of the following text. Focus on the main topic and key points.

TEXT:
{content}

DESCRIPTION:"""

    try:
        response = model.generate(prompt, temperature=0.5, max_tokens=150)
        description = response.strip()

        # Remove common prefixes
        prefixes = ["description:", "this is", "the text is about", "this text"]
        for prefix in prefixes:
            if description.lower().startswith(prefix):
                description = description[len(prefix) :].strip()

        return description if description else "Document content analysis"

    except Exception as e:
        logger.error(f"Failed to generate description: {e}")
        return "Document content analysis"


def _calculate_confidence(content: str, description: str) -> float:
    """Calculate confidence score based on content quality and description.

    Args:
        content: Original content
        description: Generated description

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Base confidence
    confidence = 0.5

    # Increase confidence for longer, more substantial content
    if len(content) > 500:
        confidence += 0.1
    if len(content) > 1000:
        confidence += 0.1

    # Increase confidence if description is detailed
    if len(description) > 50:
        confidence += 0.1
    if len(description) > 100:
        confidence += 0.1

    # Decrease confidence for very short content
    if len(content) < 100:
        confidence -= 0.2

    # Cap between 0.3 and 0.95
    confidence = max(0.3, min(0.95, confidence))

    return round(confidence, 2)
