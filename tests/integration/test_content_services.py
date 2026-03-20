"""Integration tests for content extraction and tagging services.

Covers:
  - services/deduplication/extractor.py   — DocumentExtractor
  - services/auto_tagging/content_analyzer.py — ContentTagAnalyzer
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.content_analyzer import ContentTagAnalyzer
from file_organizer.services.deduplication.extractor import DocumentExtractor

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# DocumentExtractor
# ---------------------------------------------------------------------------


@pytest.fixture()
def extractor() -> DocumentExtractor:
    return DocumentExtractor()


class TestDocumentExtractorInit:
    def test_supported_extensions_set(self, extractor: DocumentExtractor) -> None:
        exts = extractor.supported_extensions
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".txt" in exts
        assert ".md" in exts

    def test_get_supported_formats_returns_sorted_list(self, extractor: DocumentExtractor) -> None:
        fmts = extractor.get_supported_formats()
        assert isinstance(fmts, list)
        assert len(fmts) >= 4
        assert fmts == sorted(fmts)

    def test_supports_format_txt(self, extractor: DocumentExtractor, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.touch()
        assert extractor.supports_format(f) is True

    def test_supports_format_pdf(self, extractor: DocumentExtractor, tmp_path: Path) -> None:
        f = tmp_path / "file.pdf"
        f.touch()
        assert extractor.supports_format(f) is True

    def test_does_not_support_mp4(self, extractor: DocumentExtractor, tmp_path: Path) -> None:
        f = tmp_path / "video.mp4"
        f.touch()
        assert extractor.supports_format(f) is False


class TestDocumentExtractorTxt:
    def test_extract_txt_returns_content(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "sample.txt"
        f.write_text("Hello world from txt file.")
        result = extractor.extract_text(f)
        assert "Hello world" in result

    def test_extract_md_returns_content(self, extractor: DocumentExtractor, tmp_path: Path) -> None:
        f = tmp_path / "notes.md"
        f.write_text("# Heading\n\nSome markdown content here.")
        result = extractor.extract_text(f)
        assert "markdown content" in result

    def test_extract_nonexistent_file_raises(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        with pytest.raises(OSError):
            extractor.extract_text(tmp_path / "missing.txt")

    def test_extract_unsupported_format_raises(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "video.mp4"
        f.touch()
        with pytest.raises(ValueError):
            extractor.extract_text(f)

    def test_extract_empty_txt_returns_empty_string(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = extractor.extract_text(f)
        assert result == ""


class TestDocumentExtractorBatch:
    def test_batch_extract_returns_dict(self, extractor: DocumentExtractor, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("Content A")
        f2.write_text("Content B")
        results = extractor.extract_batch([f1, f2])
        assert f1 in results
        assert f2 in results
        assert "Content A" in results[f1]
        assert "Content B" in results[f2]

    def test_batch_extract_missing_file_returns_empty_string(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.txt"
        results = extractor.extract_batch([missing])
        assert results[missing] == ""

    def test_batch_extract_empty_list(self, extractor: DocumentExtractor) -> None:
        results = extractor.extract_batch([])
        assert results == {}

    def test_batch_extract_mixed_valid_invalid(
        self, extractor: DocumentExtractor, tmp_path: Path
    ) -> None:
        valid = tmp_path / "valid.txt"
        valid.write_text("Some text content")
        invalid = tmp_path / "invalid.mp4"
        invalid.touch()
        results = extractor.extract_batch([valid, invalid])
        assert results[valid] == "Some text content"
        assert results[invalid] == ""


# ---------------------------------------------------------------------------
# ContentTagAnalyzer
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyzer() -> ContentTagAnalyzer:
    return ContentTagAnalyzer()


class TestContentTagAnalyzerInit:
    def test_default_max_keywords(self, analyzer: ContentTagAnalyzer) -> None:
        assert analyzer.max_keywords == 20

    def test_default_min_keyword_length(self, analyzer: ContentTagAnalyzer) -> None:
        assert analyzer.min_keyword_length == 3

    def test_custom_params(self) -> None:
        a = ContentTagAnalyzer(min_keyword_length=5, max_keywords=10)
        assert a.min_keyword_length == 5
        assert a.max_keywords == 10

    def test_stop_words_populated(self, analyzer: ContentTagAnalyzer) -> None:
        assert "the" in analyzer.stop_words
        assert "and" in analyzer.stop_words


class TestContentTagAnalyzerFile:
    def test_analyze_txt_file_returns_tags(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "quarterly_report.txt"
        f.write_text("Financial analysis of quarterly earnings report for 2026.")
        tags = analyzer.analyze_file(f)
        assert isinstance(tags, list)
        assert len(tags) >= 1

    def test_analyze_missing_file_returns_empty(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        tags = analyzer.analyze_file(tmp_path / "missing.txt")
        assert tags == []

    def test_analyze_includes_extension_tag(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "document.txt"
        f.write_text("content here")
        tags = analyzer.analyze_file(f)
        assert "txt" in tags or "document" in tags

    def test_analyze_filename_contributes_tags(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "python_tutorial.txt"
        f.write_text("This tutorial covers python basics.")
        tags = analyzer.analyze_file(f)
        assert "python" in tags or "tutorial" in tags

    def test_analyze_respects_max_keywords(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        a = ContentTagAnalyzer(max_keywords=5)
        f = tmp_path / "longfile.txt"
        f.write_text(" ".join(f"uniqueword{i}" for i in range(100)))
        tags = a.analyze_file(f)
        assert len(tags) < 6

    def test_analyze_md_file(self, analyzer: ContentTagAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Project Documentation\nThis is the documentation for the project.")
        tags = analyzer.analyze_file(f)
        assert len(tags) >= 1


class TestContentTagAnalyzerKeywords:
    def test_extract_keywords_empty_file(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        results = analyzer.extract_keywords(f)
        assert results == []

    def test_extract_keywords_returns_tuples(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "content.txt"
        f.write_text("Python programming language is widely used for data science.")
        results = analyzer.extract_keywords(f, top_n=5)
        assert len(results) >= 1
        if results:
            kw, score = results[0]
            assert len(kw) > 0
            assert 0.0 <= score <= 1.0

    def test_extract_keywords_missing_file(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        results = analyzer.extract_keywords(tmp_path / "missing.txt")
        assert results == []

    def test_extract_keywords_top_n_respected(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "text.txt"
        f.write_text(" ".join([f"word{i}" for i in range(50)] * 2))
        results = analyzer.extract_keywords(f, top_n=3)
        assert len(results) < 4


class TestContentTagAnalyzerEntities:
    def test_extract_entities_missing_file(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        result = analyzer.extract_entities(tmp_path / "missing.txt")
        assert result == []

    def test_extract_entities_from_content(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "article.txt"
        f.write_text("John Smith works at Google in California. NASA launched a rocket.")
        result = analyzer.extract_entities(f)
        assert len(result) >= 1

    def test_extract_entities_includes_acronyms(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "tech.txt"
        f.write_text("The API uses REST and HTTP protocol. The CEO approved it.")
        result = analyzer.extract_entities(f)
        assert isinstance(result, list)
        # Should find acronyms like API, REST, HTTP, CEO
        assert any(e in ("API", "REST", "HTTP", "CEO") for e in result)


class TestContentTagAnalyzerBatch:
    def test_batch_analyze_returns_dict(self, analyzer: ContentTagAnalyzer, tmp_path: Path) -> None:
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text("Machine learning algorithms")
        f2.write_text("Financial quarterly report")
        results = analyzer.batch_analyze([f1, f2])
        assert f1 in results
        assert f2 in results
        assert isinstance(results[f1], list)
        assert isinstance(results[f2], list)

    def test_batch_analyze_empty_list(self, analyzer: ContentTagAnalyzer) -> None:
        results = analyzer.batch_analyze([])
        assert results == {}

    def test_batch_analyze_missing_file_handled(
        self, analyzer: ContentTagAnalyzer, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.txt"
        results = analyzer.batch_analyze([missing])
        assert missing in results
        assert results[missing] == []
