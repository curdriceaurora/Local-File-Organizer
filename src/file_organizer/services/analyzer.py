"""Shared file analysis service used by both API and CLI."""

from __future__ import annotations

from loguru import logger

# Confidence score bounds
MIN_CONFIDENCE = 0.3
MAX_CONFIDENCE = 0.95

# Valid categories
VALID_CATEGORIES = {
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

# Max content length for analysis
MAX_CONTENT_LENGTH = 2000


def generate_category(model: object, content: str) -> str:
    """Generate category using AI model.

    Args:
        model: Initialized text model with a ``generate`` method.
        content: Text content to categorize.

    Returns:
        Category name from :data:`VALID_CATEGORIES`.
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
        response = str(model.generate(prompt, temperature=0.3, max_tokens=20))  # type: ignore[attr-defined]
        category = response.strip().lower()

        # Extract first word and validate it's in our list
        first_word = category.split()[0] if category else ""
        if first_word in VALID_CATEGORIES:
            category = first_word
        else:
            # If not valid, try to find any valid category in the response
            found = False
            for word in category.split():
                if word in VALID_CATEGORIES:
                    category = word
                    found = True
                    break
            if not found:
                logger.warning(
                    f"AI returned invalid category '{category}', defaulting to 'general'"
                )
                category = "general"

        return category

    except (RuntimeError, ValueError, OSError, AttributeError) as e:
        logger.error(f"Failed to generate category: {e}")
        return "general"


def generate_description(model: object, content: str) -> str:
    """Generate description using AI model.

    Args:
        model: Initialized text model with a ``generate`` method.
        content: Text content to describe.

    Returns:
        Description text.
    """
    prompt = f"""Provide a brief description (1-2 sentences, max 100 words) of the following text. Focus on the main topic and key points.

TEXT:
{content}

DESCRIPTION:"""

    try:
        response = model.generate(prompt, temperature=0.5, max_tokens=150)  # type: ignore[attr-defined]
        description = response.strip()

        # Remove common prefixes
        prefixes = ["description:", "this is", "the text is about", "this text"]
        for prefix in prefixes:
            if description.lower().startswith(prefix):
                description = description[len(prefix) :].strip()

        return description if description else "Document content analysis"

    except (RuntimeError, ValueError, OSError, AttributeError) as e:
        logger.error(f"Failed to generate description: {e}")
        return "Document content analysis"


def calculate_confidence(content: str, description: str) -> float:
    """Calculate confidence score based on content quality and description.

    Args:
        content: Original content.
        description: Generated description.

    Returns:
        Confidence score between :data:`MIN_CONFIDENCE` and :data:`MAX_CONFIDENCE`.
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

    # Cap between MIN_CONFIDENCE and MAX_CONFIDENCE
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))

    return round(confidence, 2)


def truncate_content(content: str, max_chars: int = MAX_CONTENT_LENGTH) -> str:
    """Truncate content to *max_chars* if needed.

    Args:
        content: Text to truncate.
        max_chars: Maximum character count.

    Returns:
        Truncated (or original) text.
    """
    if len(content) > max_chars:
        logger.debug(f"Truncated content to {max_chars} characters for analysis")
        return content[:max_chars]
    return content
