"""Backend detector module for AI runtime detection.

Detects installed AI backends (Ollama, local GGUF models, MLX) and
queries available models for the setup wizard.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from loguru import logger

OLLAMA_CLIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    RuntimeError,
    OSError,
)
if OLLAMA_AVAILABLE:
    for _error_name in ("ConnectionError", "ResponseError"):
        _error = getattr(ollama, _error_name, None)
        if isinstance(_error, type) and issubclass(_error, BaseException):
            OLLAMA_CLIENT_EXCEPTIONS += (_error,)


@dataclass
class OllamaStatus:
    """Status of Ollama installation and runtime.

    Args:
        installed: Whether the Ollama CLI is installed.
        running: Whether the Ollama service is running.
        version: Ollama version string, if available.
        models_count: Number of models installed locally.
    """

    installed: bool
    running: bool
    version: str | None = None
    models_count: int = 0


@dataclass
class InstalledModel:
    """Information about an installed Ollama model.

    Args:
        name: Model name/tag (e.g., "qwen2.5:3b-instruct").
        size: Model size in bytes, if available.
        modified: Last modified timestamp, if available.
    """

    name: str
    size: int | None = None
    modified: str | None = None


def detect_ollama() -> OllamaStatus:
    """Detect Ollama installation and runtime status.

    Returns:
        OllamaStatus with installation and runtime information.

    Example:
        >>> status = detect_ollama()
        >>> if status.running:
        ...     print(f"Ollama is running with {status.models_count} models")
    """
    if not OLLAMA_AVAILABLE:
        logger.debug("Ollama Python package not available")
        return OllamaStatus(installed=False, running=False)

    # Check if Ollama CLI is installed
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.debug("Ollama CLI not found or returned error")
            return OllamaStatus(installed=False, running=False)

        version = result.stdout.strip()
        logger.debug("Ollama CLI found: {}", version)

    except FileNotFoundError:
        logger.debug("Ollama CLI not found in PATH")
        return OllamaStatus(installed=False, running=False)
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to check Ollama CLI: {}", e)
        return OllamaStatus(installed=False, running=False)

    # Check if Ollama service is running by trying to list models
    try:
        client = ollama.Client()
        models_response = client.list()

        # Count installed models
        models_count = 0
        if isinstance(models_response, dict) and "models" in models_response:
            models_count = len(models_response["models"])
        elif isinstance(models_response, list):
            models_count = len(models_response)

        logger.debug("Ollama service is running with {} models", models_count)
        return OllamaStatus(
            installed=True,
            running=True,
            version=version,
            models_count=models_count,
        )

    except OLLAMA_CLIENT_EXCEPTIONS as e:
        logger.debug("Ollama service not responding: {}", e)
        return OllamaStatus(
            installed=True,
            running=False,
            version=version,
            models_count=0,
        )


def list_installed_models() -> list[InstalledModel]:
    """List all models installed in Ollama.

    Returns:
        List of InstalledModel objects with model metadata.

    Example:
        >>> models = list_installed_models()
        >>> for model in models:
        ...     print(f"{model.name} - {model.size} bytes")
    """
    if not OLLAMA_AVAILABLE:
        logger.debug("Ollama Python package not available")
        return []

    # Try using the Ollama Python client first
    try:
        client = ollama.Client()
        response = client.list()

        models: list[InstalledModel] = []

        if isinstance(response, dict) and "models" in response:
            for model_data in response["models"]:
                models.append(
                    InstalledModel(
                        name=model_data.get("name", ""),
                        size=model_data.get("size"),
                        modified=model_data.get("modified_at"),
                    )
                )
        elif isinstance(response, list):
            for model_data in response:
                models.append(
                    InstalledModel(
                        name=model_data.get("name", ""),
                        size=model_data.get("size"),
                        modified=model_data.get("modified_at"),
                    )
                )

        logger.debug("Found {} installed models via Ollama client", len(models))
        return models

    except OLLAMA_CLIENT_EXCEPTIONS as e:
        logger.debug("Failed to list models via Ollama client: {}", e)

    # Fallback to CLI
    try:
        result = subprocess.run(
            ["ollama", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            logger.debug("Ollama CLI list command failed, trying text format")
            return _parse_ollama_list_text()

        data = json.loads(result.stdout)
        models: list[InstalledModel] = []

        if isinstance(data, dict) and "models" in data:
            for model_data in data["models"]:
                models.append(
                    InstalledModel(
                        name=model_data.get("name", ""),
                        size=model_data.get("size"),
                        modified=model_data.get("modified_at"),
                    )
                )
        elif isinstance(data, list):
            for model_data in data:
                models.append(
                    InstalledModel(
                        name=model_data.get("name", ""),
                        size=model_data.get("size"),
                        modified=model_data.get("modified_at"),
                    )
                )

        logger.debug("Found {} installed models via Ollama CLI", len(models))
        return models

    except FileNotFoundError:
        logger.debug("Ollama CLI not found")
        return []
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("Failed to list models via CLI: {}", e)
        return _parse_ollama_list_text()


def _parse_ollama_list_text() -> list[InstalledModel]:
    """Fallback parser for ``ollama list`` plain text output.

    Returns:
        List of InstalledModel objects with minimal metadata.
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        models: list[InstalledModel] = []
        for line in result.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                models.append(InstalledModel(name=parts[0]))

        logger.debug("Parsed {} models from text output", len(models))
        return models

    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to parse text output: {}", e)
        return []
