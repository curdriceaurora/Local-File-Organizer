"""Protocol-based interface definitions for file organizer components.

This package provides ``typing.Protocol`` contracts that define structural
interfaces for all major service boundaries.  Existing ABC-based
implementations satisfy these protocols without inheritance changes.

Modules:
    model: TextModelProtocol, VisionModelProtocol, AudioModelProtocol
    processor: FileProcessorProtocol, BatchProcessorProtocol
    storage: StorageProtocol, CacheProtocol
    intelligence: LearnerProtocol, ScorerProtocol
    pipeline: PipelineStage, StageContext
"""

from __future__ import annotations

from file_organizer.interfaces.intelligence import LearnerProtocol, ScorerProtocol
from file_organizer.interfaces.model import (
    AudioModelProtocol,
    TextModelProtocol,
    VisionModelProtocol,
)
from file_organizer.interfaces.pipeline import PipelineStage, StageContext
from file_organizer.interfaces.processor import (
    BatchProcessorProtocol,
    FileProcessorProtocol,
)
from file_organizer.interfaces.storage import MISSING, CacheProtocol, StorageProtocol

__all__ = [
    "AudioModelProtocol",
    "BatchProcessorProtocol",
    "CacheProtocol",
    "FileProcessorProtocol",
    "LearnerProtocol",
    "MISSING",
    "PipelineStage",
    "ScorerProtocol",
    "StageContext",
    "StorageProtocol",
    "TextModelProtocol",
    "VisionModelProtocol",
]
