"""
Tests for FileHasher class.

Tests hash computation, chunk_size validation, and batch processing.
"""

import pytest
from pathlib import Path
from file_organizer.services.deduplication.hasher import FileHasher


class TestFileHasherInit:
    """Test FileHasher initialization and chunk_size validation."""

    def test_default_chunk_size(self):
        """Test hasher with default chunk size."""
        hasher = FileHasher()
        assert hasher.chunk_size == FileHasher.DEFAULT_CHUNK_SIZE

    def test_custom_valid_chunk_size(self):
        """Test hasher with custom valid chunk size."""
        custom_size = 8192  # 8KB
        hasher = FileHasher(chunk_size=custom_size)
        assert hasher.chunk_size == custom_size

    def test_chunk_size_at_minimum(self):
        """Test chunk_size at minimum boundary (1KB)."""
        hasher = FileHasher(chunk_size=FileHasher.MIN_CHUNK_SIZE)
        assert hasher.chunk_size == FileHasher.MIN_CHUNK_SIZE

    def test_chunk_size_at_maximum(self):
        """Test chunk_size at maximum boundary (10MB)."""
        hasher = FileHasher(chunk_size=FileHasher.MAX_CHUNK_SIZE)
        assert hasher.chunk_size == FileHasher.MAX_CHUNK_SIZE

    def test_chunk_size_too_small(self):
        """Test that chunk_size below minimum raises ValueError."""
        with pytest.raises(ValueError, match="must be at least"):
            FileHasher(chunk_size=512)  # Less than 1KB

    def test_chunk_size_zero(self):
        """Test that chunk_size of zero raises ValueError."""
        with pytest.raises(ValueError, match="must be at least"):
            FileHasher(chunk_size=0)

    def test_chunk_size_negative(self):
        """Test that negative chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="must be at least"):
            FileHasher(chunk_size=-1024)

    def test_chunk_size_too_large(self):
        """Test that chunk_size above maximum raises ValueError."""
        with pytest.raises(ValueError, match="must not exceed"):
            FileHasher(chunk_size=11 * 1024 * 1024)  # 11MB (over limit)

    def test_chunk_size_not_integer(self):
        """Test that non-integer chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="must be an integer"):
            FileHasher(chunk_size=8192.5)  # type: ignore

    def test_chunk_size_string(self):
        """Test that string chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="must be an integer"):
            FileHasher(chunk_size="8192")  # type: ignore


class TestFileHasherComputeHash:
    """Test hash computation functionality."""

    def test_compute_hash_sha256(self, tmp_path):
        """Test SHA256 hash computation."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hasher = FileHasher()
        hash_value = hasher.compute_hash(test_file, algorithm="sha256")

        # Verify hash is a hex string
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 produces 64 hex characters
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_compute_hash_md5(self, tmp_path):
        """Test MD5 hash computation."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hasher = FileHasher()
        hash_value = hasher.compute_hash(test_file, algorithm="md5")

        # Verify hash is a hex string
        assert isinstance(hash_value, str)
        assert len(hash_value) == 32  # MD5 produces 32 hex characters
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_same_content_same_hash(self, tmp_path):
        """Test that identical files produce identical hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = "Identical content"

        file1.write_text(content)
        file2.write_text(content)

        hasher = FileHasher()
        hash1 = hasher.compute_hash(file1)
        hash2 = hasher.compute_hash(file2)

        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        """Test that different files produce different hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        hasher = FileHasher()
        hash1 = hasher.compute_hash(file1)
        hash2 = hasher.compute_hash(file2)

        assert hash1 != hash2

    def test_compute_hash_file_not_found(self):
        """Test that computing hash of non-existent file raises error."""
        hasher = FileHasher()
        with pytest.raises(FileNotFoundError):
            hasher.compute_hash(Path("/nonexistent/file.txt"))

    def test_compute_hash_directory(self, tmp_path):
        """Test that computing hash of directory raises error."""
        hasher = FileHasher()
        with pytest.raises(ValueError, match="not a file"):
            hasher.compute_hash(tmp_path)

    def test_compute_hash_invalid_algorithm(self, tmp_path):
        """Test that invalid algorithm raises error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        hasher = FileHasher()
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            hasher.compute_hash(test_file, algorithm="sha512")  # type: ignore


class TestFileHasherChunkSizes:
    """Test that different chunk sizes produce same hash."""

    def test_different_chunk_sizes_same_result(self, tmp_path):
        """Test that different chunk sizes produce identical hashes."""
        # Create a file larger than default chunk size
        test_file = tmp_path / "large_file.txt"
        content = "A" * 100000  # 100KB file
        test_file.write_text(content)

        # Compute hash with different chunk sizes
        hasher_small = FileHasher(chunk_size=1024)  # 1KB
        hasher_default = FileHasher()  # 64KB
        hasher_large = FileHasher(chunk_size=1024 * 1024)  # 1MB

        hash_small = hasher_small.compute_hash(test_file)
        hash_default = hasher_default.compute_hash(test_file)
        hash_large = hasher_large.compute_hash(test_file)

        # All should produce the same hash
        assert hash_small == hash_default == hash_large


class TestFileHasherBatch:
    """Test batch processing functionality."""

    def test_compute_batch_multiple_files(self, tmp_path):
        """Test batch hashing of multiple files."""
        # Create test files
        files = []
        for i in range(5):
            file = tmp_path / f"file{i}.txt"
            file.write_text(f"Content {i}")
            files.append(file)

        hasher = FileHasher()
        results = hasher.compute_batch(files)

        # Verify all files were hashed
        assert len(results) == 5
        for file in files:
            assert file in results
            assert isinstance(results[file], str)
            assert len(results[file]) == 64  # SHA256

    def test_compute_batch_with_missing_file(self, tmp_path):
        """Test batch processing skips missing files."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("Exists")
        file2 = tmp_path / "missing.txt"  # Not created

        hasher = FileHasher()
        results = hasher.compute_batch([file1, file2])

        # Should only have result for existing file
        assert len(results) == 1
        assert file1 in results
        assert file2 not in results


class TestFileHasherGetFileSize:
    """Test file size retrieval."""

    def test_get_file_size(self, tmp_path):
        """Test getting file size."""
        test_file = tmp_path / "test.txt"
        content = "A" * 1000
        test_file.write_text(content)

        hasher = FileHasher()
        size = hasher.get_file_size(test_file)

        assert size == len(content)

    def test_get_file_size_not_found(self):
        """Test getting size of non-existent file."""
        hasher = FileHasher()
        with pytest.raises(FileNotFoundError):
            hasher.get_file_size(Path("/nonexistent/file.txt"))


class TestFileHasherValidateAlgorithm:
    """Test algorithm validation."""

    def test_validate_md5(self):
        """Test validating MD5 algorithm."""
        result = FileHasher.validate_algorithm("md5")
        assert result == "md5"

    def test_validate_sha256(self):
        """Test validating SHA256 algorithm."""
        result = FileHasher.validate_algorithm("sha256")
        assert result == "sha256"

    def test_validate_uppercase(self):
        """Test validation handles uppercase."""
        result = FileHasher.validate_algorithm("SHA256")
        assert result == "sha256"

    def test_validate_invalid(self):
        """Test validating invalid algorithm."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            FileHasher.validate_algorithm("sha512")
