"""Protocol definitions for AI model contracts.

Defines structural interfaces for text, vision, and audio models using
``typing.Protocol`` with ``@runtime_checkable``.  Existing ABC-based
implementations (``BaseModel`` subclasses) satisfy these protocols
without any inheritance changes.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TextModelProtocol(Protocol):
    """Structural contract for text-generation models.

    Any class with ``initialize``, ``generate``, ``cleanup``, and the
    ``is_initialized`` property satisfies this protocol — no explicit
    subclassing required.
    """

    @property
    def is_initialized(self) -> bool:
        """Whether the model has been initialized and is ready."""
        ...

    def initialize(self) -> None:
        """Acquire resources and prepare the model for generation."""
        ...

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt."""
        ...

    def cleanup(self) -> None:
        """Release resources held by the model."""
        ...


@runtime_checkable
class VisionModelProtocol(Protocol):
    """Structural contract for vision-language models.

    Extends the basic model lifecycle with optional image inputs
    (``image_path`` or ``image_data``) on ``generate``.
    """

    @property
    def is_initialized(self) -> bool:
        """Whether the model has been initialized and is ready."""
        ...

    def initialize(self) -> None:
        """Acquire resources and prepare the model for generation."""
        ...

    def generate(
        self,
        prompt: str,
        image_path: str | None = ...,
        image_data: bytes | None = ...,
        **kwargs: Any,
    ) -> str:
        """Generate text from a prompt with optional image input."""
        ...

    def cleanup(self) -> None:
        """Release resources held by the model."""
        ...


# AudioModelProtocol shares the exact same structural contract as
# TextModelProtocol (initialize / generate / cleanup / is_initialized).
AudioModelProtocol = TextModelProtocol
