"""AI model interfaces and implementations."""

from __future__ import annotations

from file_organizer.models.analytics import (
    AnalyticsDashboard,
    DuplicateStats,
    FileDistribution,
    FileInfo,
    MetricsSnapshot,
    QualityMetrics,
    StorageStats,
    TimeSavings,
    TrendData,
)
from file_organizer.models.audio_model import AudioModel
from file_organizer.models.base import BaseModel, DeviceType, ModelConfig, ModelType
from file_organizer.models.openai_text_model import OpenAITextModel
from file_organizer.models.openai_vision_model import OpenAIVisionModel
from file_organizer.models.provider_factory import get_text_model, get_vision_model
from file_organizer.models.suggestion_types import (
    ConfidenceFactors,
    ConfidenceLevel,
    Suggestion,
    SuggestionBatch,
    SuggestionType,
)
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel

__all__ = [
    "BaseModel",
    "ModelConfig",
    "ModelType",
    "DeviceType",
    "TextModel",
    "VisionModel",
    "OpenAITextModel",
    "OpenAIVisionModel",
    "get_text_model",
    "get_vision_model",
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
