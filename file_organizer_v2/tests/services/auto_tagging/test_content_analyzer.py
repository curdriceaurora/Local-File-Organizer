"""Tests for ContentTagAnalyzer."""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.content_analyzer import ContentTagAnalyzer


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def analyzer():
    """Create a ContentTagAnalyzer instance."""
    return ContentTagAnalyzer()


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text file."""
    file_path = temp_dir / "test_document.txt"
    content = """
    Machine Learning and Artificial Intelligence
    This document discusses neural networks and deep learning.
    Python programming is used for data science applications.
    Keywords: machine learning, AI, neural networks, python, data science
    """
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_code_file(temp_dir):
    """Create a sample code file."""
    file_path = temp_dir / "example_script.py"
    content = """
def process_data(input_file):
    # Data processing function
    with open(input_file, 'r') as f:
        data = f.read()
    return data.split()
    """
    file_path.write_text(content)
    return file_path


class TestContentTagAnalyzer:
    """Tests for ContentTagAnalyzer class."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = ContentTagAnalyzer(
            min_keyword_length=4,
            max_keywords=15
        )
        assert analyzer.min_keyword_length == 4
        assert analyzer.max_keywords == 15
        assert len(analyzer.stop_words) > 0

    def test_analyze_file_basic(self, analyzer, sample_text_file):
        """Test basic file analysis."""
        tags = analyzer.analyze_file(sample_text_file)

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should extract from filename
        assert 'test' in tags or 'document' in tags
        # Should extract from extension
        assert 'txt' in tags

    def test_analyze_nonexistent_file(self, analyzer, temp_dir):
        """Test analyzing nonexistent file."""
        fake_path = temp_dir / "nonexistent.txt"
        tags = analyzer.analyze_file(fake_path)
        assert tags == []

    def test_extract_keywords(self, analyzer, sample_text_file):
        """Test keyword extraction."""
        keywords = analyzer.extract_keywords(sample_text_file, top_n=10)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Check format: list of (word, score) tuples
        for keyword, score in keywords:
            assert isinstance(keyword, str)
            assert isinstance(score, float)
            assert score > 0

    def test_extract_keywords_with_scores(self, analyzer, sample_text_file):
        """Test that keyword scores are reasonable."""
        keywords = analyzer.extract_keywords(sample_text_file, top_n=5)

        if keywords:
            scores = [score for _, score in keywords]
            # Scores should be in descending order
            assert scores == sorted(scores, reverse=True)

    def test_extract_entities(self, analyzer, sample_text_file):
        """Test entity extraction."""
        entities = analyzer.extract_entities(sample_text_file)

        assert isinstance(entities, list)
        # Should find capitalized words/acronyms
        # The sample has "Machine Learning", "Artificial Intelligence", "Python"
        assert len(entities) > 0

    def test_batch_analyze(self, analyzer, temp_dir):
        """Test batch file analysis."""
        # Create multiple files
        file1 = temp_dir / "doc1.txt"
        file2 = temp_dir / "doc2.txt"
        file3 = temp_dir / "script.py"

        file1.write_text("Python programming tutorial")
        file2.write_text("Machine learning basics")
        file3.write_text("def main(): pass")

        files = [file1, file2, file3]
        results = analyzer.batch_analyze(files)

        assert len(results) == 3
        assert all(isinstance(tags, list) for tags in results.values())
        assert file1 in results
        assert file2 in results
        assert file3 in results

    def test_extract_from_filename(self, analyzer, temp_dir):
        """Test extraction from filename."""
        file_path = temp_dir / "machine-learning_tutorial-2024.txt"
        file_path.write_text("content")

        tags = analyzer.analyze_file(file_path)

        # Should split filename by delimiters
        assert 'machine' in tags or 'learning' in tags or 'tutorial' in tags

    def test_extract_from_extension(self, analyzer):
        """Test tag extraction from file extensions."""
        # Test document
        tags = analyzer._extract_from_extension(Path("test.pdf"))
        assert 'pdf' in tags
        assert 'document' in tags

        # Test image
        tags = analyzer._extract_from_extension(Path("photo.jpg"))
        assert 'jpg' in tags
        assert 'image' in tags

        # Test code
        tags = analyzer._extract_from_extension(Path("script.py"))
        assert 'py' in tags
        assert 'code' in tags

    def test_is_text_file(self, analyzer):
        """Test text file detection."""
        assert analyzer._is_text_file(Path("test.txt"))
        assert analyzer._is_text_file(Path("script.py"))
        assert analyzer._is_text_file(Path("data.json"))
        assert not analyzer._is_text_file(Path("image.jpg"))
        assert not analyzer._is_text_file(Path("video.mp4"))

    def test_read_text_content(self, analyzer, sample_text_file):
        """Test reading text content."""
        content = analyzer._read_text_content(sample_text_file)
        assert content
        assert "Machine Learning" in content
        assert "Python" in content

    def test_tokenize(self, analyzer):
        """Test text tokenization."""
        text = "Machine Learning and Deep Learning with Python"
        words = analyzer._tokenize(text)

        assert isinstance(words, list)
        # Should be lowercase
        assert all(w.islower() for w in words)
        # Should filter stop words
        assert 'and' not in words
        assert 'with' not in words
        # Should keep meaningful words
        assert 'machine' in words
        assert 'learning' in words
        assert 'python' in words

    def test_clean_tags(self, analyzer):
        """Test tag cleaning."""
        tags = [
            "python",
            "Python",  # Duplicate (case insensitive)
            "machine-learning",
            "ai",  # Too short by default
            "data_science",
            "test@tag",  # Has special char
            ""  # Empty
        ]

        cleaned = analyzer._clean_tags(tags)

        # Should remove duplicates
        assert cleaned.count('python') == 1
        # Should remove special characters (turns machine-learning to machinelearning)
        assert 'machinelearning' in cleaned or 'datascience' in cleaned
        # Should be lowercase
        assert all(tag.islower() for tag in cleaned)

    def test_extract_from_directory(self, analyzer, temp_dir):
        """Test extracting tags from directory structure."""
        subdir = temp_dir / "machine-learning-projects"
        subdir.mkdir()
        file_path = subdir / "test.txt"
        file_path.write_text("content")

        tags = analyzer._extract_from_directory(file_path)

        # Should extract from parent directory name
        assert 'machine' in tags or 'learning' in tags or 'projects' in tags

    def test_analyze_code_file(self, analyzer, sample_code_file):
        """Test analyzing a code file."""
        tags = analyzer.analyze_file(sample_code_file)

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should identify file type
        assert 'py' in tags or 'code' in tags
        # Should extract from filename or content
        assert 'example' in tags or 'script' in tags or 'processing' in tags or 'data' in tags

    def test_max_keywords_limit(self, analyzer, sample_text_file):
        """Test that max_keywords limit is respected."""
        analyzer.max_keywords = 5
        tags = analyzer.analyze_file(sample_text_file)

        assert len(tags) <= 5

    def test_min_keyword_length(self):
        """Test minimum keyword length filtering."""
        analyzer = ContentTagAnalyzer(min_keyword_length=5)

        text = "AI ML NLP deep learning machine"
        words = analyzer._tokenize(text)

        # Should filter short words
        assert 'deep' not in words  # Length 4
        assert 'learning' in words  # Length 8
        assert 'machine' in words  # Length 7

    def test_keyword_scoring(self, analyzer, sample_text_file):
        """Test that keywords are properly scored."""
        keywords = analyzer.extract_keywords(sample_text_file, top_n=10)

        if len(keywords) >= 2:
            # First keyword should have highest score
            first_score = keywords[0][1]
            last_score = keywords[-1][1]
            assert first_score >= last_score

    def test_empty_file(self, analyzer, temp_dir):
        """Test analyzing empty file."""
        empty_file = temp_dir / "empty.txt"
        empty_file.write_text("")

        tags = analyzer.analyze_file(empty_file)

        # Should still extract from filename and extension
        assert len(tags) > 0
        assert 'txt' in tags
