"""Protocol definitions for intelligence-layer contracts.

Defines structural interfaces for learners (preference tracking) and
scorers (confidence ranking).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LearnerProtocol(Protocol):
    """Structural contract for preference-learning services.

    Implementations track user choices and recommend future actions
    based on accumulated patterns.
    """

    def track_folder_choice(
        self,
        file_type: str,
        folder: Path,
        context: dict[str, Any] | None = ...,
    ) -> None:
        """Record that *folder* was chosen for *file_type*."""
        ...

    def get_preferred_folder(
        self,
        file_type: str,
        confidence_threshold: float = ...,
    ) -> Path | None:
        """Return the preferred folder for *file_type*, or ``None``."""
        ...


@runtime_checkable
class ScorerProtocol(Protocol):
    """Structural contract for pattern-scoring services.

    Implementations provide score normalization and ranking of scored
    patterns.
    """

    @staticmethod
    def normalize_score(
        score: float,
        min_val: float = ...,
        max_val: float = ...,
    ) -> float:
        """Normalize *score* to a 0-1 range."""
        ...

    @staticmethod
    def rank_patterns(
        patterns: list[Any],
        key: str = ...,
        reverse: bool = ...,
    ) -> list[Any]:
        """Rank patterns by the given key."""
        ...
