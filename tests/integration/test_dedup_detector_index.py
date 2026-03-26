"""Integration tests for deduplication detector and index.

Covers:
  - services/deduplication/detector.py  — DuplicateDetector
  - services/deduplication/index.py     — DuplicateIndex
  - services/copilot/intent_parser.py   — IntentParser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.copilot.executor import Intent, IntentType
from file_organizer.services.copilot.intent_parser import IntentParser
from file_organizer.services.deduplication.detector import DuplicateDetector
from file_organizer.services.deduplication.index import DuplicateIndex

pytestmark = [pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# DuplicateIndex
# ---------------------------------------------------------------------------


@pytest.fixture()
def index() -> DuplicateIndex:
    return DuplicateIndex()


class TestDuplicateIndexInit:
    def test_creates(self) -> None:
        idx = DuplicateIndex()
        assert idx is not None


class TestDuplicateIndexAddFile:
    def test_add_single_file(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        index.add_file(f, "abc123hash")
        files = index.get_files_by_hash("abc123hash")
        assert len(files) == 1
        assert any(fm.path == f for fm in files)

    def test_add_with_metadata(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        index.add_file(f, "hash1", metadata={"size": 100})
        files = index.get_files_by_hash("hash1")
        assert any(fm.path == f for fm in files)
        by_size = index.get_files_by_size(100)
        assert f in by_size

    def test_add_duplicate_hash(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        index.add_file(f1, "samehash")
        index.add_file(f2, "samehash")
        assert index.has_duplicates()


class TestDuplicateIndexGetFiles:
    def test_get_by_hash_empty(self, index: DuplicateIndex) -> None:
        result = index.get_files_by_hash("nonexistent")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_by_hash_after_add(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        index.add_file(f, "myhash")
        result = index.get_files_by_hash("myhash")
        assert len(result) >= 1

    def test_get_duplicates_empty(self, index: DuplicateIndex) -> None:
        result = index.get_duplicates()
        assert result == {}

    def test_get_duplicates_after_adding(self, index: DuplicateIndex, tmp_path: Path) -> None:
        for i in range(2):
            f = tmp_path / f"file{i}.txt"
            f.write_text("identical")
            index.add_file(f, "dupehash")
        result = index.get_duplicates()
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_get_files_by_size(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "sized.txt"
        f.write_bytes(b"x" * 100)
        index.add_file(f, "sizehash", metadata={"size": 100})
        result = index.get_files_by_size(100)
        assert len(result) >= 1


class TestDuplicateIndexStatistics:
    def test_empty_stats(self, index: DuplicateIndex) -> None:
        stats = index.get_statistics()
        assert "total_files" in stats

    def test_stats_after_adding(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("content")
        index.add_file(f, "hash1")
        stats = index.get_statistics()
        assert stats["total_files"] >= 1


class TestDuplicateIndexClear:
    def test_clear_empty(self, index: DuplicateIndex) -> None:
        index.clear()
        assert not index.has_duplicates()

    def test_clear_with_data(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same")
        f2.write_text("same")
        index.add_file(f1, "h")
        index.add_file(f2, "h")
        index.clear()
        assert not index.has_duplicates()


class TestDuplicateIndexHasDuplicates:
    def test_empty_false(self, index: DuplicateIndex) -> None:
        assert index.has_duplicates() is False

    def test_single_file_false(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f = tmp_path / "only.txt"
        f.write_text("x")
        index.add_file(f, "unique_hash")
        assert index.has_duplicates() is False

    def test_two_files_same_hash_true(self, index: DuplicateIndex, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same")
        f2.write_text("same")
        index.add_file(f1, "dup")
        index.add_file(f2, "dup")
        assert index.has_duplicates() is True


# ---------------------------------------------------------------------------
# DuplicateDetector
# ---------------------------------------------------------------------------


@pytest.fixture()
def detector() -> DuplicateDetector:
    return DuplicateDetector()


class TestDuplicateDetectorInit:
    def test_default_init(self) -> None:
        d = DuplicateDetector()
        assert d is not None

    def test_with_custom_hasher(self) -> None:
        from file_organizer.services.deduplication.hasher import FileHasher

        hasher = FileHasher()
        d = DuplicateDetector(hasher=hasher)
        assert d is not None


class TestDuplicateDetectorScanDirectory:
    def test_empty_dir(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        result = detector.scan_directory(tmp_path)
        assert isinstance(result, DuplicateIndex)

    def test_no_duplicates(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("content A")
        (tmp_path / "b.txt").write_text("content B")
        result = detector.scan_directory(tmp_path)
        assert isinstance(result, DuplicateIndex)

    def test_with_duplicates(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        content = "identical content in both files"
        (tmp_path / "copy1.txt").write_text(content)
        (tmp_path / "copy2.txt").write_text(content)
        (tmp_path / "unique.txt").write_text("different")
        result = detector.scan_directory(tmp_path)
        assert result.has_duplicates()

    def test_returns_duplicate_index(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        result = detector.scan_directory(tmp_path)
        assert isinstance(result, DuplicateIndex)


class TestDuplicateDetectorGetGroups:
    def test_empty_returns_dict(self, detector: DuplicateDetector) -> None:
        result = detector.get_duplicate_groups()
        assert result == {}

    def test_after_scan(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("content")
        (tmp_path / "b.txt").write_text("content")
        detector.scan_directory(tmp_path)
        result = detector.get_duplicate_groups()
        all_dupes = [fm.path for group in result.values() for fm in group.files]
        assert any(p.name == "a.txt" for p in all_dupes)
        assert any(p.name == "b.txt" for p in all_dupes)


class TestDuplicateDetectorGetStatistics:
    def test_returns_dict(self, detector: DuplicateDetector) -> None:
        result = detector.get_statistics()
        assert "total_files" in result

    def test_after_scan(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        # Two files with identical content are hashed and indexed as a duplicate group
        content = b"some content"
        (tmp_path / "file_a.txt").write_bytes(content)
        (tmp_path / "file_b.txt").write_bytes(content)
        detector.scan_directory(tmp_path)
        stats = detector.get_statistics()
        assert stats["total_files"] == 2


class TestDuplicateDetectorFindDuplicatesOfFile:
    def test_no_duplicates(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        f = tmp_path / "unique.txt"
        f.write_text("unique content")
        (tmp_path / "other.txt").write_text("different")
        result = detector.find_duplicates_of_file(f, tmp_path)
        assert result == []

    def test_with_duplicate(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        content = "duplicate content for detection test"
        f1 = tmp_path / "original.txt"
        f2 = tmp_path / "copy.txt"
        f1.write_text(content)
        f2.write_text(content)
        result = detector.find_duplicates_of_file(f1, tmp_path)
        assert any(fm.path.name == "copy.txt" for fm in result)


class TestDuplicateDetectorClear:
    def test_clear(self, detector: DuplicateDetector, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("x")
        detector.scan_directory(tmp_path)
        detector.clear()
        result = detector.get_duplicate_groups()
        assert result == {}


# ---------------------------------------------------------------------------
# IntentParser
# ---------------------------------------------------------------------------


@pytest.fixture()
def intent_parser() -> IntentParser:
    return IntentParser()


class TestIntentParserInit:
    def test_creates(self) -> None:
        p = IntentParser()
        assert p is not None


class TestIntentParserParse:
    def test_returns_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("organize my files")
        assert isinstance(result, Intent)

    def test_organize_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("organize my documents folder")
        assert isinstance(result.intent_type, IntentType)

    def test_find_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("find all PDF files")
        assert isinstance(result.intent_type, IntentType)

    def test_move_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("move file.txt to Documents")
        assert isinstance(result.intent_type, IntentType)

    def test_undo_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("undo the last operation")
        assert isinstance(result.intent_type, IntentType)

    def test_empty_string(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("")
        assert isinstance(result, Intent)

    def test_with_context(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("rename files", context="working in workspace/Documents")
        assert isinstance(result, Intent)

    def test_result_has_intent_type(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("help me organize")
        assert hasattr(result, "intent_type")

    def test_result_has_confidence(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("show status")
        assert hasattr(result, "confidence")
        assert isinstance(result.confidence, float)

    def test_confidence_in_range(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("show me what's here")
        assert 0.0 <= result.confidence <= 1.0

    def test_help_intent(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("help")
        assert result.intent_type in list(IntentType)

    def test_unknown_returns_valid(self, intent_parser: IntentParser) -> None:
        result = intent_parser.parse("xyz zyx abc nonsense phrase that matches nothing")
        assert isinstance(result, Intent)
