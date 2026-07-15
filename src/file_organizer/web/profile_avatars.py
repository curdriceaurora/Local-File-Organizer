"""Avatar path validation helpers for the web profile UI."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from file_organizer.utils.safedir import SafeDir, SymlinkRejected

# Strict pattern for user IDs: ASCII alphanumeric, hyphens, underscores, dots only.
SAFE_USER_ID = re.compile(r"^[\w.\-]+$", re.ASCII)


def avatar_path(user_id: str, avatar_dir: Path) -> Path:
    """Return the filesystem path where the user's avatar is stored.

    Raises:
        ValueError: If user_id contains path-traversal characters or is empty.
    """
    if not user_id or not SAFE_USER_ID.match(user_id):
        raise ValueError(f"Invalid user_id: {user_id!r}")
    result = avatar_dir / f"{user_id}.png"
    if not result.resolve().is_relative_to(avatar_dir.resolve()):
        raise ValueError(f"Invalid user_id: {user_id!r}")
    return result


def resolve_avatar_for_read(
    user_id: str,
    avatar_dir: Path,
    *,
    path_factory: Callable[[str], Path] | None = None,
    safe_dir_open: Callable[[Path], AbstractContextManager[SafeDir]] = SafeDir.open_root,
) -> Path:
    """Return a validated avatar path that is safe to serve."""
    candidate_path = path_factory(user_id) if path_factory else avatar_path(user_id, avatar_dir)
    avatar_name = candidate_path.name
    avatar_root = avatar_dir.resolve()
    candidate = avatar_root / avatar_name

    try:
        with safe_dir_open(avatar_root) as safe_dir:
            fd = safe_dir.open_for_reader(avatar_name)
    except NotImplementedError:  # pragma: no cover - Windows fallback
        avatar_root_str = str(avatar_root)
        candidate_str = os.path.normpath(str(candidate))
        if not candidate_str.startswith(f"{avatar_root_str}{os.sep}"):
            raise FileNotFoundError("Avatar not found") from None
        if not os.path.isfile(candidate_str):
            raise FileNotFoundError("Avatar not found") from None
        return candidate
    except (FileNotFoundError, SymlinkRejected) as exc:
        raise FileNotFoundError("Avatar not found") from exc
    else:
        os.close(fd)
    return candidate
