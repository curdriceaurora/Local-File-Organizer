"""
Operation history tracking module.

This module provides comprehensive operation history tracking for file operations,
including database management, transaction support, cleanup, and export functionality.
"""

from __future__ import annotations

from .cleanup import HistoryCleanup, HistoryCleanupConfig
from .database import DatabaseManager
from .export import HistoryExporter
from .models import Operation, OperationStatus, OperationType, Transaction, TransactionStatus
from .tracker import OperationHistory
from .transaction import OperationTransaction

__all__ = [
    "DatabaseManager",
    "Operation",
    "Transaction",
    "OperationType",
    "OperationStatus",
    "TransactionStatus",
    "OperationHistory",
    "OperationTransaction",
    "HistoryCleanup",
    "HistoryCleanupConfig",
    "HistoryExporter",
]

__version__ = "1.0.0"
