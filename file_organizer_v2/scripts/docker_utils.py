"""Docker helper utilities for File Organizer v2.

Provides functions for validating Dockerfiles, parsing docker-compose
configuration, and estimating Docker image sizes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def validate_dockerfile(path: str | Path) -> list[str]:
    """Validate a Dockerfile for common issues and best practices.

    Performs basic structural validation of a Dockerfile, checking for
    required instructions, security best practices, and common mistakes.

    Args:
        path: Path to the Dockerfile to validate.

    Returns:
        A list of warning/error strings. Empty list means no issues found.

    Raises:
        FileNotFoundError: If the Dockerfile does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dockerfile not found: {path}")

    content = path.read_text()
    lines = content.splitlines()
    issues: list[str] = []

    # Check for at least one FROM instruction
    from_lines = [line for line in lines if line.strip().upper().startswith("FROM ")]
    if not from_lines:
        issues.append("ERROR: No FROM instruction found")

    # Check for latest tag usage (anti-pattern)
    for line in from_lines:
        if ":latest" in line or (
            ":" not in line.split()[-1]
            and " AS " not in line.upper()
            and not line.strip().endswith("AS")
        ):
            # Check if the image reference (after FROM, before AS) has a tag
            parts = line.strip().split()
            if len(parts) >= 2:
                image_ref = parts[1]
                if ":latest" in image_ref:
                    issues.append(
                        f"WARNING: Using ':latest' tag is not recommended: {line.strip()}"
                    )
                elif ":" not in image_ref and "$" not in image_ref:
                    issues.append(
                        f"WARNING: No tag specified (defaults to latest): {line.strip()}"
                    )

    # Check for running as root (no USER instruction)
    has_user = any(
        line.strip().upper().startswith("USER ")
        for line in lines
        if not line.strip().startswith("#")
    )
    if not has_user:
        issues.append("WARNING: No USER instruction found; container will run as root")

    # Check for apt-get update without cleanup
    has_apt_update = any("apt-get update" in line for line in lines)
    has_apt_cleanup = any("rm -rf /var/lib/apt/lists" in line for line in lines)
    if has_apt_update and not has_apt_cleanup:
        issues.append(
            "WARNING: apt-get update without 'rm -rf /var/lib/apt/lists/*' cleanup"
        )

    # Check for HEALTHCHECK
    has_healthcheck = any(
        line.strip().upper().startswith("HEALTHCHECK")
        for line in lines
        if not line.strip().startswith("#")
    )
    if not has_healthcheck:
        issues.append("INFO: No HEALTHCHECK instruction found")

    # Check for EXPOSE
    has_expose = any(
        line.strip().upper().startswith("EXPOSE")
        for line in lines
        if not line.strip().startswith("#")
    )
    if not has_expose:
        issues.append("INFO: No EXPOSE instruction found")

    # Check for secrets in ENV instructions
    secret_pattern = re.compile(
        r"(password|secret|api_key|token)\s*=\s*['\"][^$]", re.IGNORECASE
    )
    for line in lines:
        if line.strip().upper().startswith("ENV ") and secret_pattern.search(line):
            issues.append(
                f"ERROR: Possible hardcoded secret in ENV instruction: {line.strip()}"
            )

    # Check for ADD when COPY would suffice (ADD has extra features like tar extraction)
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("ADD ") and not stripped.startswith("#"):
            # ADD is only preferred for URL downloads or tar extraction
            if "http://" not in stripped and "https://" not in stripped:
                issues.append(
                    f"INFO: Consider using COPY instead of ADD: {stripped}"
                )

    return issues


def parse_docker_compose(path: str | Path) -> dict[str, Any]:
    """Parse a docker-compose YAML file and return its structure.

    Args:
        path: Path to the docker-compose.yml file.

    Returns:
        A dictionary containing the parsed compose file structure.

    Raises:
        FileNotFoundError: If the compose file does not exist.
        ValueError: If the file contains invalid YAML.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Docker compose file not found: {path}")

    content = path.read_text()
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at top level, got {type(data).__name__}")

    return data


def get_image_size_estimate(dockerfile_path: str | Path) -> int:
    """Estimate the Docker image size based on Dockerfile analysis.

    This provides a rough estimate based on the base image and installed
    packages. The actual size will vary based on build context and
    layer caching.

    Estimates are based on typical compressed image sizes:
    - python:3.11-slim: ~150MB
    - python:3.11: ~900MB
    - Alpine-based images: ~50MB
    - Each apt-get install package: ~10-50MB average
    - Python pip packages: ~5-20MB average per package

    Args:
        dockerfile_path: Path to the Dockerfile to analyze.

    Returns:
        Estimated image size in bytes.

    Raises:
        FileNotFoundError: If the Dockerfile does not exist.
    """
    dockerfile_path = Path(dockerfile_path)
    if not dockerfile_path.exists():
        raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")

    content = dockerfile_path.read_text()
    lines = content.splitlines()

    # Base image size estimates (in bytes)
    base_sizes: dict[str, int] = {
        "python:3.11-slim": 150 * 1024 * 1024,  # ~150MB
        "python:3.12-slim": 150 * 1024 * 1024,
        "python:3.10-slim": 150 * 1024 * 1024,
        "python:3.9-slim": 150 * 1024 * 1024,
        "python:3.11": 900 * 1024 * 1024,  # ~900MB
        "python:3.12": 900 * 1024 * 1024,
        "python:3.10": 900 * 1024 * 1024,
        "python:3.9": 900 * 1024 * 1024,
        "alpine": 5 * 1024 * 1024,  # ~5MB
        "ubuntu": 80 * 1024 * 1024,  # ~80MB
        "debian": 120 * 1024 * 1024,  # ~120MB
    }

    # Find the final stage base image (last FROM instruction)
    final_base = ""
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                # Get the image name (ignore AS alias)
                final_base = parts[1]

    # Determine base size
    estimated_size = 0
    for image_name, size in base_sizes.items():
        if image_name in final_base:
            estimated_size = size
            break

    # Default to slim python if no match
    if estimated_size == 0:
        if "slim" in final_base:
            estimated_size = 150 * 1024 * 1024
        elif "alpine" in final_base:
            estimated_size = 50 * 1024 * 1024
        else:
            estimated_size = 200 * 1024 * 1024

    # Estimate apt-get package sizes
    apt_package_size = 25 * 1024 * 1024  # ~25MB per package average
    for line in lines:
        if "apt-get install" in line:
            # Count packages (words after install that don't start with -)
            # Look for continuation lines too
            # Rough count: non-flag arguments after install
            pkg_matches = re.findall(r"\b([a-z][a-z0-9._+-]+)\b", line)
            # Filter out common non-package words
            non_packages = {
                "apt", "get", "install", "update", "rm", "rf", "var",
                "lib", "lists", "no", "recommends", "yes",
                "and", "the", "run", "dev",
            }
            actual_packages = [p for p in pkg_matches if p not in non_packages and len(p) > 2]
            estimated_size += len(actual_packages) * apt_package_size

    # Estimate pip install sizes
    pip_package_size = 15 * 1024 * 1024  # ~15MB per package average
    for line in lines:
        if "pip install" in line:
            # Count non-flag arguments
            pkg_matches = re.findall(r"\b([a-zA-Z][a-zA-Z0-9_-]+)\b", line)
            non_packages = {
                "pip", "install", "no", "cache", "dir", "upgrade",
                "RUN", "run", "from", "requirements", "txt",
            }
            actual_packages = [
                p for p in pkg_matches if p not in non_packages and len(p) > 2
            ]
            estimated_size += len(actual_packages) * pip_package_size

    # Add estimated COPY layer size (application code)
    copy_count = sum(
        1
        for line in lines
        if line.strip().upper().startswith("COPY ")
        and not line.strip().startswith("#")
    )
    estimated_size += copy_count * 5 * 1024 * 1024  # ~5MB per COPY layer average

    return estimated_size
