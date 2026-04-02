from typing import List


def pattern_text_to_pattern_list(text: str) -> List[str]:
    """Convert gitignore-like text to a list of patterns.

    This function removes empty lines and leading whitespace and
    comments from the text.

    For example:

        # text files
        *.txt
          *.md

        # python files
        __pycache__/
        *.py[cod]

    Produces:

        ["*.txt", "*.md", "__pycache__/", "*.py[cod]"]

    """

    COMMENT_LEADER = "#"

    patterns = []
    for line in text.splitlines():
        # discard non-pattern lines
        clean_line = line.lstrip()
        if not clean_line or clean_line.startswith(COMMENT_LEADER):
            continue

        patterns.append(clean_line)
    return patterns
