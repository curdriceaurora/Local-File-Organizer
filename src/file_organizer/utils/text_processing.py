"""Text processing utilities.

Deterministic, fully-offline NLP helpers (WP-4.4, #1234). This module previously
relied on an optional NLTK runtime dependency with ``nltk.download()`` corpus
fetching; that path was non-deterministic (network access, ``LookupError`` corpus
misses) and is now removed. Stopwords are vendored in-module (the standard NLTK
English list) and stemming is provided by the pure-Python ``snowballstemmer``
package. Tokenization is a deterministic ASCII regex tokenizer.

ASCII-only tokenization is an accepted trade-off for determinism and offline
operation.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

import snowballstemmer
from loguru import logger

# ---------------------------------------------------------------------------
# Vendored English stopwords (standard NLTK English stopword list, ~179 words).
# Kept in-module so text processing is deterministic and requires no corpus
# download. ``get_unwanted_words`` unions this with the hand-curated set below.
# ---------------------------------------------------------------------------
_ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    {
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "you're",
        "you've",
        "you'll",
        "you'd",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "she's",
        "her",
        "hers",
        "herself",
        "it",
        "it's",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "that'll",
        "these",
        "those",
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "a",
        "an",
        "the",
        "and",
        "but",
        "if",
        "or",
        "because",
        "as",
        "until",
        "while",
        "of",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "s",
        "t",
        "can",
        "will",
        "just",
        "don",
        "don't",
        "should",
        "should've",
        "now",
        "d",
        "ll",
        "m",
        "o",
        "re",
        "ve",
        "y",
        "ain",
        "aren",
        "aren't",
        "couldn",
        "couldn't",
        "didn",
        "didn't",
        "doesn",
        "doesn't",
        "hadn",
        "hadn't",
        "hasn",
        "hasn't",
        "haven",
        "haven't",
        "isn",
        "isn't",
        "ma",
        "mightn",
        "mightn't",
        "mustn",
        "mustn't",
        "needn",
        "needn't",
        "shan",
        "shan't",
        "shouldn",
        "shouldn't",
        "wasn",
        "wasn't",
        "weren",
        "weren't",
        "won",
        "won't",
        "wouldn",
        "wouldn't",
    }
)


@lru_cache(maxsize=1)
def _get_stemmer() -> snowballstemmer.EnglishStemmer:
    """Return a cached Snowball English stemmer.

    The stemmer is pure-Python and deterministic; caching avoids rebuilding it
    on every ``clean_text`` call.
    """
    return snowballstemmer.stemmer("english")


def ensure_nltk_data() -> None:
    """No-op backward-compatibility shim (WP-4.4, #1234).

    Text processing no longer depends on NLTK or any downloadable corpus; stopwords
    are vendored and stemming uses the pure-Python ``snowballstemmer`` package. This
    function is retained only so existing callers (e.g.
    ``services.text_processor.TextProcessor``) keep working without modification.
    It performs no network access, never raises, and returns immediately.
    """
    logger.debug("ensure_nltk_data() is a no-op; text processing is fully offline")


def get_unwanted_words() -> set[str]:
    """Get set of unwanted words to filter out.

    Unions the hand-curated set below with the vendored English stopword list so
    common stopwords (``the``, ``and``, ``a`` ...) are always filtered without any
    runtime corpus download.

    Returns:
        Set of unwanted words.
    """
    unwanted = {
        # Generic words
        "the",
        "and",
        "based",
        "generated",
        "this",
        "is",
        "filename",
        "file",
        "document",
        "text",
        "output",
        "only",
        "below",
        "category",
        "summary",
        "key",
        "details",
        "information",
        "note",
        "notes",
        "main",
        "ideas",
        "concepts",
        "untitled",
        "unknown",
        # Prepositions and articles
        "in",
        "on",
        "of",
        "with",
        "by",
        "for",
        "to",
        "from",
        "a",
        "an",
        "as",
        "at",
        # Pronouns
        "i",
        "we",
        "you",
        "they",
        "he",
        "she",
        "it",
        "that",
        "which",
        # Auxiliary verbs
        "are",
        "were",
        "was",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        # Conjunctions
        "but",
        "if",
        "or",
        "because",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",  # Quantifiers
        "any",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        # Negations
        "no",
        "nor",
        "not",
        # Other common words
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "s",
        "t",
        "can",
        "will",
        "just",
        "don",
        "should",
        "now",
        "new",
        # Action verbs to avoid in filenames
        "depicts",
        "show",
        "shows",
        "display",
        "illustrates",
        "presents",
        "features",
        "provides",
        "covers",
        "includes",
        "discusses",
        "demonstrates",
        "describes",
        # File type words
        "image",
        "picture",
        "photo",
        "jpg",
        "jpeg",
        "png",
        "gif",
        "bmp",
        "pdf",
        "docx",
        "xlsx",
        "pptx",
        "csv",
        "txt",
        "md",
    }

    # Union with the vendored stopword list (deterministic, offline).
    unwanted.update(_ENGLISH_STOPWORDS)

    return unwanted


def _tokenize(text: str) -> list[str]:
    """Deterministic ASCII word tokenizer.

    Splits *text* into lowercase ASCII word tokens. This replaces NLTK's
    ``word_tokenize`` with a regex tokenizer that requires no corpus and produces
    identical output on every run. ASCII-only is an accepted trade-off.

    Args:
        text: Input text (assumed already lowercased by the caller).

    Returns:
        List of word tokens.
    """
    return re.findall(r"[a-z]+", text)


def clean_text(
    text: str | None,
    max_words: int = 5,
    remove_unwanted: bool = True,
    lemmatize: bool = True,
) -> str:
    """Clean and process text for use as filename or folder name.

    Args:
        text: Input text to clean. ``None``/empty values return ``""``.
        max_words: Maximum number of words to keep.
        remove_unwanted: Whether to remove unwanted words.
        lemmatize: Whether to stem words (Snowball English). The parameter name is
            kept for backward compatibility; it now drives deterministic stemming
            rather than NLTK lemmatization.

    Returns:
        Cleaned text with words joined by underscores.
    """
    if not text:
        return ""

    # Remove special characters and numbers
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\d+", "", text)
    text = text.strip()

    # Split concatenated words (camelCase, PascalCase)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

    # Tokenize deterministically (ASCII word tokens, lowercased)
    words = _tokenize(text.lower())

    # Filter alpha-only words (tokenizer already yields alpha tokens; kept for parity)
    words = [word for word in words if word.isalpha()]

    # Stem deterministically via Snowball if requested
    stemmer = _get_stemmer() if lemmatize else None
    if stemmer is not None:
        words = [stemmer.stemWord(word) for word in words]

    # Remove unwanted words and duplicates
    if remove_unwanted:
        unwanted = get_unwanted_words()
        if stemmer is not None:
            # ``words`` were stemmed above, so the unwanted set must be stemmed
            # too — otherwise terms like "image" -> "imag" or "generated" ->
            # "generat" slip past the filter and leak into filenames/folders
            # despite remove_unwanted=True (#1291 Codex review).
            unwanted = {stemmer.stemWord(w) for w in unwanted}
        filtered_words = []
        seen: set[str] = set()

        for word in words:
            if word not in unwanted and word not in seen:
                filtered_words.append(word)
                seen.add(word)

        words = filtered_words

    # Limit to max words
    words = words[:max_words]

    # Join with underscores
    return "_".join(words)


def sanitize_filename(
    name: str,
    max_length: int = 50,
    max_words: int = 5,
) -> str:
    """Sanitize a string for use as a filename.

    Args:
        name: Input name.
        max_length: Maximum length of result.
        max_words: Maximum number of words.

    Returns:
        Sanitized filename.
    """
    # First clean with text processing
    cleaned = clean_text(name, max_words=max_words)

    # If empty after cleaning, provide default
    if not cleaned:
        return "untitled"

    # Remove any remaining non-alphanumeric except underscores
    sanitized = re.sub(r"[^\w]", "_", cleaned)

    # Replace multiple underscores with single
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip("_")

    return sanitized.lower() if sanitized else "untitled"


def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    """Extract the most frequent meaningful words from input text.

    Deterministic, offline implementation: tokenizes with the ASCII tokenizer,
    drops short words (<= 3 chars) and stopwords, and returns the most frequent
    remaining words by descending frequency (ties broken by first appearance).

    Parameters:
        text (str): Text to analyze for keyword extraction.
        top_n (int): Number of top keywords to return.

    Returns:
        list[str]: Top ``top_n`` keywords ordered by frequency; an empty list if no
        keywords are found.
    """
    if not text:
        return []

    # A non-positive ``top_n`` slices ``ranked[:top_n]`` to almost-all keywords
    # (negative index) or an empty list (0); short-circuit to an empty list so
    # the contract ("top N keywords") never returns more than requested.
    if top_n <= 0:
        return []

    words = _tokenize(text.lower())
    words = [w for w in words if len(w) > 3]

    unwanted = get_unwanted_words()
    words = [w for w in words if w not in unwanted]

    if not words:
        return []

    # Make tie-breaking explicit: for equal counts, preserve first appearance order.
    first_seen: dict[str, int] = {}
    for index, word in enumerate(words):
        if word not in first_seen:
            first_seen[word] = index

    word_freq = Counter(words)
    ranked = sorted(word_freq.items(), key=lambda item: (-item[1], first_seen[item[0]]))
    return [word for word, _ in ranked[:top_n]]


def truncate_text(text: str, max_chars: int = 5000) -> str:
    """Truncate text to maximum characters.

    Args:
        text: Input text.
        max_chars: Maximum characters.

    Returns:
        Truncated text.
    """
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."
