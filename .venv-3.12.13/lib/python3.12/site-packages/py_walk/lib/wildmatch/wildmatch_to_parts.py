# mypy: disable-error-code="name-defined"
import re
from typing import List
from typing import Union

from sly import Lexer

from .glob_to_regex import glob_to_regex

NO_MATCH_REGEX = re.compile("(?!)")


class WildmatchLexer(Lexer):
    tokens = {  # noqa
        DOUBLE_STAR,  # noqa
        SLASH,  # noqa
        GLOB,  # noqa
    }

    DOUBLE_STAR = r"(^(\*\*/)+)|((/\*\*)+$)|((/\*\*)+/)"
    SLASH = r"/"
    GLOB = r"[^/]+"


wildmatch_lexer = WildmatchLexer()


def wildmatch_to_parts(pattern: str) -> List[Union[re.Pattern, None]]:
    tokens = list(wildmatch_lexer.tokenize(pattern))
    parts: List[Union[re.Pattern, None]] = []
    for token in tokens:
        if token.type == "DOUBLE_STAR":
            parts.append(None)
        elif token.type == "GLOB":
            try:
                regex = glob_to_regex(token.value)
            except Exception:
                regex = NO_MATCH_REGEX
            parts.append(regex)
        else:
            # do nothing for SLASH
            pass

    # remove trailing double stars
    while parts and parts[-1] is None:
        parts.pop()

    # normalize patterns with one single element ('a' -> '**/a')
    if len(parts) == 1 and not tokens[0].type == "SLASH":
        parts.insert(0, None)
    elif len(parts) == 0:
        parts.append(re.compile(r"[^/]*"))

    return parts
