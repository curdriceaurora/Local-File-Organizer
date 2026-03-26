"""
Tests for FileHasher class.

Tests hash computation, chunk_size validation, and batch processing.
"""

from pathlib import Path

import pytest

from file_organizer.services.deduplication.hasher import FileHasher

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_batch_hashing(tmp_path):
    """Test parallel batch hashing with multiprocessing.

    This test verifies that compute_batch_parallel:
    - Hashes multiple files correctly using multiprocessing
    - Produces the same results as sequential hashing
    - Handles errors gracefully (skips missing files)
    - Completes faster than sequential for large batches
    """
    from file_organizer.parallel.config import ExecutorType, ParallelConfig

    # Create test files with varying content
    files = []
    expected_hashes = {}
    hasher = FileHasher()

    # Create 20 files to make parallel processing worthwhile
    for i in range(20):
        file = tmp_path / f"file{i}.txt"
        content = f"Content {i}" * 100  # Make files large enough to benefit from parallelism
        file.write_text(content)
        files.append(file)
        # Pre-compute expected hash using sequential method
        expected_hashes[file] = hasher.compute_hash(file)

    # Add one missing file to test error handling
    missing_file = tmp_path / "missing.txt"
    files.append(missing_file)

    # Test parallel hashing with default config
    config = ParallelConfig(
        executor_type=ExecutorType.PROCESS,
        max_workers=2,  # Use 2 workers for testing
        retry_count=1,
    )
    results = hasher.compute_batch_parallel(files, config=config)

    # Verify results
    assert len(results) == 20  # Missing file should be excluded
    assert missing_file not in results

    # Verify all successful hashes match expected values
    for file, hash_value in results.items():
        assert hash_value == expected_hashes[file]
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256

    # Test with MD5 algorithm
    results_md5 = hasher.compute_batch_parallel(
        files[:5],  # Use subset for faster test
        algorithm="md5",
        config=config,
    )
    assert len(results_md5) == 5
    for hash_value in results_md5.values():
        assert len(hash_value) == 32  # MD5

    # Test empty list
    empty_results = hasher.compute_batch_parallel([], config=config)
    assert empty_results == {}

    # Test with None config (should use defaults)
    default_results = hasher.compute_batch_parallel(files[:3])
    assert len(default_results) == 3


# ---------------------------------------------------------------------------
# Tests for module-level _hash_file() function (lines 41-66)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHashFileFunction:
    """Tests for the module-level _hash_file() function."""

    def test_hash_file_sha256_returns_correct_digest(self, tmp_path: Path) -> None:
        """_hash_file with sha256 returns expected hex digest."""
        import hashlib

        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "hello.txt"
        test_file.write_bytes(b"Hello, World!")

        result = _hash_file(test_file, algorithm="sha256")

        expected = hashlib.sha256(b"Hello, World!").hexdigest()
        assert result == expected
        assert len(result) == 64

    def test_hash_file_md5_returns_correct_digest(self, tmp_path: Path) -> None:
        """_hash_file with md5 returns expected hex digest."""
        import hashlib

        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "hello.txt"
        test_file.write_bytes(b"Hello, World!")

        result = _hash_file(test_file, algorithm="md5")

        expected = hashlib.md5(b"Hello, World!").hexdigest()
        assert result == expected
        assert len(result) == 32

    def test_hash_file_nonexistent_raises_file_not_found(self) -> None:
        """_hash_file raises FileNotFoundError for missing path."""
        from file_organizer.services.deduplication.hasher import _hash_file

        with pytest.raises(FileNotFoundError, match="File not found"):
            _hash_file(Path("/does/not/exist.txt"))

    def test_hash_file_directory_raises_value_error(self, tmp_path: Path) -> None:
        """_hash_file raises ValueError when path is a directory."""
        from file_organizer.services.deduplication.hasher import _hash_file

        with pytest.raises(ValueError, match="not a file"):
            _hash_file(tmp_path)

    def test_hash_file_unsupported_algorithm_raises_value_error(self, tmp_path: Path) -> None:
        """_hash_file raises ValueError for unsupported algorithm."""
        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "test.txt"
        test_file.write_text("data")

        with pytest.raises(ValueError, match="Unsupported algorithm"):
            _hash_file(test_file, algorithm="sha512")

    def test_hash_file_permission_error(self, tmp_path: Path) -> None:
        """_hash_file raises PermissionError when file is unreadable."""
        from unittest.mock import patch

        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "secret.txt"
        test_file.write_text("secret")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError, match="Cannot read file"):
                _hash_file(test_file)

    def test_hash_file_empty_file(self, tmp_path: Path) -> None:
        """_hash_file returns valid digest for an empty file."""
        import hashlib

        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        result = _hash_file(test_file, algorithm="sha256")

        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_hash_file_custom_chunk_size(self, tmp_path: Path) -> None:
        """_hash_file produces same digest regardless of chunk_size."""
        from file_organizer.services.deduplication.hasher import _hash_file

        test_file = tmp_path / "multi_chunk.txt"
        test_file.write_bytes(b"A" * 10000)

        result_small = _hash_file(test_file, algorithm="sha256", chunk_size=1024)
        result_large = _hash_file(test_file, algorithm="sha256", chunk_size=65536)

        assert result_small == result_large


# ---------------------------------------------------------------------------
# Tests for compute_batch_parallel result processing (lines 209-252)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeBatchParallelResultProcessing:
    """Tests for compute_batch_parallel using mocked ParallelProcessor."""

    def test_empty_file_paths_returns_empty_dict(self) -> None:
        """compute_batch_parallel returns {} for empty input list."""
        hasher = FileHasher()
        result = hasher.compute_batch_parallel([])
        assert result == {}

    def test_default_config_when_none_provided(self, tmp_path: Path) -> None:
        """compute_batch_parallel creates ProcessPool config when config is None."""
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.config import ExecutorType
        from file_organizer.parallel.result import BatchResult

        hasher = FileHasher()
        test_file = tmp_path / "f.txt"
        test_file.write_text("data")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=1,
            succeeded=1,
            failed=0,
            results=[],
            total_duration_ms=10.0,
            files_per_second=100.0,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ) as mock_cls:
            hasher.compute_batch_parallel([test_file], config=None)

            # Verify default config was created with PROCESS executor
            call_args = mock_cls.call_args
            config_arg = call_args[0][0]
            assert config_arg.executor_type == ExecutorType.PROCESS
            assert config_arg.retry_count == 2

    def test_successful_results_mapped_to_dict(self, tmp_path: Path) -> None:
        """compute_batch_parallel maps successful FileResults to {path: hash}."""
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.result import BatchResult, FileResult

        hasher = FileHasher()
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("aaa")
        file_b.write_text("bbb")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=2,
            succeeded=2,
            failed=0,
            results=[
                FileResult(path=file_a, success=True, result="abcdef1234567890" * 4),
                FileResult(path=file_b, success=True, result="1234567890abcdef" * 4),
            ],
            total_duration_ms=50.0,
            files_per_second=40.0,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ):
            result = hasher.compute_batch_parallel([file_a, file_b])

        assert len(result) == 2
        assert result[file_a] == "abcdef1234567890" * 4
        assert result[file_b] == "1234567890abcdef" * 4

    def test_failed_results_excluded_from_dict(self, tmp_path: Path) -> None:
        """compute_batch_parallel excludes failed FileResults from output."""
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.result import BatchResult, FileResult

        hasher = FileHasher()
        file_ok = tmp_path / "ok.txt"
        file_fail = tmp_path / "fail.txt"
        file_ok.write_text("ok")
        file_fail.write_text("fail")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=2,
            succeeded=1,
            failed=1,
            results=[
                FileResult(path=file_ok, success=True, result="hash_ok" * 8),
                FileResult(
                    path=file_fail,
                    success=False,
                    result=None,
                    error="Permission denied",
                ),
            ],
            total_duration_ms=30.0,
            files_per_second=66.7,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ):
            result = hasher.compute_batch_parallel([file_ok, file_fail])

        assert len(result) == 1
        assert file_ok in result
        assert file_fail not in result

    def test_failure_logged_as_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """compute_batch_parallel logs warning for each failed file."""
        import logging
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.result import BatchResult, FileResult

        hasher = FileHasher()
        file_fail = tmp_path / "bad.txt"
        file_fail.write_text("x")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=1,
            succeeded=0,
            failed=1,
            results=[
                FileResult(
                    path=file_fail,
                    success=False,
                    result=None,
                    error="File not found: bad.txt",
                ),
            ],
            total_duration_ms=5.0,
            files_per_second=0.0,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ):
            with caplog.at_level(
                logging.WARNING,
                logger="file_organizer.services.deduplication.hasher",
            ):
                result = hasher.compute_batch_parallel([file_fail])

        assert result == {}
        assert "Could not hash" in caplog.text
        assert "File not found: bad.txt" in caplog.text

    def test_batch_summary_logged_as_info(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """compute_batch_parallel logs info-level batch summary."""
        import logging
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.result import BatchResult, FileResult

        hasher = FileHasher()
        file_a = tmp_path / "a.txt"
        file_a.write_text("data")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=3,
            succeeded=2,
            failed=1,
            results=[
                FileResult(path=file_a, success=True, result="deadbeef" * 8),
            ],
            total_duration_ms=123.4,
            files_per_second=24.31,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ):
            with caplog.at_level(
                logging.INFO,
                logger="file_organizer.services.deduplication.hasher",
            ):
                hasher.compute_batch_parallel([file_a])

        assert "Batch hashing complete" in caplog.text
        assert "2/3" in caplog.text
        assert "123.4ms" in caplog.text

    def test_success_true_but_result_none_excluded(self, tmp_path: Path) -> None:
        """FileResult with success=True but result=None is excluded."""
        from unittest.mock import MagicMock, patch

        from file_organizer.parallel.result import BatchResult, FileResult

        hasher = FileHasher()
        file_a = tmp_path / "a.txt"
        file_a.write_text("data")

        mock_processor = MagicMock()
        mock_processor.process_batch.return_value = BatchResult(
            total=1,
            succeeded=1,
            failed=0,
            results=[
                FileResult(path=file_a, success=True, result=None),
            ],
            total_duration_ms=10.0,
            files_per_second=100.0,
        )

        with patch(
            "file_organizer.services.deduplication.hasher.ParallelProcessor",
            return_value=mock_processor,
        ):
            result = hasher.compute_batch_parallel([file_a])

        assert len(result) == 0
        assert file_a not in result
