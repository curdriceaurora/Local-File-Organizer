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

    def test_registered_types(self):
        pool = ProcessorPool()
        pool.register_factory(ProcessorType.TEXT, lambda: _make_processor())
        pool.register_factory(ProcessorType.IMAGE, lambda: _make_processor())
        assert set(pool.registered_types) == {ProcessorType.TEXT, ProcessorType.IMAGE}


class TestNormalizeProcessorResult:
    def test_normalize_mapping_with_tags(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        mapping_result = {
            "category": "Invoices",
            "filename": "sample_invoice",
            "tags": ["finance", "tax-2024"],
        }
        normalized = normalize_processor_result(file_path, mapping_result)
        assert normalized == {
            "category": "Invoices",
            "filename": "sample_invoice",
            "tags": ["finance", "tax-2024"],
        }

    def test_normalize_mapping_precedence_and_fallbacks(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        # folder_name takes precedence over category
        mapping_result = {
            "category": "OldDocs",
            "folder_name": "Docs",
        }
        normalized = normalize_processor_result(file_path, mapping_result)
        assert normalized["category"] == "Docs"
        assert normalized["filename"] == "sample"
        assert "tags" not in normalized

        # category fallback when folder_name absent
        mapping_fallback = {"category": "Spreadsheets"}
        normalized_fb = normalize_processor_result(file_path, mapping_fallback)
        assert normalized_fb["category"] == "Spreadsheets"

    def test_normalize_mapping_error_raises(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        with pytest.raises(RuntimeError, match="Processor reported error: model failed"):
            normalize_processor_result(file_path, {"error": "model failed"})

    def test_normalize_object_with_tags(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "photo.jpg"
        obj = MagicMock(spec=["folder_name", "category", "filename", "tags", "error"])
        obj.folder_name = "Photos"
        obj.category = "IgnoredCategory"
        obj.filename = "beach"
        obj.tags = ["vacation", "summer"]
        obj.error = None

        normalized = normalize_processor_result(file_path, obj)
        assert normalized == {
            "category": "Photos",
            "filename": "beach",
            "tags": ["vacation", "summer"],
        }

    def test_normalize_object_folder_name_fallback(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "photo.jpg"
        obj = MagicMock(spec=["folder_name", "filename", "error", "tags"])
        obj.folder_name = "FallbackPhotos"
        obj.filename = "beach"
        obj.tags = []
        obj.error = None

        normalized = normalize_processor_result(file_path, obj)
        assert normalized["category"] == "FallbackPhotos"
        assert "tags" not in normalized

    def test_normalize_object_error_raises(self, tmp_path):
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "photo.jpg"
        obj = MagicMock()
        obj.error = "corrupted file"

        with pytest.raises(RuntimeError, match="Processor reported error: corrupted file"):
            normalize_processor_result(file_path, obj)

    def test_normalize_mapping_neither_folder_name_nor_category(self, tmp_path):
        """Mirrors the object-branch default (test_registered_types-style fallback)."""
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        normalized = normalize_processor_result(file_path, {})
        assert normalized["category"] == "uncategorized"
        assert normalized["filename"] == "sample"
        assert "tags" not in normalized

    def test_normalize_object_category_fallback_when_no_folder_name(self, tmp_path):
        """The object-branch mirror of test_normalize_mapping_precedence_and_fallbacks'
        category-without-folder_name case -- previously untested, same elif as the
        Mapping branch but on the attribute-access side."""
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        obj = MagicMock(spec=["folder_name", "category", "filename", "tags", "error"])
        obj.folder_name = None
        obj.category = "FallbackCategory"
        obj.filename = None
        obj.tags = None
        obj.error = None

        normalized = normalize_processor_result(file_path, obj)
        assert normalized["category"] == "FallbackCategory"
        assert normalized["filename"] == "sample"
        assert "tags" not in normalized

    def test_normalize_object_neither_folder_name_nor_category(self, tmp_path):
        """Object-branch mirror of test_normalize_mapping_neither_folder_name_nor_category."""
        from file_organizer.pipeline.processor_pool import normalize_processor_result

        file_path = tmp_path / "sample.pdf"
        obj = MagicMock(spec=["folder_name", "category", "filename", "tags", "error"])
        obj.folder_name = None
        obj.category = None
        obj.filename = None
        obj.tags = None
        obj.error = None

        normalized = normalize_processor_result(file_path, obj)
        assert normalized["category"] == "uncategorized"
        assert normalized["filename"] == "sample"
        assert "tags" not in normalized
