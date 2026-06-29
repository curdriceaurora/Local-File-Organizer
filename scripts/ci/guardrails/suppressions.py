"""Shared suppression parsing helpers for CI guardrails."""

from __future__ import annotations

import io
import re
import tokenize


def _comment_tokens(line_content: str) -> list[str]:
    """Return actual Python comment tokens from one source line."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line_content).readline)
        return [token.string for token in tokens if token.type == tokenize.COMMENT]
    except (IndentationError, tokenize.TokenError):
        comment = _manual_comment_token(line_content)
        return [comment] if comment else []


def _manual_comment_token(line_content: str) -> str | None:
    """Find a comment marker outside simple string literals on incomplete lines."""
    quote: str | None = None
    triple_quote: str | None = None
    escaped = False

    for idx, char in enumerate(line_content):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue

        if triple_quote is not None:
            if line_content.startswith(triple_quote, idx):
                triple_quote = None
            continue

        if quote is not None:
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            if line_content.startswith(char * 3, idx):
                triple_quote = char * 3
            else:
                quote = char
            continue

        if char == "#":
            return line_content[idx:]

    return None


def has_targeted_noqa(line_content: str, rail_name: str) -> bool:
    """Return True when an inline comment has ``noqa`` for ``rail_name``.

    The parser only inspects COMMENT tokens, so strings such as
    ``"noqa: rail-name"`` never suppress a violation.
    """
    target = rail_name.lower()
    for comment in _comment_tokens(line_content):
        body = comment.lstrip("#").strip()
        for match in re.finditer(r"(?:^|#|\s)noqa\s*:\s*([^#]+)", body, flags=re.IGNORECASE):
            code_list = match.group(1)
            for raw_code in code_list.split(","):
                code = raw_code.strip().split(maxsplit=1)[0].lower()
                if code == target:
                    return True
    return False


def has_comment_marker(line_content: str, marker: str) -> bool:
    """Return True when an exact marker appears in an actual comment token."""
    target = marker.lower()
    return any(target in comment.lower() for comment in _comment_tokens(line_content))
