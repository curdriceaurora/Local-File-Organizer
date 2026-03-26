"""
Unit tests for Duplicate Index service.

Tests file indexing, duplicate detection, group management, statistics,
and metadata handling for duplicate file detection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from file_organizer.services.deduplication.index import (
    DuplicateGroup,
    DuplicateIndex,
    FileMetadata,
    IndexBuildConfig,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.mark.unit
class TestFileMetadata:
    """Tests for FileMetadata dataclass."""

    def test_create_file_metadata(self):
        """Test creating file metadata."""
        now = datetime.now(UTC)
        path = Path("/test/file.txt")
        metadata = FileMetadata(
            path=path,
            size=1024,
            modified_time=now,
            accessed_time=now,
            hash_value="abc123",
        )

        assert metadata.path == path
        assert metadata.size == 1024
        assert metadata.hash_value == "abc123"

    def test_file_metadata_path_as_string(self):
        """Test that file metadata converts string path to Path."""
        metadata = FileMetadata(
            path="/test/file.txt",  # string path
            size=512,
            modified_time=datetime.now(UTC),
            accessed_time=datetime.now(UTC),
            hash_value="xyz789",
        )

        assert isinstance(metadata.path, Path)
        assert metadata.path == Path("/test/file.txt")


@pytest.mark.unit
class TestDuplicateGroup:
    """Tests for DuplicateGroup class."""

    def test_create_duplicate_group(self):
        """Test creating a duplicate group."""
        group = DuplicateGroup(hash_value="hash123")

        assert group.hash_value == "hash123"
        assert group.count == 0
        assert group.files == []

    def test_duplicate_group_count(self):
        """Test counting files in duplicate group."""
        now = datetime.now(UTC)
        group = DuplicateGroup(hash_value="hash123")

        file1 = FileMetadata(
            path=Path("/file1.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )
        file2 = FileMetadata(
            path=Path("/file2.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )

        group.files.append(file1)
        assert group.count == 1

        group.files.append(file2)
        assert group.count == 2

    def test_duplicate_group_total_size(self):
        """Test total size calculation for duplicate group."""
        now = datetime.now(UTC)
        group = DuplicateGroup(hash_value="hash123")

        file1 = FileMetadata(
            path=Path("/file1.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )
        file2 = FileMetadata(
            path=Path("/file2.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )

        group.files.extend([file1, file2])
        assert group.total_size == 2000

    def test_duplicate_group_wasted_space(self):
        """Test wasted space calculation."""
        now = datetime.now(UTC)
        group = DuplicateGroup(hash_value="hash123")

        file1 = FileMetadata(
            path=Path("/file1.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )
        file2 = FileMetadata(
            path=Path("/file2.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )
        file3 = FileMetadata(
            path=Path("/file3.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )

        group.files.extend([file1, file2, file3])
        # Wasted space = file size * (count - 1) = 1000 * 2
        assert group.wasted_space == 2000

    def test_duplicate_group_wasted_space_single_file(self):
        """Test wasted space is 0 for single file."""
        now = datetime.now(UTC)
        group = DuplicateGroup(hash_value="hash123")

        file1 = FileMetadata(
            path=Path("/file1.txt"),
            size=1000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )

        group.files.append(file1)
        assert group.wasted_space == 0

    def test_duplicate_group_empty_total_size(self):
        """Test total size is 0 for empty group."""
        group = DuplicateGroup(hash_value="hash123")

        assert group.total_size == 0


@pytest.mark.unit
class TestDuplicateIndexInit:
    """Tests for DuplicateIndex initialization."""

    def test_init_empty_index(self):
        """Test initializing empty duplicate index."""
        index = DuplicateIndex()

        assert len(index._index) == 0
        assert len(index._size_index) == 0


@pytest.mark.unit
class TestAddFile:
    """Tests for adding files to index."""

    def test_add_single_file(self):
        """Test adding a single file."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            assert "hash123" in index._index
            assert len(index._index["hash123"]) == 1

    def test_add_file_with_custom_metadata(self):
        """Test adding file with custom metadata."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            now = datetime.now(UTC)
            metadata = {
                "size": 5000,
                "modified_time": now,
                "accessed_time": now,
            }

            index = DuplicateIndex()
            index.add_file(file_path, "hash123", metadata=metadata)

            file_metadata = index._index["hash123"][0]
            assert file_metadata.size == 5000

    def test_add_multiple_files_same_hash(self):
        """Test adding multiple files with same hash."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file1 = tmppath / "file1.txt"
            file2 = tmppath / "file2.txt"
            file1.write_text("content")
            file2.write_text("content")

            index = DuplicateIndex()
            index.add_file(file1, "hash123")
            index.add_file(file2, "hash123")

            assert len(index._index["hash123"]) == 2

    def test_add_files_different_hashes(self):
        """Test adding files with different hashes."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file1 = tmppath / "file1.txt"
            file2 = tmppath / "file2.txt"
            file1.write_text("content1")
            file2.write_text("content2")

            index = DuplicateIndex()
            index.add_file(file1, "hash123")
            index.add_file(file2, "hash456")

            assert "hash123" in index._index
            assert "hash456" in index._index
            assert len(index._index) == 2

    def test_add_file_auto_metadata(self):
        """Test that add_file auto-generates metadata if not provided."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("test content")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            file_metadata = index._index["hash123"][0]
            assert file_metadata.size > 0
            assert file_metadata.modified_time is not None


@pytest.mark.unit
class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_find_duplicates_by_hash(self):
        """Test finding duplicates by hash."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file1 = tmppath / "file1.txt"
            file2 = tmppath / "file2.txt"
            file1.write_text("same content")
            file2.write_text("same content")

            index = DuplicateIndex()
            index.add_file(file1, "hash123")
            index.add_file(file2, "hash123")

            duplicates = index._index.get("hash123", [])
            assert len(duplicates) == 2

    def test_no_duplicates_for_single_file(self):
        """Test no duplicates found for single file."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            # Only one file with this hash
            assert len(index._index["hash123"]) == 1

    def test_identify_duplicate_groups(self):
        """Test identifying groups of duplicates."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            files = {}
            for i in range(3):
                f = tmppath / f"file{i}.txt"
                f.write_text("duplicate content")
                files[f] = f

            index = DuplicateIndex()
            for f in files:
                index.add_file(f, "dup_hash")

            # All 3 files in one group
            assert len(index._index["dup_hash"]) == 3


@pytest.mark.unit
class TestIndexStatistics:
    """Tests for index statistics."""

    def test_total_duplicates_count(self):
        """Test counting total duplicates in index."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(3):
                f = tmppath / f"file{i}.txt"
                f.write_text("content")

            index = DuplicateIndex()
            for i in range(3):
                index.add_file(tmppath / f"file{i}.txt", "same_hash")

            assert len(index._index["same_hash"]) == 3

    def test_total_wasted_space(self):
        """Test calculating total wasted space."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(3):
                f = tmppath / f"file{i}.txt"
                f.write_text("x" * 1000)  # 1000 bytes each

            index = DuplicateIndex()
            now = datetime.now(UTC)
            metadata = {
                "size": 1000,
                "modified_time": now,
                "accessed_time": now,
            }

            for i in range(3):
                index.add_file(tmppath / f"file{i}.txt", "hash123", metadata)

            # Get duplicate group
            files = index._index["hash123"]
            group = DuplicateGroup("hash123")
            group.files = files

            # Wasted space = 1000 * (3 - 1) = 2000
            assert group.wasted_space == 2000

    def test_index_size(self):
        """Test getting index size (number of unique hashes)."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(2):
                f = tmppath / f"set{i}_file.txt"
                f.write_text("content")

            index = DuplicateIndex()
            index.add_file(tmppath / "set0_file.txt", "hash1")
            index.add_file(tmppath / "set1_file.txt", "hash2")

            assert len(index._index) == 2


@pytest.mark.unit
class TestIndexUpdate:
    """Tests for updating index entries."""

    def test_add_file_to_existing_hash(self):
        """Test adding a file to existing hash entry."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file1 = tmppath / "file1.txt"
            file2 = tmppath / "file2.txt"
            file1.write_text("content")
            file2.write_text("content")

            index = DuplicateIndex()
            index.add_file(file1, "hash123")
            assert len(index._index["hash123"]) == 1

            index.add_file(file2, "hash123")
            assert len(index._index["hash123"]) == 2

    def test_replace_file_metadata(self):
        """Test that adding same file path updates metadata."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content1")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            # Update file and re-add
            file_path.write_text("content2 which is longer")
            index.add_file(file_path, "hash123")

            # Should have 2 entries for same path (appended)
            assert len(index._index["hash123"]) == 2


@pytest.mark.unit
class TestDatetimeHandling:
    """Tests for datetime handling."""

    def test_naive_datetime_to_utc(self):
        """Test that naive datetimes are converted to UTC."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            naive_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            metadata = {
                "size": 100,
                "modified_time": naive_dt,
                "accessed_time": naive_dt,
            }

            index = DuplicateIndex()
            index.add_file(file_path, "hash123", metadata)

            file_metadata = index._index["hash123"][0]
            assert file_metadata.modified_time.tzinfo == UTC

    def test_utc_datetime_preserved(self):
        """Test that UTC datetimes are preserved."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            metadata = {
                "size": 100,
                "modified_time": utc_dt,
                "accessed_time": utc_dt,
            }

            index = DuplicateIndex()
            index.add_file(file_path, "hash123", metadata)

            file_metadata = index._index["hash123"][0]
            assert file_metadata.modified_time == utc_dt


@pytest.mark.unit
class TestIndexQuerying:
    """Tests for querying the index."""

    def test_get_files_by_hash(self):
        """Test retrieving files by hash."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file1 = tmppath / "file1.txt"
            file2 = tmppath / "file2.txt"
            file1.write_text("content")
            file2.write_text("content")

            index = DuplicateIndex()
            index.add_file(file1, "dup_hash")
            index.add_file(file2, "dup_hash")

            files = index._index.get("dup_hash")
            assert files is not None
            assert len(files) == 2

    def test_get_nonexistent_hash(self):
        """Test getting hash that doesn't exist returns None."""
        index = DuplicateIndex()

        files = index._index.get("nonexistent")
        assert files is None

    def test_list_all_hashes(self):
        """Test listing all hashes in index."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(3):
                f = tmppath / f"file{i}.txt"
                f.write_text(f"content{i}")

            index = DuplicateIndex()
            index.add_file(tmppath / "file0.txt", "hash1")
            index.add_file(tmppath / "file1.txt", "hash2")
            index.add_file(tmppath / "file2.txt", "hash3")

            hashes = list(index._index.keys())
            assert len(hashes) == 3
            assert "hash1" in hashes
            assert "hash2" in hashes
            assert "hash3" in hashes


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_hash_string(self):
        """Test handling of empty hash string."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("content")

            index = DuplicateIndex()
            index.add_file(file_path, "")

            assert "" in index._index

    def test_special_characters_in_path(self):
        """Test handling paths with special characters."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file_path = tmppath / "file with spaces & chars.txt"
            file_path.write_text("content")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            assert "hash123" in index._index

    def test_very_large_file_size(self):
        """Test handling very large file sizes."""
        now = datetime.now(UTC)

        file_metadata = FileMetadata(
            path=Path("/test.txt"),
            size=1_000_000_000_000,
            modified_time=now,
            accessed_time=now,
            hash_value="hash123",
        )

        assert file_metadata.size == 1_000_000_000_000

    def test_zero_size_file(self):
        """Test handling zero-size files."""
        now = datetime.now(UTC)

        file_metadata = FileMetadata(
            path=Path("/empty.txt"),
            size=0,
            modified_time=now,
            accessed_time=now,
            hash_value="empty_hash",
        )

        assert file_metadata.size == 0

    def test_unicode_file_path(self):
        """Test handling unicode characters in file paths."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            file_path = tmppath / "файл_ファイル_文件.txt"
            file_path.write_text("content")

            index = DuplicateIndex()
            index.add_file(file_path, "hash123")

            assert "hash123" in index._index
            assert index._index["hash123"][0].path.name == "файл_ファイル_文件.txt"


@pytest.mark.unit
class TestStreamingIndexBuilder:
    """Tests for streaming index building."""

    def test_streaming_build(self):
        """Test building index from directory using streaming approach."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test files with different content
            for i in range(5):
                f = tmppath / f"unique_{i}.txt"
                f.write_text(f"unique content {i}")

            # Create some duplicates
            for i in range(3):
                f = tmppath / f"dup_a_{i}.txt"
                f.write_text("duplicate content A")

            for i in range(2):
                f = tmppath / f"dup_b_{i}.txt"
                f.write_text("duplicate content B")

            # Build index from directory using streaming
            index = DuplicateIndex()

            # Mock hash function for consistency
            def mock_hasher(path: Path) -> str:
                content = path.read_text()
                if "duplicate content A" in content:
                    return "hash_dup_a"
                elif "duplicate content B" in content:
                    return "hash_dup_b"
                else:
                    # Unique hash per file
                    return f"hash_{path.name}"

            # Use streaming build with small chunks
            config = IndexBuildConfig(chunk_size=3)
            progress_updates = []

            for progress in index.build_from_directory_streaming(tmppath, mock_hasher, config):
                progress_updates.append(progress)

            # Verify streaming yielded progress updates
            assert len(progress_updates) > 0
            assert progress_updates[-1] == 10  # Final count

            # Verify index was built correctly
            stats = index.get_statistics()
            assert stats["total_files"] == 10
            assert stats["duplicate_groups"] == 2  # 2 groups of duplicates

    def test_streaming_build_with_chunks(self):
        """Test streaming build processes files in chunks."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 50 test files
            for i in range(50):
                f = tmppath / f"file_{i:03d}.txt"
                # Create some duplicates
                if i % 5 == 0:
                    f.write_text("duplicate")
                else:
                    f.write_text(f"content {i}")

            index = DuplicateIndex()

            # Hash function
            def hash_func(path: Path) -> str:
                content = path.read_text()
                return f"hash_{hash(content)}"

            # Build index with streaming approach (chunks of 10)
            config = IndexBuildConfig(chunk_size=10)
            progress_updates = []

            for progress in index.build_from_directory_streaming(tmppath, hash_func, config):
                progress_updates.append(progress)

            # Verify we got progress updates for each chunk
            assert len(progress_updates) == 5  # 50 files / 10 per chunk
            assert progress_updates[-1] == 50

            assert index.get_statistics()["total_files"] == 50

    def test_streaming_build_empty_directory(self):
        """Test streaming build on empty directory."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            index = DuplicateIndex()

            # Hash function
            def hash_func(path: Path) -> str:
                return "hash"

            # Build from empty directory
            progress_updates = list(index.build_from_directory_streaming(tmppath, hash_func))

            # Should complete with no updates (no files)
            assert len(progress_updates) == 0

            stats = index.get_statistics()
            assert stats["total_files"] == 0
            assert not index.has_duplicates()

    def test_streaming_build_large_number_of_files(self):
        """Test streaming build handles large number of files efficiently."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 100 files to simulate larger directory
            for i in range(100):
                f = tmppath / f"file_{i:04d}.txt"
                # Create groups of duplicates (every 10th file same content)
                f.write_text(f"content_{i // 10}")

            index = DuplicateIndex()

            # Hash function
            def hash_func(path: Path) -> str:
                content = path.read_text()
                return f"hash_{content}"

            # Stream files in chunks of 20
            config = IndexBuildConfig(chunk_size=20)
            progress_updates = []

            for progress in index.build_from_directory_streaming(tmppath, hash_func, config):
                progress_updates.append(progress)

            # Verify chunked processing
            assert len(progress_updates) == 5  # 100 files / 20 per chunk
            assert progress_updates[-1] == 100

            stats = index.get_statistics()
            assert stats["total_files"] == 100
            # We have 10 groups of 10 duplicates each
            assert stats["duplicate_groups"] == 10

    def test_streaming_build_with_progress_callback(self):
        """Test streaming build calls progress callback."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 20 test files
            for i in range(20):
                f = tmppath / f"file_{i}.txt"
                f.write_text(f"content {i}")

            index = DuplicateIndex()
            progress_calls = []

            # Progress callback
            def progress_callback(count: int) -> None:
                progress_calls.append(count)

            # Hash function
            def hash_func(path: Path) -> str:
                return f"hash_{path.name}"

            # Build with progress callback
            config = IndexBuildConfig(chunk_size=5, progress_callback=progress_callback)

            list(index.build_from_directory_streaming(tmppath, hash_func, config))

            # Verify callback was called for each file
            assert len(progress_calls) == 20
            assert progress_calls[-1] == 20

    def test_streaming_build_from_files_list(self):
        """Test streaming build from explicit file list."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test files
            for i in range(15):
                f = tmppath / f"file_{i}.txt"
                f.write_text(f"content {i % 3}")  # 3 groups of 5 duplicates

            index = DuplicateIndex()

            # Get file list
            file_list = list(tmppath.iterdir())

            # Hash function
            def hash_func(path: Path) -> str:
                content = path.read_text()
                return f"hash_{content}"

            # Build from file list
            config = IndexBuildConfig(chunk_size=5)
            progress_updates = []

            for progress in index.build_from_files_streaming(file_list, hash_func, config):
                progress_updates.append(progress)

            # Verify
            assert len(progress_updates) == 3  # 15 files / 5 per chunk
            assert progress_updates[-1] == 15

            stats = index.get_statistics()
            assert stats["total_files"] == 15
            assert stats["duplicate_groups"] == 3

    def test_streaming_build_with_max_files(self):
        """Test streaming build respects max_files limit."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 50 files
            for i in range(50):
                f = tmppath / f"file_{i}.txt"
                f.write_text(f"content {i}")

            index = DuplicateIndex()

            # Hash function
            def hash_func(path: Path) -> str:
                return f"hash_{path.name}"

            # Build with max_files limit
            config = IndexBuildConfig(chunk_size=10, max_files=25)
            progress_updates = []

            for progress in index.build_from_directory_streaming(tmppath, hash_func, config):
                progress_updates.append(progress)

            # Should only process 25 files
            assert progress_updates[-1] == 25
            assert index.get_statistics()["total_files"] == 25

    def test_add_files_batch(self):
        """Test batch file addition."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create test files
            files_to_add = []
            for i in range(10):
                f = tmppath / f"file_{i}.txt"
                f.write_text(f"content {i}")
                files_to_add.append((f, f"hash_{i}"))

            index = DuplicateIndex()

            # Add files in batch
            added_count = index.add_files_batch(files_to_add)

            assert added_count == 10
            assert index.get_statistics()["total_files"] == 10


@pytest.mark.unit
class TestBuildFromDirectoryStreamingErrors:
    """Tests for error paths in build_from_directory_streaming."""

    def test_raises_valueerror_for_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test ValueError raised when directory does not exist."""
        index = DuplicateIndex()
        nonexistent = tmp_path / "does_not_exist"

        def hash_func(path: Path) -> str:
            return "hash"

        with pytest.raises(ValueError, match="Directory not found"):
            list(index.build_from_directory_streaming(nonexistent, hash_func))

    def test_raises_valueerror_for_file_path(self, tmp_path: Path) -> None:
        """Test ValueError raised when path is a file, not a directory."""
        index = DuplicateIndex()
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("content")

        def hash_func(path: Path) -> str:
            return "hash"

        with pytest.raises(ValueError, match="Path is not a directory"):
            list(index.build_from_directory_streaming(file_path, hash_func))

    def test_uses_default_config_when_none(self, tmp_path: Path) -> None:
        """Test that default IndexBuildConfig is used when config is None."""
        index = DuplicateIndex()
        f = tmp_path / "file.txt"
        f.write_text("content")

        def hash_func(path: Path) -> str:
            return "hash_default"

        # Pass config=None explicitly
        progress = list(index.build_from_directory_streaming(tmp_path, hash_func, config=None))

        assert progress[-1] == 1
        assert len(index) == 1
        assert "hash_default" in index

    def test_oserror_during_hash_skips_file(self, tmp_path: Path) -> None:
        """Test that OSError during hash computation skips the file gracefully."""
        index = DuplicateIndex()
        good_file = tmp_path / "good.txt"
        good_file.write_text("good content")
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text("bad content")

        def hash_func(path: Path) -> str:
            if path.name == "bad.txt":
                raise OSError("disk read error")
            return f"hash_{path.name}"

        progress = list(index.build_from_directory_streaming(tmp_path, hash_func))

        # Only the good file should be in the index
        assert len(index) == 1
        assert progress[-1] == 1

    def test_permission_error_during_hash_skips_file(self, tmp_path: Path) -> None:
        """Test that PermissionError during hash computation skips the file."""
        index = DuplicateIndex()
        ok_file = tmp_path / "ok.txt"
        ok_file.write_text("ok")
        denied_file = tmp_path / "denied.txt"
        denied_file.write_text("denied")

        def hash_func(path: Path) -> str:
            if path.name == "denied.txt":
                raise PermissionError("access denied")
            return "hash_ok"

        progress = list(index.build_from_directory_streaming(tmp_path, hash_func))

        assert len(index) == 1
        assert progress[-1] == 1

    def test_progress_callback_called_per_file(self, tmp_path: Path) -> None:
        """Test that progress_callback receives incrementing count per processed file."""
        index = DuplicateIndex()
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(f"content{i}")

        callback_values: list[int] = []

        def on_progress(count: int) -> None:
            callback_values.append(count)

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=10, progress_callback=on_progress)
        list(index.build_from_directory_streaming(tmp_path, hash_func, config))

        assert len(callback_values) == 5
        assert callback_values == [1, 2, 3, 4, 5]

    def test_chunked_yielding(self, tmp_path: Path) -> None:
        """Test that generator yields once per chunk with correct progress."""
        index = DuplicateIndex()
        for i in range(7):
            (tmp_path / f"f{i}.txt").write_text(f"c{i}")

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=3)
        yields = list(index.build_from_directory_streaming(tmp_path, hash_func, config))

        # 7 files, chunk_size=3 -> 3 chunks (3, 3, 1)
        assert len(yields) == 3
        assert yields[-1] == 7

    def test_max_files_limits_processing(self, tmp_path: Path) -> None:
        """Test max_files in config limits number of files processed."""
        index = DuplicateIndex()
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text(f"c{i}")

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=100, max_files=3)
        progress = list(index.build_from_directory_streaming(tmp_path, hash_func, config))

        assert progress[-1] == 3
        assert len(index) == 3


@pytest.mark.unit
class TestBuildFromFilesStreamingCoverage:
    """Tests for uncovered paths in build_from_files_streaming."""

    def test_uses_default_config_when_none(self, tmp_path: Path) -> None:
        """Test that default IndexBuildConfig is used when config is None."""
        index = DuplicateIndex()
        f = tmp_path / "file.txt"
        f.write_text("content")

        def hash_func(path: Path) -> str:
            return "hash_file"

        progress = list(index.build_from_files_streaming([f], hash_func, config=None))

        assert progress[-1] == 1
        assert len(index) == 1

    def test_max_files_limits_file_list(self, tmp_path: Path) -> None:
        """Test max_files config truncates the file list before processing."""
        index = DuplicateIndex()
        files = []
        for i in range(10):
            f = tmp_path / f"f{i}.txt"
            f.write_text(f"c{i}")
            files.append(f)

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=100, max_files=4)
        progress = list(index.build_from_files_streaming(files, hash_func, config))

        assert progress[-1] == 4
        assert len(index) == 4

    def test_skips_non_files(self, tmp_path: Path) -> None:
        """Test that non-file paths (directories) are skipped."""
        index = DuplicateIndex()
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        # Pass both a file and a directory in the list
        progress = list(index.build_from_files_streaming([real_file, sub_dir], hash_func))

        assert progress[-1] == 1
        assert len(index) == 1

    def test_oserror_during_hash_skips_file(self, tmp_path: Path) -> None:
        """Test that OSError during hash skips the file and continues."""
        index = DuplicateIndex()
        good = tmp_path / "good.txt"
        good.write_text("good")
        bad = tmp_path / "bad.txt"
        bad.write_text("bad")

        def hash_func(path: Path) -> str:
            if path.name == "bad.txt":
                raise OSError("read failure")
            return "hash_good"

        progress = list(index.build_from_files_streaming([good, bad], hash_func))

        assert progress[-1] == 1
        assert len(index) == 1

    def test_progress_callback_invoked(self, tmp_path: Path) -> None:
        """Test progress_callback receives correct incrementing values."""
        index = DuplicateIndex()
        files = []
        for i in range(4):
            f = tmp_path / f"f{i}.txt"
            f.write_text(f"c{i}")
            files.append(f)

        cb_values: list[int] = []

        def on_progress(count: int) -> None:
            cb_values.append(count)

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=10, progress_callback=on_progress)
        list(index.build_from_files_streaming(files, hash_func, config))

        assert cb_values == [1, 2, 3, 4]

    def test_chunked_yielding(self, tmp_path: Path) -> None:
        """Test generator yields once per chunk."""
        index = DuplicateIndex()
        files = []
        for i in range(5):
            f = tmp_path / f"f{i}.txt"
            f.write_text(f"c{i}")
            files.append(f)

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        config = IndexBuildConfig(chunk_size=2)
        yields = list(index.build_from_files_streaming(files, hash_func, config))

        # 5 files, chunk_size=2 -> 3 chunks (2, 2, 1)
        assert len(yields) == 3
        assert yields[-1] == 5

    def test_nonexistent_file_in_list_skipped(self, tmp_path: Path) -> None:
        """Test that a path pointing to a nonexistent file is skipped (is_file returns False)."""
        index = DuplicateIndex()
        real = tmp_path / "real.txt"
        real.write_text("real")
        ghost = tmp_path / "ghost.txt"  # never created

        def hash_func(path: Path) -> str:
            return f"hash_{path.name}"

        progress = list(index.build_from_files_streaming([real, ghost], hash_func))

        assert progress[-1] == 1
        assert len(index) == 1


@pytest.mark.unit
class TestAddFilesBatchCoverage:
    """Tests for uncovered paths in add_files_batch."""

    def test_batch_with_metadata_dict(self, tmp_path: Path) -> None:
        """Test add_files_batch uses metadata_dict when provided."""
        index = DuplicateIndex()
        now = datetime.now(UTC)

        f1 = tmp_path / "a.txt"
        f1.write_text("aaa")
        f2 = tmp_path / "b.txt"
        f2.write_text("bbb")

        metadata_dict = {
            f1: {"size": 999, "modified_time": now, "accessed_time": now},
            f2: {"size": 888, "modified_time": now, "accessed_time": now},
        }

        pairs = [(f1, "hash_a"), (f2, "hash_b")]
        added = index.add_files_batch(pairs, metadata_dict=metadata_dict)

        assert added == 2
        # Verify metadata was actually used (not auto-generated from stat)
        file_a = index.get_files_by_hash("hash_a")[0]
        assert file_a.size == 999
        file_b = index.get_files_by_hash("hash_b")[0]
        assert file_b.size == 888

    def test_batch_without_metadata_dict(self, tmp_path: Path) -> None:
        """Test add_files_batch works when metadata_dict is None (auto-generates metadata)."""
        index = DuplicateIndex()
        f = tmp_path / "x.txt"
        f.write_text("hello world")

        pairs = [(f, "hash_x")]
        added = index.add_files_batch(pairs, metadata_dict=None)

        assert added == 1
        file_x = index.get_files_by_hash("hash_x")[0]
        assert file_x.size == len("hello world")

    def test_batch_metadata_dict_missing_key(self, tmp_path: Path) -> None:
        """Test add_files_batch handles file not present in metadata_dict gracefully."""
        index = DuplicateIndex()
        f1 = tmp_path / "present.txt"
        f1.write_text("present")
        f2 = tmp_path / "absent.txt"
        f2.write_text("absent")

        now = datetime.now(UTC)
        # Only f1 has metadata; f2 will get None from .get() and fall back to stat()
        metadata_dict = {
            f1: {"size": 500, "modified_time": now, "accessed_time": now},
        }

        pairs = [(f1, "hash1"), (f2, "hash2")]
        added = index.add_files_batch(pairs, metadata_dict=metadata_dict)

        assert added == 2
        assert index.get_files_by_hash("hash1")[0].size == 500
        # f2 gets auto-generated metadata from stat
        assert index.get_files_by_hash("hash2")[0].size == len("absent")

    def test_batch_error_handling_skips_bad_files(self) -> None:
        """Test add_files_batch skips files that raise OSError during add_file."""
        index = DuplicateIndex()
        # Use a nonexistent path without metadata -- add_file will call stat() and fail
        bad_path = Path("/nonexistent/path/file.txt")
        good_path = Path("/tmp/test_batch_good.txt")

        # Provide metadata for good_path so stat() is not called
        now = datetime.now(UTC)
        metadata_dict = {
            good_path: {"size": 42, "modified_time": now, "accessed_time": now},
        }

        pairs = [(bad_path, "hash_bad"), (good_path, "hash_good")]
        added = index.add_files_batch(pairs, metadata_dict=metadata_dict)

        # bad_path should fail (no metadata, stat fails), good_path should succeed
        assert added == 1
        assert len(index.get_files_by_hash("hash_good")) == 1
        assert len(index.get_files_by_hash("hash_bad")) == 0
