import os
from typing import List
from typing import Union
from pathlib import Path
from dataclasses import dataclass

from py_walk.exceptions import PyWalkInputError
from py_walk.logs import log
from .pattern import Pattern


@dataclass
class Parser:
    patterns: List[Pattern]
    base_dir: Union[Path, None]

    def __init__(self, glob_pattern_list: List[str], base_dir: Union[Path, None]):
        self.patterns = []
        for glob_pattern in glob_pattern_list:
            log.debug("\n-- Regex building")
            pattern = Pattern(glob_pattern)
            log.debug(f"{pattern}")
            self.patterns.append(pattern)
        self.base_dir = base_dir

    def match(self, path: Union[Path, str]) -> bool:
        # check if path is a directory
        trailing_slash = path.endswith(os.sep) if isinstance(path, str) else False
        if self.base_dir:
            full_path = self.base_dir / Path(path)
            path_is_dir = full_path.is_dir() or trailing_slash
        else:
            path_is_dir = trailing_slash

        # get relative path
        if self.base_dir:
            try:
                relative_path = full_path.relative_to(self.base_dir)
            except ValueError:
                raise PyWalkInputError(
                    f"Error: path '{path}' is not relative to base dir '{self.base_dir}'"
                )
        else:
            relative_path = Path(path)

        # match against each pattern
        matched_patterns: List[int] = []
        log.debug(f"\n-- Matching path: {relative_path} (is_dir: {path_is_dir})")

        for pattern in self.patterns:
            # if no match found, skip negative patterns
            if pattern.negated and not matched_patterns:
                continue

            # check if pattern matches
            matched_parts = pattern.match(relative_path, path_is_dir)
            if matched_parts:
                if pattern.negated:
                    if not (set(matched_patterns) - set(matched_parts)):
                        matched_patterns = []
                else:
                    matched_patterns.extend(matched_parts)
        return bool(matched_patterns)
