"""Text processing utilities."""

import re
from typing import Set, List

try:
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

from loguru import logger


def ensure_nltk_data() -> None:
    """Ensure NLTK data is downloaded (quietly).

    Downloads required NLTK datasets if not already present.
    This is called automatically on first use.
    """
    if not NLTK_AVAILABLE:
        logger.warning("NLTK not available, text processing will be limited")
        return

    datasets = ['stopwords', 'punkt', 'wordnet']
    for dataset in datasets:
        try:
            # Try to load the dataset
            if dataset == 'stopwords':
                stopwords.words('english')
            elif dataset == 'punkt':
                word_tokenize("test")
            elif dataset == 'wordnet':
                from nltk.corpus import wordnet
                wordnet.synsets("test")
        except LookupError:
            # Dataset not found, download it
            try:
                logger.info(f"Downloading NLTK dataset: {dataset}")
                nltk.download(dataset, quiet=True)
                logger.debug(f"NLTK dataset {dataset} downloaded successfully")
            except Exception as e:
                logger.warning(f"Failed to download NLTK {dataset}: {e}")
        except Exception:
            # Dataset exists but failed to load, ignore
            pass

    logger.debug("NLTK data verified and ready")


def get_unwanted_words() -> Set[str]:
    """Get set of unwanted words to filter out.

    Returns:
        Set of unwanted words
    """
    unwanted = {
        # Generic words
        'the', 'and', 'based', 'generated', 'this', 'is', 'filename', 'file',
        'document', 'text', 'output', 'only', 'below', 'category', 'summary',
        'key', 'details', 'information', 'note', 'notes', 'main', 'ideas',
        'concepts', 'untitled', 'unknown',

        # Prepositions and articles
        'in', 'on', 'of', 'with', 'by', 'for', 'to', 'from', 'a', 'an',
        'as', 'at',

        # Pronouns
        'i', 'we', 'you', 'they', 'he', 'she', 'it', 'that', 'which',

        # Auxiliary verbs
        'are', 'were', 'was', 'be', 'have', 'has', 'had', 'do', 'does', 'did',

        # Conjunctions
        'but', 'if', 'or', 'because', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below',

        # Quantifiers
        'any', 'each', 'few', 'more', 'most', 'other', 'some', 'such',

        # Negations
        'no', 'nor', 'not',

        # Other common words
        'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't',
        'can', 'will', 'just', 'don', 'should', 'now', 'new',

        # Action verbs to avoid in filenames
        'depicts', 'show', 'shows', 'display', 'illustrates', 'presents',
        'features', 'provides', 'covers', 'includes', 'discusses',
        'demonstrates', 'describes',

        # File type words
        'image', 'picture', 'photo', 'jpg', 'jpeg', 'png', 'gif', 'bmp',
        'pdf', 'docx', 'xlsx', 'pptx', 'csv', 'txt', 'md',
    }

    # Add NLTK stopwords if available
    if NLTK_AVAILABLE:
        try:
            unwanted.update(stopwords.words('english'))
        except LookupError:
            logger.warning("NLTK stopwords not available")

    return unwanted


def clean_text(
    text: str,
    max_words: int = 5,
    remove_unwanted: bool = True,
    lemmatize: bool = True,
) -> str:
    """Clean and process text for use as filename or folder name.

    Args:
        text: Input text to clean
        max_words: Maximum number of words to keep
        remove_unwanted: Whether to remove unwanted words
        lemmatize: Whether to lemmatize words

    Returns:
        Cleaned text with words joined by underscores
    """
    if not text:
        return ""

    # Remove special characters and numbers
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', '', text)
    text = text.strip()

    # Split concatenated words (camelCase, PascalCase)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Tokenize
    if NLTK_AVAILABLE:
        try:
            words = word_tokenize(text.lower())
        except LookupError:
            # Fallback if NLTK data not available
            words = text.lower().split()
    else:
        words = text.lower().split()

    # Filter alpha-only words
    words = [word for word in words if word.isalpha()]

    # Lemmatize if available
    if lemmatize and NLTK_AVAILABLE:
        try:
            lemmatizer = WordNetLemmatizer()
            words = [lemmatizer.lemmatize(word) for word in words]
        except Exception as e:
            logger.debug(f"Lemmatization failed: {e}")

    # Remove unwanted words and duplicates
    if remove_unwanted:
        unwanted = get_unwanted_words()
        filtered_words = []
        seen = set()

        for word in words:
            if word not in unwanted and word not in seen:
                filtered_words.append(word)
                seen.add(word)

        words = filtered_words

    # Limit to max words
    words = words[:max_words]

    # Join with underscores
    return '_'.join(words)


def sanitize_filename(
    name: str,
    max_length: int = 50,
    max_words: int = 5,
) -> str:
    """Sanitize a string for use as a filename.

    Args:
        name: Input name
        max_length: Maximum length of result
        max_words: Maximum number of words

    Returns:
        Sanitized filename
    """
    # First clean with text processing
    cleaned = clean_text(name, max_words=max_words)

    # If empty after cleaning, provide default
    if not cleaned:
        return 'untitled'

    # Remove any remaining non-alphanumeric except underscores
    sanitized = re.sub(r'[^\w]', '_', cleaned)

    # Replace multiple underscores with single
    sanitized = re.sub(r'_+', '_', sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')

    return sanitized.lower() if sanitized else 'untitled'


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """Extract top keywords from text.

    Args:
        text: Input text
        top_n: Number of top keywords to return

    Returns:
        List of top keywords
    """
    if not NLTK_AVAILABLE:
        # Fallback: simple word frequency
        words = text.lower().split()
        from collections import Counter
        word_freq = Counter(words)
        return [word for word, _ in word_freq.most_common(top_n)]

    try:
        from nltk.probability import FreqDist

        # Tokenize and clean
        words = word_tokenize(text.lower())
        words = [w for w in words if w.isalpha() and len(w) > 3]

        # Remove stopwords
        unwanted = get_unwanted_words()
        words = [w for w in words if w not in unwanted]

        # Get frequency distribution
        freq_dist = FreqDist(words)

        # Return top N
        return [word for word, _ in freq_dist.most_common(top_n)]

    except Exception as e:
        logger.debug(f"Keyword extraction failed: {e}")
        return []


def truncate_text(text: str, max_chars: int = 5000) -> str:
    """Truncate text to maximum characters.

    Args:
        text: Input text
        max_chars: Maximum characters

    Returns:
        Truncated text
    """
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."
