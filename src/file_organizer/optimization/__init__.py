"""Optimization module for the file organizer system.

This module provides database indexing, query optimization, connection pooling,
query caching, lazy model loading, model caching, resource monitoring,
model warmup, memory profiling, memory limiting, adaptive batch sizing,
and leak detection capabilities.
"""

from __future__ import annotations

from .batch_sizer import AdaptiveBatchSizer
from .connection_pool import ConnectionPool, PoolStats
from .database import DatabaseOptimizer, QueryPlan, TableStats
from .lazy_loader import LazyModelLoader
from .leak_detector import LeakDetector, LeakSuspect
from .memory_limiter import LimitAction, MemoryLimiter, MemoryLimitError
from .memory_profiler import (
    MemoryProfiler,
    MemorySnapshot,
    MemoryTimeline,
    ProfileResult,
)
from .model_cache import CacheStats, ModelCache
from .query_cache import CachedResult, QueryCache
from .resource_monitor import GpuMemoryInfo, MemoryInfo, ResourceMonitor
from .warmup import ModelWarmup, WarmupResult

__all__ = [
    "AdaptiveBatchSizer",
    "CachedResult",
    "CacheStats",
    "ConnectionPool",
    "DatabaseOptimizer",
    "GpuMemoryInfo",
    "LazyModelLoader",
    "LeakDetector",
    "LeakSuspect",
    "LimitAction",
    "MemoryInfo",
    "MemoryLimitError",
    "MemoryLimiter",
    "MemoryProfiler",
    "MemorySnapshot",
    "MemoryTimeline",
    "ModelCache",
    "ModelWarmup",
    "PoolStats",
    "ProfileResult",
    "QueryCache",
    "QueryPlan",
    "ResourceMonitor",
    "TableStats",
    "WarmupResult",
]

__version__ = "1.1.0"
