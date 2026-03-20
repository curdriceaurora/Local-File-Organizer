"""Integration tests for storage reporter and vector/search utilities.

Covers:
  - services/deduplication/reporter.py  — StorageReporter
  - services/search/vector_index.py     — VectorIndex
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from file_organizer.services.deduplication.reporter import StorageReporter
from file_organizer.services.search.vector_index import VectorIndex

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_duplicate_group(
    count: int = 2,
    total_size: int = 2048,
    avg_similarity: float = 0.95,
    representative: str = "a.txt",
    files: list[str] | None = None,
) -> dict:
    return {
        "count": count,
        "total_size": total_size,
        "avg_similarity": avg_similarity,
        "representative": representative,
        "files": files or ["a.txt", "b.txt"],
    }


def _make_duplicate_results(groups: list[dict] | None = None) -> dict:
    groups = groups or [_make_duplicate_group()]
    return {
        "analyzed_documents": 10,
        "num_groups": len(groups),
        "space_wasted": sum(g["total_size"] for g in groups),
        "duplicate_groups": groups,
    }


# ---------------------------------------------------------------------------
# StorageReporter
# ---------------------------------------------------------------------------


class TestStorageReporterInit:
    def test_created(self) -> None:
        reporter = StorageReporter()
        assert reporter is not None


class TestStorageReporterCalculateReclamation:
    def test_returns_dict(self) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(count=2, total_size=2000)]
        result = reporter.calculate_reclamation(groups)
        assert result["total_duplicate_files"] == 2

    def test_total_duplicate_files(self) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(count=3), _make_duplicate_group(count=2)]
        result = reporter.calculate_reclamation(groups)
        assert result["total_duplicate_files"] == 5

    def test_total_groups(self) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(), _make_duplicate_group()]
        result = reporter.calculate_reclamation(groups)
        assert result["total_duplicate_groups"] == 2

    def test_recoverable_space_positive(self) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(count=3, total_size=3000)]
        result = reporter.calculate_reclamation(groups)
        assert result["recoverable_space"] > 0

    def test_empty_groups(self) -> None:
        reporter = StorageReporter()
        result = reporter.calculate_reclamation([])
        assert result["total_duplicate_files"] == 0
        assert result["recovery_percentage"] == 0

    def test_recovery_percentage_range(self) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(count=2, total_size=2000)]
        result = reporter.calculate_reclamation(groups)
        assert 0 <= result["recovery_percentage"] <= 100


class TestStorageReporterGenerateReport:
    def test_returns_string(self) -> None:
        reporter = StorageReporter()
        result = reporter.generate_report(_make_duplicate_results())
        assert "REPORT" in result.upper()

    def test_text_format_contains_header(self) -> None:
        reporter = StorageReporter()
        result = reporter.generate_report(_make_duplicate_results(), output_format="text")
        assert "REPORT" in result.upper()

    def test_json_format_returns_valid_json(self) -> None:
        reporter = StorageReporter()
        data = _make_duplicate_results()
        result = reporter.generate_report(data, output_format="json")
        parsed = json.loads(result)
        assert "duplicate_groups" in parsed

    def test_json_contains_groups(self) -> None:
        reporter = StorageReporter()
        data = _make_duplicate_results()
        result = reporter.generate_report(data, output_format="json")
        parsed = json.loads(result)
        assert "duplicate_groups" in parsed

    def test_text_shows_group_count(self) -> None:
        reporter = StorageReporter()
        group = _make_duplicate_group(count=5)
        data = _make_duplicate_results(groups=[group])
        result = reporter.generate_report(data, output_format="text")
        assert "5" in result

    def test_large_group_truncates_files(self) -> None:
        reporter = StorageReporter()
        files = [f"file{i}.txt" for i in range(10)]
        group = _make_duplicate_group(count=10, files=files, representative=files[0])
        data = _make_duplicate_results(groups=[group])
        result = reporter.generate_report(data, output_format="text")
        assert "more" in result.lower()


class TestStorageReporterExportToCSV:
    def test_creates_csv_file(self, tmp_path: Path) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group()]
        output = tmp_path / "report.csv"
        reporter.export_to_csv(groups, output)
        assert output.exists()

    def test_csv_has_header(self, tmp_path: Path) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group()]
        output = tmp_path / "report.csv"
        reporter.export_to_csv(groups, output)
        content = output.read_text(encoding="utf-8")
        assert "Group ID" in content

    def test_csv_has_data_row(self, tmp_path: Path) -> None:
        reporter = StorageReporter()
        groups = [_make_duplicate_group(count=3)]
        output = tmp_path / "report.csv"
        reporter.export_to_csv(groups, output)
        lines = output.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 2


class TestStorageReporterExportToJSON:
    def test_creates_json_file(self, tmp_path: Path) -> None:
        reporter = StorageReporter()
        data = _make_duplicate_results()
        output = tmp_path / "report.json"
        reporter.export_to_json(data, output)
        assert output.exists()

    def test_json_file_valid(self, tmp_path: Path) -> None:
        reporter = StorageReporter()
        data = _make_duplicate_results()
        output = tmp_path / "report.json"
        reporter.export_to_json(data, output)
        parsed = json.loads(output.read_text(encoding="utf-8"))
        assert "duplicate_groups" in parsed


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------


class TestVectorIndexInit:
    def test_created(self) -> None:
        idx = VectorIndex()
        assert idx is not None

    def test_empty_initially(self) -> None:
        idx = VectorIndex()
        assert idx.size == 0

    def test_search_before_index_empty(self) -> None:
        idx = VectorIndex()
        assert idx.search("anything") == []

    def test_with_threshold(self) -> None:
        idx = VectorIndex(similarity_threshold=0.5)
        assert idx is not None


class TestVectorIndexIndex:
    def test_sets_size(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"doc{i}.txt" for i in range(3)]
        idx.index(["document one content", "document two text", "document three data"], paths)
        assert idx.size == 3

    def test_mismatched_lengths_raises(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        with pytest.raises(ValueError, match="equal length"):
            idx.index(["a", "b"], [tmp_path / "one.txt"])

    def test_empty_corpus_resets(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(4)]
        idx.index(
            ["finance quarterly", "cooking recipes dinner", "sports events", "music concerts"],
            paths,
        )
        idx.index([], [])
        assert idx.size == 0

    def test_reindex_replaces_old(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        old_paths = [tmp_path / f"old{i}.txt" for i in range(4)]
        idx.index(
            ["alpha documents", "beta recipes cooking", "gamma sports", "delta music"], old_paths
        )
        new_paths = [tmp_path / f"new{i}.txt" for i in range(2)]
        idx.index(["finance quarterly report", "cooking pasta dinner recipes"], new_paths)
        assert idx.size == 2


class TestVectorIndexSearch:
    def test_returns_list(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(4)]
        idx.index(
            [
                "finance quarterly report",
                "cooking pasta recipe",
                "project work items",
                "sports news",
            ],
            paths,
        )
        result = idx.search("finance")
        # At least the finance document should be returned
        assert len(result) >= 1

    def test_results_are_tuples(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(4)]
        idx.index(
            ["finance quarterly report", "cooking pasta recipe", "project items", "music events"],
            paths,
        )
        results = idx.search("finance")
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_scores_are_floats(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(3)]
        idx.index(["finance doc", "cooking doc", "travel doc"], paths)
        results = idx.search("finance")
        for _, score in results:
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_empty_query(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(4)]
        idx.index(
            ["finance quarterly", "cooking recipes", "sports events", "music concerts"], paths
        )
        result = idx.search("")
        assert result == []

    def test_top_k_limit(self, tmp_path: Path) -> None:
        idx = VectorIndex()
        paths = [tmp_path / f"d{i}.txt" for i in range(8)]
        docs = [
            "finance quarterly invoice payment report",
            "cooking pasta dinner recipes kitchen",
            "sports events football basketball",
            "music concerts piano violin orchestra",
            "travel destinations tourism vacation",
            "technology software programming code",
            "health fitness exercise nutrition",
            "education schools universities learning",
        ]
        idx.index(docs, paths)
        results = idx.search("finance", top_k=3)
        assert len(results) < 4
