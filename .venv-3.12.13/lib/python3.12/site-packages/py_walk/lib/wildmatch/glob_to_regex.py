# mypy: disable-error-code="name-defined"
import re

from sly import Lexer

from py_walk.logs import log
from .character_class_to_regex import character_class_to_regex


class GlobLexer(Lexer):
    tokens = {  # noqa
        ESC,  # noqa
        CHARACTER_CLASS,  # noqa
        QUESTION_MARK,  # noqa
        STAR,  # noqa
        TEXT,  # noqa
    }

    ESC = r"\\."
    CHARACTER_CLASS = (
        r"\[(\^|!)?\]?-?"
        r"("
        r"\[:[a-z]*:\]|"
        r"(\\.|.)-(\\.|.)|"
        r"(\\.|[^]])"
        r")*"
        r"\]"
    )
    QUESTION_MARK = r"\?"
    STAR = r"\*"
    TEXT = r"[^[*?\\]+"


glob_lexer = GlobLexer()

regex_map = {
    "QUESTION_MARK": r".",
    "STAR": r"[^/]*",
}


def glob_to_regex(glob_pattern: str) -> re.Pattern:
    tokens = glob_lexer.tokenize(glob_pattern)
    regex = ""
    for token in tokens:
        log.debug(f"- token: {token.type} ({token.value})")
        if token.type == "TEXT":
            regex += re.escape(token.value)
        elif token.type == "ESC":
            regex += re.escape(token.value[1:])
        elif token.type == "CHARACTER_CLASS":
            regex += character_class_to_regex(token.value)
        else:
            regex += regex_map.get(token.type, token.value)
    return re.compile(regex)
