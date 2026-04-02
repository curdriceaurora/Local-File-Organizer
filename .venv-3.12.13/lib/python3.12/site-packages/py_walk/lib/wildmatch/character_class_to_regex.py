# mypy: disable-error-code="name-defined"
import re

from sly import Lexer

from py_walk.logs import log


class CCLexer(Lexer):
    tokens = {  # noqa
        NEGATED_START_BRACKET,  # noqa
        NEGATED_START,  # noqa
        BARE_START_BRACKET,  # noqa
        BARE_START,  # noqa
        CLASS_EMPTY,  # noqa
        CLASS_ALNUM,  # noqa
        CLASS_ALPHA,  # noqa
        CLASS_BLANK,  # noqa
        CLASS_CNTRL,  # noqa
        CLASS_DIGIT,  # noqa
        CLASS_GRAPH,  # noqa
        CLASS_LOWER,  # noqa
        CLASS_PRINT,  # noqa
        CLASS_PUNCT,  # noqa
        CLASS_SPACE,  # noqa
        CLASS_UPPER,  # noqa
        CLASS_XDIGIT,  # noqa
        RANGE,  # noqa
        ESC,  # noqa
        END,  # noqa
        CHAR,  # noqa
    }

    NEGATED_START_BRACKET = r"^\[(!|\^)\]"
    NEGATED_START = r"^\[(!|\^)"
    BARE_START_BRACKET = r"^\[\]"
    BARE_START = r"^\["
    CLASS_EMPTY = r"\[::\]"
    CLASS_ALNUM = r"\[:alnum:\]"
    CLASS_ALPHA = r"\[:alpha:\]"
    CLASS_BLANK = r"\[:blank:\]"
    CLASS_CNTRL = r"\[:cntrl:\]"
    CLASS_DIGIT = r"\[:digit:\]"
    CLASS_GRAPH = r"\[:graph:\]"
    CLASS_LOWER = r"\[:lower:\]"
    CLASS_PRINT = r"\[:print:\]"
    CLASS_PUNCT = r"\[:punct:\]"
    CLASS_SPACE = r"\[:space:\]"
    CLASS_UPPER = r"\[:upper:\]"
    CLASS_XDIGIT = r"\[:xdigit:\]"
    RANGE = r"(\\.|.)-(\\.|.)"
    ESC = r"\\."
    END = r"\]$"
    CHAR = r"."


cc_lexer = CCLexer()

regex_map = {
    "NEGATED_START_BRACKET": r"[^\]",
    "NEGATED_START": r"[^",
    "BARE_START_BRACKET": r"[\]",
    "BARE_START": r"[",
    "CLASS_ALNUM": r"a-zA-Z0-9",
    "CLASS_ALPHA": r"a-zA-Z",
    "CLASS_BLANK": r" \t",
    "CLASS_CNTRL": r"\x00-\x1F\x7F",
    "CLASS_DIGIT": r"0-9",
    "CLASS_GRAPH": r"\x21-\x7E",
    "CLASS_LOWER": r"a-z",
    "CLASS_PRINT": r"\x20-\x7E",
    "CLASS_PUNCT": r"!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~",
    "CLASS_SPACE": r" \t\r\n\v\f",
    "CLASS_UPPER": r"A-Z",
    "CLASS_XDIGIT": r"A-Fa-f0-9",
    "END": r"]",
}


def validate_range(range_text):
    """Return the range itself if valid or empty string otherwise.

    Invalid ranges are ignored in wildmatch, while they through an error
    in regular expressions. This function guarantees that the rest of the
    character class expression is still evaluated evaluated even if the
    range is invalid.
    """
    if range_text[0] == "\\":
        range_text = re.escape(range_text[1]) + range_text[2:]
    if range_text[-2] == "\\":
        range_text = range_text[:-2] + re.escape(range_text[-1])
    if range_text.startswith(("^", "!")):
        # characters 'a' and 'z' ensure that the range
        # is considered in a middle position (eg. '^' would be
        # considered as a special character right after '['
        test_range_text = f"[a{range_text}z]"
    else:
        test_range_text = f"[{range_text}]"

    try:
        _ = re.compile(test_range_text)
    except Exception:
        return ""

    return range_text


def character_class_to_regex(text: str) -> str:
    tokens = cc_lexer.tokenize(text)
    regex = ""
    for token in tokens:
        log.debug(f"- cc token: {token.type} ({token.value})")
        if token.type == "CHAR":
            regex += token.value
        elif token.type == "ESC":
            regex += re.escape(token.value[1:])
        elif token.type == "RANGE":
            regex += validate_range(token.value)
        elif token.type == "CLASS_EMPTY":
            return "(?!)"
        else:
            regex += regex_map.get(token.type, token.value)
    return regex
