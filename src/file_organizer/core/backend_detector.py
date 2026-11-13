# pyre-ignore-all-errors
"""Backend detector module for AI runtime detection.

Detects installed AI backends (Ollama, local GGUF models, MLX) and
queries available models for the setup wizard.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field

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

    installed: bool  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    running: bool  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    version: str | None = None  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    models_count: int = 0  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.


@dataclass
class InstalledModel:
    """Information about an installed Ollama model.

    Args:
        name: Model name/tag (e.g., "qwen2.5:3b-instruct").
        size: Model size in bytes, if available.
        modified: Last modified timestamp, if available.
    """

    name: str  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    size: int | None = None  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    modified: str | None = None  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.


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

    # Check if Ollama CLI is installed (optional — service may run remotely or in Docker)
    cli_installed = False
    version: str | None = None
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            cli_installed = True
            version = result.stdout.strip()
            logger.debug("Ollama CLI found: {}", version)
        else:
            logger.debug("Ollama CLI not found or returned error")
    except FileNotFoundError:
        logger.debug("Ollama CLI not found in PATH — will still probe service endpoint")
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("Failed to check Ollama CLI: {}", e)

    # Check if Ollama service is running by trying to list models.
    # Respects OLLAMA_HOST env var (set e.g. to http://host.docker.internal:11434
    # when running inside Docker so the client reaches the host machine).
    try:
        client = ollama.Client()
        models_response = client.list()

        # Count installed models — handle dict, list, and ListResponse object
        models_count = 0
        if isinstance(models_response, dict) and "models" in models_response:
            models_count = len(models_response["models"])
        elif isinstance(models_response, list):
            models_count = len(models_response)
        elif hasattr(models_response, "models"):
            models_count = len(models_response.models)

        logger.debug("Ollama service is running with {} models", models_count)
        return OllamaStatus(
            installed=True,  # service reachable implies Ollama is present
            running=True,
            version=version,
            models_count=models_count,
        )

    except OLLAMA_CLIENT_EXCEPTIONS as e:
        logger.debug("Ollama service not responding: {}", e)
        return OllamaStatus(
            installed=cli_installed,
            running=False,
            version=version,
            models_count=0,
        )


@dataclass
class EndpointStatus:
    """Status of an OpenAI-compatible endpoint (OpenAI, LM Studio, vLLM, ...).

    Args:
        base_url: Endpoint base URL that was probed.
        reachable: Whether ``GET {base_url}/models`` succeeded.
        models: Model ids reported by the endpoint.
        error: Human-readable failure reason when not reachable.
    """

    base_url: str  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    reachable: bool  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.
    models: list[str] = field(default_factory=list)  # pyre-ignore[35]
    error: str | None = None  # pyre-ignore[35]: Pyre 0.9.25 dataclass false positive.


def detect_openai_endpoint(
    base_url: str | None,
    api_key: str | None,
    timeout: float = 5.0,
) -> EndpointStatus:
    """Probe an OpenAI-compatible endpoint by listing its models.

    Args:
        base_url: Endpoint base URL; defaults to the public OpenAI API.
        api_key: Bearer token, if the endpoint requires one.
        timeout: Request timeout in seconds.

    Returns:
        EndpointStatus describing reachability and available models.
    """
    base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
    request = urllib.request.Request(f"{base_url}/models")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            reason = (
                "endpoint rejected the API key"
                if api_key
                else "endpoint requires an API key; set FO_OPENAI_API_KEY"
            )
        else:
            reason = f"HTTP {e.code} from {base_url}/models"
        return EndpointStatus(base_url=base_url, reachable=False, error=reason)
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", None) or e
        return EndpointStatus(
            base_url=base_url, reachable=False, error=f"cannot reach {base_url}: {reason}"
        )

    data = payload.get("data", []) if isinstance(payload, dict) else []
    models = [str(m["id"]) for m in data if isinstance(m, dict) and "id" in m]
    logger.debug("OpenAI-compatible endpoint {} lists {} models", base_url, len(models))
    return EndpointStatus(base_url=base_url, reachable=True, models=models)


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

        # Normalise to a flat iterable — handles dict, list, and ListResponse object
        if isinstance(response, dict) and "models" in response:
            raw_models = response["models"]
        elif isinstance(response, list):
            raw_models = response
        elif hasattr(response, "models"):
            raw_models = response.models
        else:
            raw_models = []

        for model_data in raw_models:
            if hasattr(model_data, "model"):
                # ollama.Model dataclass
                models.append(
                    InstalledModel(
                        name=model_data.model,
                        size=getattr(model_data, "size", None),
                        modified=str(getattr(model_data, "modified_at", None)),
                    )
                )
            else:
                # plain dict fallback
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
        # Accepted fire-and-forget: non-zero exit leaves stdout empty or
        # truncated, so the loop below silently yields [] — the correct
        # fallback.  returncode is intentionally not checked here.
        result = subprocess.run(  # noqa: subprocess-returncode
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
