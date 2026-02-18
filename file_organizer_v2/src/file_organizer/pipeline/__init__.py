"""
Auto-organization pipeline package.

Connects file system monitoring to file processing and organization,
providing a cohesive pipeline for automatically categorizing and
organizing files using AI-powered processors.
"""

from __future__ import annotations

from .config import PipelineConfig
from .orchestrator import PipelineOrchestrator, PipelineStats, ProcessingResult
from .processor_pool import BaseProcessor, ProcessorPool
from .router import FileRouter, ProcessorType

__all__ = [
    "BaseProcessor",
    "FileRouter",
    "PipelineConfig",
    "PipelineOrchestrator",
    "PipelineStats",
    "ProcessingResult",
    "ProcessorPool",
    "ProcessorType",
]
