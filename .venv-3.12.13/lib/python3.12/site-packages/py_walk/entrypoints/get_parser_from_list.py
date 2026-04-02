from typing import List
from typing import Union
from pathlib import Path

from py_walk.models import Parser


def get_parser_from_list(
    pattern_list: List[str], base_dir: Union[Path, str, None] = None
) -> Parser:
    """Create a PatternCollection object from a list of patterns."""

    # normalize base_dir to Path
    if isinstance(base_dir, str):
        base_dir = Path(base_dir)

    return Parser(pattern_list, base_dir)
