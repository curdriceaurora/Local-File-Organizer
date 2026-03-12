"""Protocol definitions for composable pipeline stages.

Defines the ``PipelineStage`` protocol and ``StageContext`` dataclass
that enable the orchestrator to compose independent processing stages
into a configurable pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class StageContext:
    """Data carrier passed through pipeline stages.

    Each stage reads from and writes to the context, building up
    the processing result incrementally.  The context is created
    once per file and flows through all stages in order.

    Attributes:
        file_path: Original path of the file being processed.
        metadata: File metadata extracted during preprocessing
            (size, extension, mime type, etc.).
        analysis: Results from the analyzer stage (category,
            description, suggested filename, etc.).
        destination: Final destination path computed by the
            postprocessor stage.
        category: Folder/category name assigned to the file.
            Validated on every assignment to reject traversal sequences.
        filename: Suggested filename (without extension).
            Validated on every assignment — same rules as *category*.
        dry_run: Whether this is a simulation (no file moves).
        error: Error message if a stage fails, ``None`` otherwise.
        extra: Arbitrary per-stage data that doesn't fit the
            fixed fields.  Stages should namespace their keys
            (e.g. ``"analyzer.confidence"``).
    """

    file_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    destination: Path | None = None
    category: str = ""
    filename: str = ""
    dry_run: bool = True
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _validate_path_component(field_name: str, value: str) -> str:
        """Reject traversal sequences and separators in a path component."""
        if value and (".." in value or "/" in value or "\\" in value):
            raise ValueError(f"Invalid {field_name}: {value!r}")
        return value

    def __setattr__(self, name: str, value: object) -> None:
        """Validate ``category`` and ``filename`` on every assignment."""
        if name in ("category", "filename") and isinstance(value, str):
            value = self._validate_path_component(name, value)
        object.__setattr__(self, name, value)

    @property
    def failed(self) -> bool:
        """Return ``True`` if a stage has recorded an error."""
        return self.error is not None


@runtime_checkable
class PipelineStage(Protocol):
    """Structural contract for a composable pipeline stage.

    Each stage receives a :class:`StageContext`, performs its work,
    and returns the (possibly mutated) context.  Stages may set
    ``context.error`` to signal failure; subsequent stages can
    choose to skip processing when ``context.failed`` is ``True``.

    Attributes:
        name: Human-readable identifier for logging and config.
    """

    @property
    def name(self) -> str:
        """Human-readable stage identifier."""
        ...

    def process(self, context: StageContext) -> StageContext:
        """Execute this stage's logic on *context*.

        Args:
            context: The pipeline context to read from and write to.

        Returns:
            The same context instance (mutated in place) or a new one.
        """
        ...
