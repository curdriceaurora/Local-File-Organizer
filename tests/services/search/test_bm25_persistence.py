"""Unit tests for BM25Persistence."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

pytest.importorskip("rank_bm25")

from rank_bm25 import BM25Okapi

from file_organizer.services.search.bm25_persistence import BM25Persistence

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_cache_path(tmp_path: Path) -> Path:
    """Return a temporary cache file path for testing."""
    return tmp_path / "test_bm25_cache.pkl"


@pytest.fixture
def sample_bm25_index() -> BM25Okapi:
    """Return a simple fitted BM25Okapi index for testing."""
    corpus = [
        ["finance", "budget", "report"],
        ["legal", "contract", "agreement"],
        ["recipe", "baking", "chocolate"],
    ]
    return BM25Okapi(corpus)


@pytest.fixture
def sample_paths(tmp_path: Path) -> list[Path]:
    """Return a list of sample file paths."""
    return [
        tmp_path / "finance.txt",
        tmp_path / "legal.txt",
        tmp_path / "recipe.txt",
    ]


@pytest.fixture
def persistence() -> BM25Persistence:
    """Return a BM25Persistence instance."""
    return BM25Persistence()


# ---------------------------------------------------------------------------
# BM25Persistence Save Tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceSave:
    """Tests for BM25Persistence.save() method."""

    def test_save_creates_file(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Saving an index creates the cache file."""
        assert not temp_cache_path.exists()
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        assert temp_cache_path.exists()

    def test_save_creates_parent_directory(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        tmp_path: Path,
    ) -> None:
        """Save creates parent directories if they don't exist."""
        nested_path = tmp_path / "nested" / "dirs" / "cache.pkl"
        assert not nested_path.parent.exists()
        persistence.save(sample_bm25_index, sample_paths, nested_path)
        assert nested_path.exists()

    def test_save_none_index_logs_warning(
        self,
        persistence: BM25Persistence,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Saving None index logs warning and does not create file."""
        persistence.save(None, sample_paths, temp_cache_path)
        assert not temp_cache_path.exists()

    def test_save_empty_paths_list(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        temp_cache_path: Path,
    ) -> None:
        """Save works with empty paths list."""
        persistence.save(sample_bm25_index, [], temp_cache_path)
        assert temp_cache_path.exists()

    def test_save_overwrites_existing_file(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Saving to existing file overwrites it."""
        # Write initial data
        temp_cache_path.write_text("old content")
        initial_size = temp_cache_path.stat().st_size

        # Save index (should overwrite)
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)

        # File should be overwritten with pickle data
        assert temp_cache_path.stat().st_size != initial_size


# ---------------------------------------------------------------------------
# BM25Persistence Load Tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceLoad:
    """Tests for BM25Persistence.load() method."""

    def test_load_nonexistent_file_returns_none(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Loading from nonexistent file returns (None, [])."""
        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""

    def test_load_saved_index_succeeds(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Load returns the same index and paths that were saved."""
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        loaded_index, loaded_paths, loaded_documents, loaded_fingerprint = persistence.load(
            temp_cache_path
        )

        assert loaded_index is not None
        assert loaded_paths == sample_paths
        assert loaded_documents == []
        assert loaded_fingerprint == ""

    def test_loaded_index_is_functional(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Loaded index can be used for scoring queries."""
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        loaded_index, _, _, _ = persistence.load(temp_cache_path)

        assert loaded_index is not None
        # Test that loaded index works for scoring
        query_tokens = ["finance", "budget"]
        scores = loaded_index.get_scores(query_tokens)
        assert len(scores) == 3
        assert scores[0] > 0  # First doc should match

    def test_load_corrupted_file_raises(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Loading corrupted pickle file raises exception."""
        temp_cache_path.write_text("not a pickle file")

        with pytest.raises(pickle.UnpicklingError):
            persistence.load(temp_cache_path)

    def test_load_invalid_data_structure_returns_none(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Load returns None for invalid data structure."""
        # Save a string instead of dict
        with open(temp_cache_path, "wb") as f:
            pickle.dump("invalid data", f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""

    def test_load_missing_paths_key_returns_index_with_empty_paths(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        temp_cache_path: Path,
    ) -> None:
        """Load returns the bm25 index and defaults paths/documents to empty lists when keys missing."""
        data = {"bm25_index": sample_bm25_index}  # Missing 'paths'
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        # Index is present, paths/documents default to empty lists
        assert bm25 is not None  # Index is present
        assert paths == []  # Default value
        assert documents == []
        assert fingerprint == ""

    def test_load_invalid_paths_type_returns_none(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        temp_cache_path: Path,
    ) -> None:
        """Load returns None if paths is not a list."""
        data = {"bm25_index": sample_bm25_index, "paths": "not a list"}
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""


# ---------------------------------------------------------------------------
# BM25Persistence Delete Tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceDelete:
    """Tests for BM25Persistence.delete() method."""

    def test_delete_existing_file_removes_it(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Delete removes an existing cache file."""
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        assert temp_cache_path.exists()

        persistence.delete(temp_cache_path)
        assert not temp_cache_path.exists()

    def test_delete_nonexistent_file_does_not_raise(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Deleting nonexistent file does not raise exception."""
        assert not temp_cache_path.exists()
        persistence.delete(temp_cache_path)  # Should not raise


# ---------------------------------------------------------------------------
# BM25Persistence Validation Tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceValidation:
    """Tests for BM25Persistence.is_valid() method."""

    def test_is_valid_nonexistent_file_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False for nonexistent file."""
        assert not persistence.is_valid(temp_cache_path)

    def test_is_valid_properly_saved_file_returns_true(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns True for properly saved file."""
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        assert persistence.is_valid(temp_cache_path)

    def test_is_valid_corrupted_file_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False for corrupted file."""
        temp_cache_path.write_text("corrupted data")
        assert not persistence.is_valid(temp_cache_path)

    def test_is_valid_wrong_structure_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False for wrong data structure."""
        # Save a list instead of dict
        with open(temp_cache_path, "wb") as f:
            pickle.dump(["not", "a", "dict"], f)

        assert not persistence.is_valid(temp_cache_path)

    def test_is_valid_missing_keys_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False if required keys are missing."""
        data = {"bm25_index": "something"}  # Missing 'paths'
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        assert not persistence.is_valid(temp_cache_path)

    def test_is_valid_invalid_paths_type_returns_false(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False if paths is not a list."""
        data = {"bm25_index": sample_bm25_index, "paths": "not a list"}
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        assert not persistence.is_valid(temp_cache_path)

    def test_is_valid_empty_file_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False for empty file."""
        temp_cache_path.touch()
        assert not persistence.is_valid(temp_cache_path)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceIntegration:
    """Integration tests for complete save/load/delete workflow."""

    def test_round_trip_preserves_data(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Complete save/load round trip preserves all data."""
        # Save
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)

        # Load
        loaded_index, loaded_paths, loaded_documents, loaded_fingerprint = persistence.load(
            temp_cache_path
        )

        # Verify
        assert loaded_index is not None
        assert loaded_paths == sample_paths
        assert loaded_documents == []
        assert loaded_fingerprint == ""
        assert persistence.is_valid(temp_cache_path)

    def test_multiple_save_load_cycles(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        temp_cache_path: Path,
    ) -> None:
        """Multiple save/load cycles work correctly."""
        paths1 = [temp_cache_path.parent / "file1.txt", temp_cache_path.parent / "file2.txt"]
        paths2 = [
            temp_cache_path.parent / "file3.txt",
            temp_cache_path.parent / "file4.txt",
            temp_cache_path.parent / "file5.txt",
        ]

        # First cycle
        persistence.save(sample_bm25_index, paths1, temp_cache_path)
        _, loaded_paths1, loaded_documents1, loaded_fingerprint1 = persistence.load(temp_cache_path)
        assert loaded_paths1 == paths1
        assert loaded_documents1 == []
        assert loaded_fingerprint1 == ""

        # Second cycle (overwrite)
        persistence.save(sample_bm25_index, paths2, temp_cache_path)
        _, loaded_paths2, loaded_documents2, loaded_fingerprint2 = persistence.load(temp_cache_path)
        assert loaded_paths2 == paths2
        assert loaded_paths2 != paths1
        assert loaded_documents2 == []
        assert loaded_fingerprint2 == ""

    def test_delete_invalidates_cache(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Deleting cache makes subsequent loads return None."""
        # Save and verify
        persistence.save(sample_bm25_index, sample_paths, temp_cache_path)
        assert persistence.is_valid(temp_cache_path)

        # Delete
        persistence.delete(temp_cache_path)

        # Verify deletion
        assert not persistence.is_valid(temp_cache_path)
        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""


# ---------------------------------------------------------------------------
# Additional Coverage Tests — error handling & validation branches
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceSaveErrorHandling:
    """Tests for BM25Persistence.save() error handling (lines 73-75)."""

    def test_save_permission_error_raises_oserror(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        tmp_path: Path,
    ) -> None:
        """Save raises OSError when the cache directory is not writable."""
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        cache_path = read_only_dir / "cache.pkl"

        # Make directory read-only to trigger OSError on file creation
        read_only_dir.chmod(0o444)
        try:
            with pytest.raises(OSError):
                persistence.save(sample_bm25_index, sample_paths, cache_path)
        finally:
            read_only_dir.chmod(0o755)

    def test_save_unpicklable_object_raises_pickling_error(
        self,
        persistence: BM25Persistence,
        sample_paths: list[Path],
        tmp_path: Path,
    ) -> None:
        """Save raises PicklingError when the index cannot be serialized."""

        # A lambda is not picklable
        unpicklable = lambda x: x  # noqa: E731
        cache_path = tmp_path / "cache.pkl"

        with pytest.raises((pickle.PicklingError, AttributeError)):
            persistence.save(unpicklable, sample_paths, cache_path)


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceLoadValidationBranches:
    """Tests for BM25Persistence.load() validation branches (lines 120, 124, 127, 132)."""

    def test_load_documents_not_list_returns_none(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Load returns (None, [], []) when documents is not a list (line 120-124)."""
        data = {
            "bm25_index": "fake_index",
            "paths": [Path("a.txt")],
            "documents": "not a list",
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""

    def test_load_documents_with_non_string_items_returns_none(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Load returns (None, [], []) when documents contains non-str items (line 120-124)."""
        data = {
            "bm25_index": "fake_index",
            "paths": [Path("a.txt")],
            "documents": [123, 456],
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""

    def test_save_and_load_preserves_fingerprint(
        self,
        persistence: BM25Persistence,
        sample_bm25_index: BM25Okapi,
        sample_paths: list[Path],
        temp_cache_path: Path,
    ) -> None:
        """Fingerprint metadata round-trips with the saved cache."""
        persistence.save(
            sample_bm25_index,
            sample_paths,
            temp_cache_path,
            documents=["finance budget", "legal contract", "recipe chocolate"],
            fingerprint="docs-hash-123",
        )

        _, loaded_paths, loaded_documents, fingerprint = persistence.load(temp_cache_path)

        assert loaded_paths == sample_paths
        assert loaded_documents == ["finance budget", "legal contract", "recipe chocolate"]
        assert fingerprint == "docs-hash-123"

    def test_load_documents_count_mismatch_returns_none(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """Load returns (None, [], []) when documents length != paths length (lines 126-132)."""
        data = {
            "bm25_index": "fake_index",
            "paths": [Path("a.txt"), Path("b.txt")],
            "documents": ["only one doc"],
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        bm25, paths, documents, fingerprint = persistence.load(temp_cache_path)
        assert bm25 is None
        assert paths == []
        assert documents == []
        assert fingerprint == ""


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceDeleteErrorPath:
    """Tests for BM25Persistence.delete() error handling (lines 160-162)."""

    def test_delete_permission_error_raises(
        self,
        persistence: BM25Persistence,
        tmp_path: Path,
    ) -> None:
        """Delete raises OSError when file cannot be removed due to permissions."""
        protected_dir = tmp_path / "protected"
        protected_dir.mkdir()
        cache_file = protected_dir / "cache.pkl"
        cache_file.write_bytes(b"data")

        # Make the parent directory read-only so unlink fails
        protected_dir.chmod(0o444)
        try:
            with pytest.raises(OSError):
                persistence.delete(cache_file)
        finally:
            protected_dir.chmod(0o755)


@pytest.mark.ci
@pytest.mark.unit
class TestBM25PersistenceIsValidEdgeCases:
    """Tests for BM25Persistence.is_valid() additional validation (lines 191, 193)."""

    def test_is_valid_documents_not_list_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False when documents field is not a list (line 191)."""
        data = {
            "bm25_index": "fake",
            "paths": [Path("a.txt")],
            "documents": "not a list",
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        assert persistence.is_valid(temp_cache_path) is False

    def test_is_valid_documents_count_mismatch_returns_false(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns False when documents count != paths count (line 193)."""
        data = {
            "bm25_index": "fake",
            "paths": [Path("a.txt"), Path("b.txt")],
            "documents": ["only one"],
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        assert persistence.is_valid(temp_cache_path) is False

    def test_is_valid_documents_empty_with_paths_returns_true(
        self,
        persistence: BM25Persistence,
        temp_cache_path: Path,
    ) -> None:
        """is_valid returns True when documents is empty (no mismatch check needed)."""
        data = {
            "bm25_index": "fake",
            "paths": [temp_cache_path.parent / "a.txt"],
            "documents": [],
        }
        with open(temp_cache_path, "wb") as f:
            pickle.dump(data, f)

        assert persistence.is_valid(temp_cache_path) is True
