from typing import List
from typing import Union
from typing import Callable
from typing import Generator
from pathlib import Path

from py_walk.exceptions import PyWalkInputError
from .get_parser_from_list import get_parser_from_list
from .get_parser_from_text import get_parser_from_text


def walk(
    base_dir: Union[Path, str],
    ignore: Union[str, List[str], None] = None,
    match: Union[str, List[str], None] = None,
    mode: str = "files-and-dirs",
) -> Generator[Path, None, None]:
    """Return all the children under a given path that match the provided filters.

    :param base_dir: directory to walk.
    :param ignore: ignore all paths matching these patterns (set to None to not ignore any path).
    :param match: include only the non-ignored paths matching these patterns (when None, all paths are returned).
    :param mode: only-files | only-dirs | files-and-dirs
    """

    # normalize path to Path
    if isinstance(base_dir, str):
        base_dir = Path(base_dir)
    if not base_dir.is_dir():
        raise PyWalkInputError(f"Not a directory: '{base_dir}'")

    # validate mode
    if mode not in ("only-files", "only-dirs", "files-and-dirs"):
        raise PyWalkInputError(
            "'mode' must be one of: 'only-files', 'only-dirs' or 'files-and-dirs' (default)."
        )

    # get ignore parser
    if isinstance(ignore, str):
        ignore_parser = get_parser_from_text(ignore, base_dir).match
    elif isinstance(ignore, list):
        ignore_parser = get_parser_from_list(ignore, base_dir).match
    elif ignore is None:
        ignore_parser = lambda path: False
    else:
        raise PyWalkInputError("'ignore' must be a string or a list of patterns")

    # get include parser
    if isinstance(match, str):
        match_parser = get_parser_from_text(match, base_dir).match
    elif isinstance(match, list):
        match_parser = get_parser_from_list(match, base_dir).match
    elif match is None:
        match_parser = lambda path: True
    else:
        raise PyWalkInputError("'match' must be a string or a list of patterns")

    # walk children
    for child in base_dir.iterdir():
        yield from walk_rec(child, ignore_parser, match_parser, mode)


def walk_rec(
    path: Path,
    ignore_parser: Callable[[Path], bool],
    match_parser: Callable[[Path], bool],
    mode: str,
) -> Generator[Path, None, None]:
    if not ignore_parser(path):
        path_is_dir = path.is_dir()
        if match_parser(path):
            if (
                mode == "files-and-dirs"
                or (mode == "only-files" and not path_is_dir)
                or (mode == "only-dirs" and path_is_dir)
            ):
                yield path
        if path_is_dir:
            for child in path.iterdir():
                yield from walk_rec(child, ignore_parser, match_parser, mode)
