"""Shared fixtures for integration tests.

Integration tests exercise real service instances with only external HTTP
(Ollama / OpenAI clients) mocked.  Mock at ``model.generate()`` level so the
full service → model wiring is exercised.

All fixtures here are available to every ``tests/integration/`` module.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from asgi_lifespan import LifespanManager
from typer.testing import CliRunner

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings
from file_organizer.models.base import BaseModel, ModelConfig, ModelType

# ---------------------------------------------------------------------------
# Deterministic model stubs
# ---------------------------------------------------------------------------

_TEXT_RESPONSES: dict[str, str] = {
    "describe": "A document about software architecture and design patterns.",
    "categorize": "Software Documentation",
    "filename": "Software_Architecture_Guide",
    "default": "Deterministic stub response for integration tests.",
}

_VISION_RESPONSES: dict[str, str] = {
    "describe": "A photograph of a sunset over mountains with orange and purple hues.",
    "categorize": "Nature Photography",
    "filename": "Mountain_Sunset",
    "ocr": "",
    "default": "Deterministic vision stub response.",
}


def _stub_text_generate(prompt: str, **kwargs: Any) -> str:
    """Return a deterministic text response based on prompt keywords."""
    prompt_lower = prompt.lower()
    for key, response in _TEXT_RESPONSES.items():
        if key != "default" and key in prompt_lower:
            return response
    return _TEXT_RESPONSES["default"]


def _stub_vision_generate(prompt: str, **kwargs: Any) -> str:
    """Return a deterministic vision response based on prompt keywords."""
    prompt_lower = prompt.lower()
    for key, response in _VISION_RESPONSES.items():
        if key != "default" and key in prompt_lower:
            return response
    return _VISION_RESPONSES["default"]


# ---------------------------------------------------------------------------
# Model patching fixtures
# ---------------------------------------------------------------------------


def _fake_model_init(self: BaseModel) -> None:
    """Shared fake ``initialize()`` — sets up a mock client and marks ready."""
    self.client = MagicMock()
    with self._lifecycle_lock:
        self._shutting_down = False
        self._initialized = True


@pytest.fixture()
def stub_text_model_init() -> Iterator[None]:
    """Patch ``TextModel.initialize()`` to skip Ollama client setup.

    The model is marked as initialized without creating a real client.
    """
    with patch(
        "file_organizer.models.text_model.TextModel.initialize",
        _fake_model_init,
    ):
        yield


@pytest.fixture()
def stub_text_model_generate() -> Iterator[MagicMock]:
    """Patch ``TextModel._do_generate()`` with deterministic responses.

    Also patches ``_enter_generate`` / ``_exit_generate`` to no-op so the
    lifecycle lock isn't required.
    Trade-off: integration tests stay deterministic and focus on service wiring,
    while lifecycle-lock correctness is covered separately by thread-safety tests.
    """
    with (
        patch(
            "file_organizer.models.text_model.TextModel._do_generate",
            side_effect=_stub_text_generate,
        ) as mock_gen,
        patch(
            "file_organizer.models.text_model.TextModel._enter_generate",
        ),
        patch(
            "file_organizer.models.text_model.TextModel._exit_generate",
        ),
    ):
        yield mock_gen


@pytest.fixture()
def stub_vision_model_init() -> Iterator[None]:
    """Patch ``VisionModel.initialize()`` to skip Ollama client setup."""
    with patch(
        "file_organizer.models.vision_model.VisionModel.initialize",
        _fake_model_init,
    ):
        yield


@pytest.fixture()
def stub_vision_model_generate() -> Iterator[MagicMock]:
    """Patch ``VisionModel._do_generate()`` with deterministic responses.

    Also patches ``_enter_generate`` / ``_exit_generate`` to no-op so the
    lifecycle lock isn't required.
    Trade-off: keeps these tests focused on integration behavior, not model
    lifecycle synchronization internals validated in dedicated unit tests.
    """
    with (
        patch(
            "file_organizer.models.vision_model.VisionModel._do_generate",
            side_effect=_stub_vision_generate,
        ) as mock_gen,
        patch(
            "file_organizer.models.vision_model.VisionModel._enter_generate",
        ),
        patch(
            "file_organizer.models.vision_model.VisionModel._exit_generate",
        ),
    ):
        yield mock_gen


@pytest.fixture()
def stub_all_models(
    stub_text_model_init: None,
    stub_text_model_generate: MagicMock,
    stub_vision_model_init: None,
    stub_vision_model_generate: MagicMock,
) -> None:
    """Convenience fixture: stubs init + generate for both text and vision models."""


@pytest.fixture()
def stub_nltk() -> Iterator[None]:
    """Patch ``ensure_nltk_data()`` to no-op for integration tests."""
    with patch("file_organizer.services.text_processor.ensure_nltk_data"):
        yield


# ---------------------------------------------------------------------------
# Environment isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_env(tmp_path: Path) -> Iterator[None]:
    """Isolate integration tests from real user paths and env vars.

    Sets HOME and XDG_* dirs to per-test temp directories so that
    OperationHistory, ConfigManager, and resolve_legacy_path never
    touch real user data.  Also clears FO_* env vars.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_config = tmp_path / "xdg_config"
    fake_config.mkdir()
    fake_data = tmp_path / "xdg_data"
    fake_data.mkdir()
    fake_state = tmp_path / "xdg_state"
    fake_state.mkdir()

    env_overrides = {
        "HOME": str(fake_home),
        "XDG_CONFIG_HOME": str(fake_config),
        "XDG_DATA_HOME": str(fake_data),
        "XDG_STATE_HOME": str(fake_state),
    }
    # Clear FO_* vars that might leak from the real environment
    env_clears = {
        "FO_PROFILE": "",
        "FO_PROVIDER": "",
    }
    with patch.dict("os.environ", {**env_overrides, **env_clears}, clear=False):
        yield


# ---------------------------------------------------------------------------
# Filesystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def integration_source_dir(tmp_path: Path) -> Path:
    """Temp directory with real files for integration tests.

    Contains ``.txt``, ``.csv``, and ``.md`` files with realistic content.
    """
    src = tmp_path / "source"
    src.mkdir()

    (src / "report.txt").write_text(
        "Quarterly Report Q4 2025\n\n"
        "Revenue increased by 15% compared to the previous quarter.\n"
        "Key drivers include expanded market presence and new product launches.\n"
        "Operating expenses remained stable at $2.3M.\n"
    )
    (src / "data.csv").write_text(
        "date,product,units_sold,revenue\n"
        "2025-10-01,Widget A,150,4500.00\n"
        "2025-10-15,Widget B,89,2670.00\n"
        "2025-11-01,Widget A,200,6000.00\n"
    )
    (src / "notes.md").write_text(
        "# Meeting Notes\n\n"
        "## Action Items\n\n"
        "- Review Q4 projections\n"
        "- Schedule follow-up with engineering\n"
        "- Update roadmap document\n"
    )

    return src


@pytest.fixture()
def integration_output_dir(tmp_path: Path) -> Path:
    """Clean temp output directory for organized files."""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture()
def isolated_config_dir(tmp_path: Path) -> Path:
    """Temp config directory that won't read user's real config.

    Prevents ``ConfigManager`` from picking up ``~/.config/file-organizer/``
    settings during tests.
    """
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def make_text_config(
    name: str = "qwen2.5:3b-instruct-q4_K_M",
    **overrides: Any,
) -> ModelConfig:
    """Build a ``ModelConfig`` for text models with optional overrides."""
    defaults: dict[str, Any] = {
        "name": name,
        "model_type": ModelType.TEXT,
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


def make_vision_config(
    name: str = "qwen2.5vl:7b-q4_K_M",
    **overrides: Any,
) -> ModelConfig:
    """Build a ``ModelConfig`` for vision models with optional overrides."""
    defaults: dict[str, Any] = {
        "name": name,
        "model_type": ModelType.VISION,
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def minimal_png_bytes() -> bytes:
    """Return a structurally valid 1×1 RGB PNG image."""
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR: 1x1, 8-bit RGB
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # IDAT: single red pixel (filter byte 0 + RGB)
    raw = b"\x00\xff\x00\x00"
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    # IEND
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# Error simulation helpers
# ---------------------------------------------------------------------------


@contextmanager
def patch_text_generate(
    side_effect: BaseException | Callable[..., str],
) -> Iterator[MagicMock]:
    """Patch ``TextModel._do_generate`` with a custom *side_effect*.

    Accepts either an exception (raised on every call) or a callable
    (used as the replacement generate function).  Also no-ops the
    lifecycle guards so the lock isn't required.
    """
    with (
        patch(
            "file_organizer.models.text_model.TextModel._do_generate",
            side_effect=side_effect,
        ) as mock_gen,
        patch("file_organizer.models.text_model.TextModel._enter_generate"),
        patch("file_organizer.models.text_model.TextModel._exit_generate"),
    ):
        yield mock_gen


# Keep old name as alias for backward compatibility within this epic
patch_text_generate_error = patch_text_generate


# ---------------------------------------------------------------------------
# FakeTextModel — concrete BaseModel for tests requiring a real instance
# ---------------------------------------------------------------------------


class FakeTextModel(BaseModel):
    """Concrete ``BaseModel`` subclass that never calls external services.

    ``generate()`` returns deterministic responses keyed on prompt keywords,
    matching the existing ``_TEXT_RESPONSES`` mapping so tests that use
    ``FakeTextModel`` produce the same output as the patch-based stubs.

    Use this fixture when a test needs to pass a real model *instance* (not a
    patch) to a service — for example when testing model lifecycle, context
    managers, or provider abstractions that inspect the object directly.
    """

    def initialize(self) -> None:
        """Set ``_initialized = True`` via the base-class lifecycle lock."""
        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Return a deterministic response without calling any external service."""
        self._enter_generate()
        try:
            return _stub_text_generate(prompt, **kwargs)
        finally:
            self._exit_generate()

    def cleanup(self) -> None:
        """Mark model as shut down so subsequent ``generate()`` calls raise."""
        with self._lifecycle_lock:
            self._shutting_down = True
            self._initialized = False


@pytest.fixture()
def fake_text_model() -> FakeTextModel:
    """Pre-initialized ``FakeTextModel`` ready for ``generate()`` calls.

    Use when a test requires a concrete model instance rather than a patch,
    e.g. for testing provider abstractions or lifecycle methods.
    """
    model = FakeTextModel(make_text_config())
    model.initialize()
    return model


# ---------------------------------------------------------------------------
# CLI runner fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_runner() -> CliRunner:
    """``typer.testing.CliRunner`` for invoking CLI commands in tests.

    Provides per-test isolation: each fixture invocation returns a fresh
    runner so that ``mix_stderr`` state and environment overrides do not
    leak between tests.
    """
    return CliRunner()


# ---------------------------------------------------------------------------
# Full-stack AsyncClient fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def async_client(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient, None]:
    """``httpx.AsyncClient`` wired to the full FastAPI app via ASGI transport.

    Auth is disabled so routes do not require a JWT token.  Use this fixture
    when testing API routers, web routes, or any endpoint that requires the
    full application stack (middleware, exception handlers, dependency graph).

    The app is created fresh per test using ``tmp_path`` for the auth database
    so tests are fully isolated.  ``LifespanManager`` ensures ASGI
    startup/shutdown events fire so any lifespan-registered resources are
    properly initialised and torn down.
    """

    settings = build_test_settings(tmp_path, auth_overrides={"auth_enabled": False})
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
