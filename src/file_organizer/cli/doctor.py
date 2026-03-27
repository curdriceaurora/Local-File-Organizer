"""Doctor command for detecting file types and recommending optional dependencies.

This module provides functionality to scan directories for file types and recommend
which optional dependency groups should be installed based on detected file types.
"""

import importlib.util
from typing import Dict, List, Set

# Extension-to-group registry mapping file extensions to optional dependency groups
EXTENSION_REGISTRY: Dict[str, str] = {
    # Audio files
    ".mp3": "audio",
    ".wav": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".wma": "audio",
    ".aac": "audio",
    ".opus": "audio",
    # Video files
    ".mp4": "video",
    ".avi": "video",
    ".mkv": "video",
    ".mov": "video",
    ".wmv": "video",
    ".webm": "video",
    # Document parsers
    ".pdf": "parsers",
    ".docx": "parsers",
    ".xlsx": "parsers",
    ".pptx": "parsers",
    ".epub": "parsers",
    ".html": "parsers",
    # Archive files
    ".7z": "archive",
    ".rar": "archive",
    # Scientific data files
    ".hdf5": "scientific",
    ".h5": "scientific",
    ".nc": "scientific",
    ".mat": "scientific",
    # CAD files
    ".dxf": "cad",
    ".dwg": "cad",
}

# Dependency check packages - maps groups to representative packages to check
DEPENDENCY_CHECK_PACKAGES: Dict[str, str] = {
    "audio": "faster_whisper",
    "video": "cv2",
    "parsers": "fitz",
    "archive": "py7zr",
    "scientific": "h5py",
    "cad": "ezdxf",
    "dedup": "imagededup",
}

# System prerequisites for optional groups
SYSTEM_PREREQUISITES: Dict[str, List[str]] = {
    "audio": ["FFmpeg (required)", "CUDA GPU (optional, for acceleration)"],
    "archive": ["unrar tool (required for RAR files)"],
}


def is_group_installed(group: str) -> bool:
    """Check if an optional dependency group is installed.

    Uses importlib.util.find_spec() for non-destructive checking.

    Args:
        group: The name of the optional dependency group

    Returns:
        True if the group's representative package is installed, False otherwise
    """
    package_name = DEPENDENCY_CHECK_PACKAGES.get(group)
    if not package_name:
        return False

    spec = importlib.util.find_spec(package_name)
    return spec is not None


def get_groups_for_extensions(extensions: Set[str]) -> Set[str]:
    """Get the set of dependency groups needed for the given file extensions.

    Args:
        extensions: Set of file extensions (with leading dot, e.g., '.mp3')

    Returns:
        Set of dependency group names
    """
    groups = set()
    for ext in extensions:
        # Normalize extension to lowercase
        ext_lower = ext.lower()
        if ext_lower in EXTENSION_REGISTRY:
            groups.add(EXTENSION_REGISTRY[ext_lower])
    return groups


def get_missing_groups(detected_groups: Set[str]) -> Set[str]:
    """Filter detected groups to only those not already installed.

    Args:
        detected_groups: Set of detected dependency group names

    Returns:
        Set of group names that are not installed
    """
    return {group for group in detected_groups if not is_group_installed(group)}
