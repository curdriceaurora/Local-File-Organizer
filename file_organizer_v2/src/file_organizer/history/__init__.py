"""
Operation history tracking module.

This module provides comprehensive operation history tracking for file operations,
including database management, transaction support, cleanup, and export functionality.
"""

from .database import DatabaseManager
from .models import (
    Operation,
    Transaction,
    OperationType,
    OperationStatus,
    TransactionStatus
)
from .tracker import OperationHistory
from .transaction import OperationTransaction
from .cleanup import HistoryCleanup, HistoryCleanupConfig
from .export import HistoryExporter

__all__ = [
    'DatabaseManager',
    'Operation',
    'Transaction',
    'OperationType',
    'OperationStatus',
    'TransactionStatus',
    'OperationHistory',
    'OperationTransaction',
    'HistoryCleanup',
    'HistoryCleanupConfig',
    'HistoryExporter',
]

__version__ = '1.0.0'
