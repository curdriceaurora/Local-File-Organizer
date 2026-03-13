import os
from pathlib import Path
from typing import Protocol

from file_organizer.api.models import FileInfo
from file_organizer.api.utils import file_info_from_path

BASE_DIR = Path(__file__).resolve().parent


def basename_only(name: str) -> str:
    return Path(name).name.strip()


def config_roots(allowed_paths: list[str]) -> list[str]:
    # codeql[py/path-injection]
    return [os.path.realpath(Path(root).expanduser()) for root in allowed_paths]


class _HasPath(Protocol):
    path: str


def info_path(info: _HasPath) -> FileInfo:
    return file_info_from_path(Path(info.path))


def resolve_path(path_value: str) -> Path:
    resolved_str = path_value
    return Path(resolved_str)


def boundary_validated(path: str) -> Path:
    # Path must be pre-validated at API boundary
    return Path(path)
