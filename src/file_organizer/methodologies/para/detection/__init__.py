"""PARA Detection Module.

Heuristic-based detection algorithms for automatically categorizing files
into PARA categories (Projects, Areas, Resources, Archive).
"""

from __future__ import annotations

from .heuristics import (
    AIHeuristic,
    CategoryScore,
    ContentHeuristic,
    HeuristicEngine,
    HeuristicResult,
    StructuralHeuristic,
    TemporalHeuristic,
)

__all__ = [
    "HeuristicEngine",
    "TemporalHeuristic",
    "ContentHeuristic",
    "StructuralHeuristic",
    "AIHeuristic",
    "HeuristicResult",
    "CategoryScore",
]
