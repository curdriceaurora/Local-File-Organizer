"""Undo/redo functionality for file operations.

This module provides comprehensive undo/redo capabilities for file operations,
including validation, rollback execution, and history viewing.
"""

from __future__ import annotations

from .models import Conflict, ConflictType, RollbackResult, ValidationResult
from .rollback import RollbackExecutor
from .undo_manager import UndoManager
from .validator import OperationValidator
from .viewer import HistoryViewer

__all__ = [
    "ValidationResult",
    "RollbackResult",
    "Conflict",
    "ConflictType",
    "OperationValidator",
    "RollbackExecutor",
    "UndoManager",
    "HistoryViewer",
]

__version__ = "1.0.0"
