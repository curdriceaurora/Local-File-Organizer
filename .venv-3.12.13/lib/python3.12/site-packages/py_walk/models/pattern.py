import re
from typing import List
from typing import Union
from pathlib import Path
from dataclasses import field
from dataclasses import dataclass

from py_walk.lib.wildmatch import wildmatch_match
from py_walk.lib.wildmatch import wildmatch_to_parts

TRAILING_WHITESPACE_REGEX = re.compile(r"(?<!\\)\s*$")


@dataclass
class Pattern:
    glob: str
    parts: List[Union[re.Pattern, None]] = field(init=False)
    negated: bool = False
    is_dir: bool = False

    def __post_init__(self):
        inner_glob = self.glob

        # remove trailing whitespace
        trailing_whitespace = TRAILING_WHITESPACE_REGEX.search(inner_glob)
        if trailing_whitespace:
            inner_glob = inner_glob[: trailing_whitespace.start()]

        # check negation prefix (!)
        if self.glob.startswith("!"):
            self.negated = True
            inner_glob = self.glob[1:]

        # parse final slash
        if self.glob.endswith(("/", "/**")):
            self.is_dir = True

        # get parts
        self.parts = wildmatch_to_parts(inner_glob)

    def match(self, path: Path, is_dir: bool) -> List[int]:
        if self.parts is None:
            return False
        path_parts = list(path.parts)
        num_part_list = wildmatch_match(path_parts, self.parts)
        # check directory parttern
        if (
            num_part_list
            and min(num_part_list) == len(path_parts)
            and (self.is_dir and not is_dir)
        ):
            return []
        return num_part_list

    def __str__(self):
        return (
            f"Glob: {self.glob} Parts: {[(part.pattern if part else '_') for part in self.parts]}"
            f"{ ' (negated)' if self.negated else ''}"
        )
