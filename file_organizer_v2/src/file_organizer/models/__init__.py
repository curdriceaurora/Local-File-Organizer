"""AI model interfaces and implementations."""

from file_organizer.models.base import BaseModel, ModelConfig, ModelType, DeviceType
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel
from file_organizer.models.audio_model import AudioModel
from file_organizer.models.suggestion_types import (
    Suggestion,
    SuggestionType,
    SuggestionBatch,
    ConfidenceFactors,
    ConfidenceLevel,
)
from file_organizer.models.analytics import (
    FileInfo,
    StorageStats,
    FileDistribution,
    DuplicateStats,
    QualityMetrics,
    TimeSavings,
    MetricsSnapshot,
    TrendData,
    AnalyticsDashboard,
)

__all__ = [
    "BaseModel",
    "ModelConfig",
    "ModelType",
    "DeviceType",
    "TextModel",
    "VisionModel",
    "AudioModel",
    "Suggestion",
    "SuggestionType",
    "SuggestionBatch",
    "ConfidenceFactors",
    "ConfidenceLevel",
    "FileInfo",
    "StorageStats",
    "FileDistribution",
    "DuplicateStats",
    "QualityMetrics",
    "TimeSavings",
    "MetricsSnapshot",
    "TrendData",
    "AnalyticsDashboard",
]
