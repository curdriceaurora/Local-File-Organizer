"""
PARA Detection Module

Heuristic-based detection algorithms for automatically categorizing files
into PARA categories (Projects, Areas, Resources, Archive).
"""

from .heuristics import (
    HeuristicEngine,
    TemporalHeuristic,
    ContentHeuristic,
    StructuralHeuristic,
    AIHeuristic,
    HeuristicResult,
    CategoryScore,
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
