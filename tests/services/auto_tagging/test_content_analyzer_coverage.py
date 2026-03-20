"""Coverage tests for ContentTagAnalyzer — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.content_analyzer import ContentTagAnalyzer

pytestmark = pytest.mark.unit


@pytest.fixture()
def analyzer():
    return ContentTagAnalyzer()


# ---------------------------------------------------------------------------
# analyze_file
# ---------------------------------------------------------------------------


class TestAnalyzeFile:
    def test_nonexistent_file(self, analyzer):
        result = analyzer.analyze_file(Path("nonexistent/file.txt"))
        assert result == []

    def test_text_file(self, analyzer, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("Python programming tutorial advanced concepts")
        tags = analyzer.analyze_file(f)
        assert isinstance(tags, list)
        assert len(tags) > 0

    def test_non_text_file(self, analyzer, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        tags = analyzer.analyze_file(f)
        assert isinstance(tags, list)
        # Should have extension-based tags at minimum
        assert "png" in tags or "image" in tags

    def test_max_keywords_limit(self, tmp_path):
        analyzer = ContentTagAnalyzer(max_keywords=3)
        f = tmp_path / "big.txt"
        f.write_text("alpha bravo charlie delta echo foxtrot golf hotel " * 10)
        tags = analyzer.analyze_file(f)
        assert len(tags) == 3  # max_keywords=3 with 8 unique words x 10 reps -> exactly 3


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    def test_nonexistent_file(self, analyzer):
        assert analyzer.extract_keywords(Path("no/such.txt")) == []

    def test_non_text_file(self, analyzer, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert analyzer.extract_keywords(f) == []

    def test_empty_text_file(self, analyzer, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert analyzer.extract_keywords(f) == []

    def test_returns_scored_keywords(self, analyzer, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text(
            "python programming language python code python development "
            "software engineering machine learning artificial intelligence"
        )
        results = analyzer.extract_keywords(f, top_n=5)
        assert 1 <= len(results) <= 5  # at most 5 (top_n cap); at least 1 (rich content)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # First keyword should have the highest score
        if len(results) > 1:
            assert results[0][1] >= results[1][1]

    def test_long_word_boost(self, analyzer, tmp_path):
        f = tmp_path / "doc.txt"
        # "programming" is >6 chars, should get boost; "code" is <=6 chars
        f.write_text("programming " * 20 + "code " * 20)
        results = analyzer.extract_keywords(f, top_n=10)
        assert len(results) > 0
        scores = dict(results)
        # "programming" should score higher than "code" due to long-word boost
        if "programming" in scores and "code" in scores:
            assert scores["programming"] > scores["code"]


# ---------------------------------------------------------------------------
# extract_entities
# ---------------------------------------------------------------------------


class TestExtractEntities:
    def test_nonexistent_file(self, analyzer):
        assert analyzer.extract_entities(Path("no/such.txt")) == []

    def test_non_text_file(self, analyzer, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8\xff\xe0")
        assert analyzer.extract_entities(f) == []

    def test_empty_content(self, analyzer, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert analyzer.extract_entities(f) == []

    def test_extracts_proper_nouns(self, analyzer, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text(
            "John Smith visited Microsoft headquarters. "
            "The CEO of Google announced the project. "
            "NASA launched a new satellite."
        )
        entities = analyzer.extract_entities(f)
        assert any("John" in e for e in entities) or any("Smith" in e for e in entities)

    def test_extracts_acronyms(self, analyzer, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("NASA and CERN collaborated on the LHC project.")
        entities = analyzer.extract_entities(f)
        assert "NASA" in entities or "CERN" in entities


# ---------------------------------------------------------------------------
# batch_analyze
# ---------------------------------------------------------------------------


class TestBatchAnalyze:
    def test_batch_multiple_files(self, analyzer, tmp_path):
        f1 = tmp_path / "one.txt"
        f1.write_text("python programming")
        f2 = tmp_path / "two.txt"
        f2.write_text("java development")
        results = analyzer.batch_analyze([f1, f2])
        assert f1 in results
        assert f2 in results

    def test_batch_with_error(self, analyzer, tmp_path):
        f1 = tmp_path / "good.txt"
        f1.write_text("content")
        f2 = Path("nonexistent/bad.txt")
        results = analyzer.batch_analyze([f1, f2])
        assert f1 in results
        assert f2 in results
        assert results[f2] == []


# ---------------------------------------------------------------------------
# _extract_from_extension
# ---------------------------------------------------------------------------


class TestExtractFromExtension:
    def test_known_extensions(self, analyzer, tmp_path):
        for ext, category in [
            (".py", "code"),
            (".pdf", "document"),
            (".jpg", "image"),
            (".mp4", "video"),
            (".mp3", "audio"),
            (".zip", "archive"),
            (".xlsx", "spreadsheet"),
            (".pptx", "presentation"),
        ]:
            f = tmp_path / f"test{ext}"
            f.write_text("x")
            tags = analyzer._extract_from_extension(f)
            assert category in tags

    def test_no_extension(self, analyzer, tmp_path):
        f = tmp_path / "noext"
        f.write_text("x")
        tags = analyzer._extract_from_extension(f)
        assert tags == []


# ---------------------------------------------------------------------------
# _extract_from_directory
# ---------------------------------------------------------------------------


class TestExtractFromDirectory:
    def test_directory_tags(self, analyzer, tmp_path):
        d = tmp_path / "project-alpha"
        d.mkdir()
        f = d / "file.txt"
        f.write_text("x")
        tags = analyzer._extract_from_directory(f)
        assert "project" in tags or "alpha" in tags

    def test_common_dir_filtered(self, analyzer, tmp_path):
        d = tmp_path / "downloads"
        d.mkdir()
        f = d / "file.txt"
        f.write_text("x")
        tags = analyzer._extract_from_directory(f)
        assert "downloads" not in tags


# ---------------------------------------------------------------------------
# _extract_from_metadata
# ---------------------------------------------------------------------------


class TestExtractFromMetadata:
    def test_small_file(self, analyzer, tmp_path):
        f = tmp_path / "tiny.txt"
        f.write_text("x")
        tags = analyzer._extract_from_metadata(f)
        assert "small" in tags

    def test_nonexistent_file(self, analyzer):
        tags = analyzer._extract_from_metadata(Path("no/such/file"))
        assert tags == []


# ---------------------------------------------------------------------------
# _read_text_content
# ---------------------------------------------------------------------------


class TestReadTextContent:
    def test_read_utf8(self, analyzer, tmp_path):
        f = tmp_path / "utf8.txt"
        f.write_text("hello world", encoding="utf-8")
        content = analyzer._read_text_content(f)
        assert content == "hello world"

    def test_read_latin1_fallback(self, analyzer, tmp_path):
        f = tmp_path / "latin1.txt"
        f.write_bytes(b"caf\xe9")
        content = analyzer._read_text_content(f)
        assert "café" in content

    def test_too_large_file(self, analyzer, tmp_path):
        f = tmp_path / "big.txt"
        # Create a file > 5 MB
        f.write_text("x" * (6 * 1024 * 1024))
        content = analyzer._read_text_content(f)
        assert content == ""


# ---------------------------------------------------------------------------
# _clean_tags
# ---------------------------------------------------------------------------


class TestCleanTags:
    def test_removes_duplicates(self, analyzer):
        tags = analyzer._clean_tags(["python", "Python", "PYTHON"])
        assert len(tags) == 1

    def test_removes_short_tags(self, analyzer):
        tags = analyzer._clean_tags(["py", "ab", "python"])
        assert "python" in tags
        assert "py" not in tags

    def test_removes_special_chars(self, analyzer):
        tags = analyzer._clean_tags(["hello!world", "test@tag"])
        assert tags
        assert all(c.isalnum() or c == "-" for tag in tags for c in tag)
