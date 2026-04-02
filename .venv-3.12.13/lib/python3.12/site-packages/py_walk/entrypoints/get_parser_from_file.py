from typing import Union
from pathlib import Path

from py_walk.models import Parser
from .get_parser_from_text import get_parser_from_text


def get_parser_from_file(path: Union[Path, str]) -> Parser:
    """Create a Parser object from a gitignore-type file."""

    # normalize path to Path
    if isinstance(path, str):
        path = Path(path)

    text = path.read_text()
    base_dir = path.parent
    return get_parser_from_text(text, base_dir=base_dir)
