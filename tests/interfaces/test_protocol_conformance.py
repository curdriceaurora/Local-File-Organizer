"""Protocol conformance tests for interface contracts.

Verifies that existing implementations satisfy their respective
``@runtime_checkable`` Protocol classes via ``isinstance()`` checks.
These tests require no network access or model initialization — they
validate structural conformance only.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.interfaces import (
    MISSING,
    AudioModelProtocol,
    BatchProcessorProtocol,
    CacheProtocol,
    FileProcessorProtocol,
    LearnerProtocol,
    PipelineStage,
    ScorerProtocol,
    StageContext,
    StorageProtocol,
    TextModelProtocol,
    VisionModelProtocol,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_config(
    *,
    model_type: str = "text",
    provider: str = "ollama",
) -> MagicMock:
    """Create a minimal ModelConfig mock for model instantiation."""
    from file_organizer.models.base import DeviceType, ModelType

    type_map = {
        "text": ModelType.TEXT,
        "vision": ModelType.VISION,
        "audio": ModelType.AUDIO,
    }
    cfg = MagicMock()
    cfg.name = "test-model"
    cfg.model_type = type_map[model_type]
    cfg.quantization = "q4_k_m"
    cfg.device = DeviceType.AUTO
    cfg.temperature = 0.5
    cfg.max_tokens = 3000
    cfg.top_k = 3
    cfg.top_p = 0.3
    cfg.context_window = 4096
    cfg.batch_size = 1
    cfg.framework = provider
    cfg.provider = provider
    cfg.api_key = None
    cfg.api_base_url = None
    cfg.model_path = None
    cfg.local_path = None
    cfg.extra_params = {}
    return cfg


# ---------------------------------------------------------------------------
# Model protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestModelProtocolConformance:
    """Verify that all model implementations satisfy their Protocol."""

    def test_text_model_satisfies_text_protocol(self) -> None:
        from file_organizer.models.text_model import TextModel

        cfg = _make_model_config(model_type="text")
        model = TextModel(cfg)
        assert isinstance(model, TextModelProtocol)

    def test_vision_model_satisfies_vision_protocol(self) -> None:
        from file_organizer.models.vision_model import VisionModel

        cfg = _make_model_config(model_type="vision")
        model = VisionModel(cfg)
        assert isinstance(model, VisionModelProtocol)

    def test_audio_model_satisfies_audio_protocol(self) -> None:
        from file_organizer.models.audio_model import AudioModel

        cfg = _make_model_config(model_type="audio")
        model = AudioModel(cfg)
        assert isinstance(model, AudioModelProtocol)

    def test_text_model_also_satisfies_audio_protocol(self) -> None:
        """TextModel and AudioModel share the same generate signature."""
        from file_organizer.models.text_model import TextModel

        cfg = _make_model_config(model_type="text")
        model = TextModel(cfg)
        assert isinstance(model, AudioModelProtocol)

    @patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True)
    @patch("file_organizer.models.openai_text_model.create_openai_client")
    def test_openai_text_model_satisfies_text_protocol(self, _mock_create: MagicMock) -> None:
        from file_organizer.models.openai_text_model import OpenAITextModel

        cfg = _make_model_config(model_type="text", provider="openai")
        cfg.api_key = "test-key"
        model = OpenAITextModel(cfg)
        assert isinstance(model, TextModelProtocol)

    @patch("file_organizer.models.openai_vision_model.OPENAI_AVAILABLE", True)
    @patch("file_organizer.models.openai_vision_model.create_openai_client")
    def test_openai_vision_model_satisfies_vision_protocol(self, _mock_create: MagicMock) -> None:
        from file_organizer.models.openai_vision_model import OpenAIVisionModel

        cfg = _make_model_config(model_type="vision", provider="openai")
        cfg.api_key = "test-key"
        model = OpenAIVisionModel(cfg)
        assert isinstance(model, VisionModelProtocol)


# ---------------------------------------------------------------------------
# Processor protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestProcessorProtocolConformance:
    """Verify that processor classes satisfy FileProcessorProtocol."""

    def test_text_processor_satisfies_protocol(self) -> None:
        from file_organizer.services.text_processor import TextProcessor

        # Provide a mock model to avoid network calls during init
        mock_model = MagicMock()
        mock_model.config.model_type = _make_model_config().model_type
        processor = TextProcessor(text_model=mock_model)
        assert isinstance(processor, FileProcessorProtocol)

    def test_vision_processor_satisfies_protocol(self) -> None:
        from file_organizer.services.vision_processor import VisionProcessor

        mock_model = MagicMock()
        mock_model.config.model_type = _make_model_config(model_type="vision").model_type
        processor = VisionProcessor(vision_model=mock_model)
        assert isinstance(processor, FileProcessorProtocol)


# ---------------------------------------------------------------------------
# Batch processor protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBatchProcessorProtocolConformance:
    """Verify that ParallelProcessor satisfies BatchProcessorProtocol."""

    def test_parallel_processor_satisfies_protocol(self) -> None:
        from file_organizer.parallel.processor import ParallelProcessor

        processor = ParallelProcessor()
        assert isinstance(processor, BatchProcessorProtocol)


# ---------------------------------------------------------------------------
# Cache protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestCacheProtocolConformance:
    """Verify that ModelCache satisfies CacheProtocol."""

    def test_model_cache_satisfies_protocol(self) -> None:
        from file_organizer.optimization.model_cache import ModelCache

        cache = ModelCache(max_models=2)
        assert isinstance(cache, CacheProtocol)


# ---------------------------------------------------------------------------
# Intelligence protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestIntelligenceProtocolConformance:
    """Verify that intelligence services satisfy their protocols."""

    def test_folder_learner_satisfies_learner_protocol(self) -> None:
        from file_organizer.services.intelligence.folder_learner import (
            FolderPreferenceLearner,
        )

        learner = FolderPreferenceLearner()
        assert isinstance(learner, LearnerProtocol)

    def test_pattern_scorer_satisfies_scorer_protocol(self) -> None:
        from file_organizer.services.intelligence.scoring import PatternScorer

        scorer = PatternScorer()
        assert isinstance(scorer, ScorerProtocol)


# ---------------------------------------------------------------------------
# Storage protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestStorageProtocolConformance:
    """Verify that a minimal implementation satisfies StorageProtocol.

    No concrete StorageProtocol implementation exists yet (forward-looking
    contract).  This test uses a stub to confirm the protocol shape is
    structurally sound and that ``isinstance()`` works at runtime.
    """

    def test_stub_satisfies_storage_protocol(self) -> None:
        class _StubStorage:
            def get(self, key: str, default: object = MISSING) -> object:
                return default

            def put(self, key: str, value: object) -> None:
                pass

            def delete(self, key: str) -> bool:
                return False

            def exists(self, key: str) -> bool:
                return False

        protocol_params = list(inspect.signature(StorageProtocol.get).parameters.values())
        stub_params = list(inspect.signature(_StubStorage.get).parameters.values())
        assert len(stub_params) == len(protocol_params)
        assert [param.name for param in stub_params] == [param.name for param in protocol_params]
        assert [param.kind for param in stub_params] == [param.kind for param in protocol_params]
        assert stub_params[-1].default is MISSING
        assert isinstance(_StubStorage(), StorageProtocol)


# ---------------------------------------------------------------------------
# Pipeline stage protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestPipelineStageProtocolConformance:
    """Verify that pipeline stage implementations satisfy PipelineStage."""

    def test_stub_satisfies_pipeline_stage_protocol(self) -> None:
        """A minimal stub with name + process satisfies the protocol."""

        class _StubStage:
            @property
            def name(self) -> str:
                return "stub"

            def process(self, context: StageContext) -> StageContext:
                return context

        stage = _StubStage()
        assert isinstance(stage, PipelineStage)

    def test_all_built_in_stages_satisfy_protocol(self) -> None:
        """All four extracted pipeline stages satisfy PipelineStage."""
        from pathlib import Path

        from file_organizer.pipeline.stages.analyzer import AnalyzerStage
        from file_organizer.pipeline.stages.postprocessor import PostprocessorStage
        from file_organizer.pipeline.stages.preprocessor import PreprocessorStage
        from file_organizer.pipeline.stages.writer import WriterStage

        preprocessor = PreprocessorStage()
        assert isinstance(preprocessor, PipelineStage)

        analyzer = AnalyzerStage()
        assert isinstance(analyzer, PipelineStage)

        postprocessor = PostprocessorStage(output_directory=Path("out"))
        assert isinstance(postprocessor, PipelineStage)

        writer = WriterStage()
        assert isinstance(writer, PipelineStage)
