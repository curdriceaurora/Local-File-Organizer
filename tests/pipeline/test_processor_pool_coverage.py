"""Coverage tests for pipeline.processor_pool module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.pipeline.processor_pool import ProcessorPool
from file_organizer.pipeline.router import ProcessorType

pytestmark = pytest.mark.unit


def _make_processor():
    proc = MagicMock()
    proc.initialize = MagicMock()
    proc.cleanup = MagicMock()
    return proc


class TestProcessorPoolRegistration:
    def test_register_factory(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        assert ProcessorType.TEXT in pool.registered_types

    def test_has_processor_with_factory(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        assert pool.has_processor(ProcessorType.TEXT) is True
        assert pool.has_processor(ProcessorType.IMAGE) is False

    def test_is_initialized_false_before_get(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        assert pool.is_initialized(ProcessorType.TEXT) is False


class TestProcessorPoolGet:
    def test_get_creates_and_initializes(self):
        proc = _make_processor()
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: proc)

        result = pool.get_processor(ProcessorType.TEXT)
        assert result is proc
        proc.initialize.assert_called_once()
        assert pool.is_initialized(ProcessorType.TEXT) is True

    def test_get_returns_cached(self):
        proc = _make_processor()
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: proc)

        result1 = pool.get_processor(ProcessorType.TEXT)
        result2 = pool.get_processor(ProcessorType.TEXT)
        assert result1 is result2
        proc.initialize.assert_called_once()

    def test_get_returns_none_for_unknown_type(self):
        pool = ProcessorPool()
        result = pool.get_processor(ProcessorType.UNKNOWN)
        assert result is None

    def test_get_returns_none_on_factory_error(self):
        pool = ProcessorPool()
        pool.register_factory(
            ProcessorType.TEXT, lambda: (_ for _ in ()).throw(RuntimeError("fail"))
        )

        result = pool.get_processor(ProcessorType.TEXT)
        assert result is None


class TestProcessorPoolCleanup:
    def test_cleanup_calls_all(self):
        proc1 = _make_processor()
        proc2 = _make_processor()
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: proc1)
        pool.register_factory(ProcessorType.IMAGE, lambda: proc2)

        pool.get_processor(ProcessorType.TEXT)
        pool.get_processor(ProcessorType.IMAGE)

        pool.cleanup()
        proc1.cleanup.assert_called_once()
        proc2.cleanup.assert_called_once()
        assert pool.active_count == 0

    def test_cleanup_continues_on_error(self):
        proc1 = _make_processor()
        proc1.cleanup.side_effect = RuntimeError("fail")
        proc2 = _make_processor()
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: proc1)
        pool.register_factory(ProcessorType.IMAGE, lambda: proc2)

        pool.get_processor(ProcessorType.TEXT)
        pool.get_processor(ProcessorType.IMAGE)

        pool.cleanup()
        proc2.cleanup.assert_called_once()
        assert pool.active_count == 0


class TestProcessorPoolProperties:
    def test_active_count(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        assert pool.active_count == 0

        pool.get_processor(ProcessorType.TEXT)
        assert pool.active_count == 1


class TestNormalizeProcessorResult:
    def test_normalize_mapping_with_folder_and_tags(self):
        from pathlib import Path

        from file_organizer.pipeline.processor_pool import normalize_processor_result

        raw = {
            "folder_name": "reports",
            "filename": "annual_summary",
            "tags": ["finance", "annual"],
        }
        res = normalize_processor_result(Path("summary.pdf"), raw)
        assert res["category"] == "reports"
        assert res["filename"] == "annual_summary"
        assert res["tags"] == ["finance", "annual"]

    def test_normalize_mapping_with_error_raises(self):
        from pathlib import Path

        from file_organizer.pipeline.processor_pool import normalize_processor_result

        with pytest.raises(RuntimeError, match="Processor reported error"):
            normalize_processor_result(Path("doc.txt"), {"error": "Corrupted file"})

    def test_normalize_object_with_category_and_tags(self):
        from pathlib import Path

        from file_organizer.pipeline.processor_pool import normalize_processor_result

        class ObjResult:
            category = "photos"
            filename = "beach"
            tags = ["vacation", "summer"]

        res = normalize_processor_result(Path("img.jpg"), ObjResult())
        assert res["category"] == "photos"
        assert res["filename"] == "beach"
        assert res["tags"] == ["vacation", "summer"]

    def test_normalize_object_with_error_raises(self):
        from pathlib import Path

        from file_organizer.pipeline.processor_pool import normalize_processor_result

        class ErrorResult:
            error = "Inference timed out"

        with pytest.raises(RuntimeError, match="Inference timed out"):
            normalize_processor_result(Path("img.jpg"), ErrorResult())

    def test_registered_types(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        pool.register_factory(ProcessorType.IMAGE, lambda: _make_processor())
        assert set(pool.registered_types) == {ProcessorType.TEXT, ProcessorType.IMAGE}
