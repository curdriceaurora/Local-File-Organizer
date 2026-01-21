"""
Undo/redo functionality for file operations.

This module provides comprehensive undo/redo capabilities for file operations,
including validation, rollback execution, and history viewing.
"""

from .models import ValidationResult, RollbackResult, Conflict, ConflictType
from .validator import OperationValidator
from .rollback import RollbackExecutor
from .undo_manager import UndoManager
from .viewer import HistoryViewer

__all__ = [
    'ValidationResult',
    'RollbackResult',
    'Conflict',
    'ConflictType',
    'OperationValidator',
    'RollbackExecutor',
    'UndoManager',
    'HistoryViewer',
]

__version__ = '1.0.0'
