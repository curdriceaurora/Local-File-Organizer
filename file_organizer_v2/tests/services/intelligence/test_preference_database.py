"""
Tests for preference database manager.
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from file_organizer.services.intelligence.preference_database import (
    PreferenceDatabaseManager
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_preferences.db"
        yield db_path


@pytest.fixture
def db_manager(temp_db):
    """Create database manager instance."""
    manager = PreferenceDatabaseManager(db_path=temp_db)
    manager.initialize()
    yield manager
    manager.close()


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_initialize_creates_database(self, temp_db):
        """Test that initialization creates database file."""
        manager = PreferenceDatabaseManager(db_path=temp_db)
        manager.initialize()

        assert temp_db.exists()
        manager.close()

    def test_initialize_creates_tables(self, db_manager):
        """Test that all required tables are created."""
        conn = db_manager.get_connection()

        # Check for required tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            'preferences',
            'preference_history',
            'corrections',
            'folder_mappings',
            'naming_patterns',
            'category_overrides',
            'schema_version'
        }

        assert required_tables.issubset(tables)

    def test_initialize_creates_indexes(self, db_manager):
        """Test that indexes are created."""
        conn = db_manager.get_connection()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        # Check for some key indexes
        assert 'idx_preferences_type' in indexes
        assert 'idx_preferences_key' in indexes
        assert 'idx_corrections_type' in indexes

    def test_initialize_sets_schema_version(self, db_manager):
        """Test that schema version is set."""
        conn = db_manager.get_connection()

        cursor = conn.execute("SELECT version FROM schema_version")
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == PreferenceDatabaseManager.SCHEMA_VERSION

    def test_initialize_idempotent(self, db_manager):
        """Test that multiple initializations don't cause errors."""
        # Should not raise any errors
        db_manager.initialize()
        db_manager.initialize()


class TestPreferenceCRUD:
    """Test CRUD operations for preferences."""

    def test_add_preference(self, db_manager):
        """Test adding a new preference."""
        pref_id = db_manager.add_preference(
            preference_type="folder_mapping",
            key="Documents/Work",
            value="/path/to/work",
            confidence=0.8,
            frequency=1,
            source="user_correction"
        )

        assert pref_id is not None
        assert pref_id > 0

    def test_add_preference_with_context(self, db_manager):
        """Test adding preference with context."""
        context = {"file_type": "pdf", "category": "technical"}

        pref_id = db_manager.add_preference(
            preference_type="naming_pattern",
            key="report_*.pdf",
            value="Report_{date}_{name}.pdf",
            context=context
        )

        # Verify ID was returned
        assert pref_id is not None
        assert pref_id > 0

        # Retrieve and verify context
        pref = db_manager.get_preference("naming_pattern", "report_*.pdf")
        assert pref is not None
        assert pref['context'] == context

    def test_add_duplicate_preference_updates(self, db_manager):
        """Test that adding duplicate preference updates existing one."""
        # Add initial preference
        db_manager.add_preference(
            preference_type="folder_mapping",
            key="test_key",
            value="initial_value",
            confidence=0.5
        )

        # Add duplicate (should update)
        db_manager.add_preference(
            preference_type="folder_mapping",
            key="test_key",
            value="updated_value",
            confidence=0.8
        )

        # Verify update
        pref = db_manager.get_preference("folder_mapping", "test_key")
        assert pref['value'] == "updated_value"
        assert pref['confidence'] == 0.8
        assert pref['frequency'] == 2  # Should increment

    def test_get_preference(self, db_manager):
        """Test retrieving a preference."""
        db_manager.add_preference(
            preference_type="category_override",
            key="*.py",
            value="Code/Python",
            confidence=0.9
        )

        pref = db_manager.get_preference("category_override", "*.py")

        assert pref is not None
        assert pref['preference_type'] == "category_override"
        assert pref['key'] == "*.py"
        assert pref['value'] == "Code/Python"
        assert pref['confidence'] == 0.9

    def test_get_nonexistent_preference(self, db_manager):
        """Test retrieving non-existent preference returns None."""
        pref = db_manager.get_preference("folder_mapping", "nonexistent")
        assert pref is None

    def test_get_preferences_by_type(self, db_manager):
        """Test retrieving all preferences of a type."""
        # Add multiple preferences
        db_manager.add_preference("folder_mapping", "key1", "value1", 0.9)
        db_manager.add_preference("folder_mapping", "key2", "value2", 0.7)
        db_manager.add_preference("folder_mapping", "key3", "value3", 0.8)
        db_manager.add_preference("naming_pattern", "key4", "value4", 0.6)

        # Get folder_mapping preferences
        prefs = db_manager.get_preferences_by_type("folder_mapping")

        assert len(prefs) == 3
        # Should be ordered by confidence DESC
        assert prefs[0]['confidence'] == 0.9
        assert prefs[1]['confidence'] == 0.8
        assert prefs[2]['confidence'] == 0.7

    def test_update_preference_confidence(self, db_manager):
        """Test updating preference confidence."""
        pref_id = db_manager.add_preference(
            "folder_mapping",
            "test_key",
            "test_value",
            confidence=0.5
        )

        db_manager.update_preference_confidence(pref_id, 0.9)

        pref = db_manager.get_preference("folder_mapping", "test_key")
        assert pref['confidence'] == 0.9

    def test_increment_preference_usage(self, db_manager):
        """Test incrementing preference usage frequency."""
        pref_id = db_manager.add_preference(
            "folder_mapping",
            "test_key",
            "test_value",
            frequency=1
        )

        db_manager.increment_preference_usage(pref_id)
        db_manager.increment_preference_usage(pref_id)

        pref = db_manager.get_preference("folder_mapping", "test_key")
        assert pref['frequency'] == 3
        assert pref['last_used_at'] is not None

    def test_delete_preference(self, db_manager):
        """Test deleting a preference."""
        pref_id = db_manager.add_preference(
            "folder_mapping",
            "test_key",
            "test_value"
        )

        db_manager.delete_preference(pref_id)

        pref = db_manager.get_preference("folder_mapping", "test_key")
        assert pref is None


class TestCorrectionTracking:
    """Test correction tracking functionality."""

    def test_add_correction(self, db_manager):
        """Test adding a correction."""
        corr_id = db_manager.add_correction(
            correction_type="file_move",
            source_path="/path/to/source.txt",
            destination_path="/path/to/dest.txt",
            confidence_before=0.5,
            confidence_after=0.8
        )

        assert corr_id is not None
        assert corr_id > 0

    def test_add_correction_with_metadata(self, db_manager):
        """Test adding correction with metadata."""
        metadata = {
            "file_size": 1024,
            "file_type": "document",
            "reason": "user_moved"
        }

        corr_id = db_manager.add_correction(
            correction_type="file_rename",
            source_path="/old_name.txt",
            destination_path="/new_name.txt",
            metadata=metadata
        )

        # Verify ID was returned
        assert corr_id is not None
        assert corr_id > 0

        corrections = db_manager.get_corrections(limit=1)
        assert len(corrections) == 1
        assert corrections[0]['metadata'] == metadata

    def test_add_category_correction(self, db_manager):
        """Test adding category change correction."""
        corr_id = db_manager.add_correction(
            correction_type="category_change",
            source_path="/path/to/file.txt",
            category_old="Documents/General",
            category_new="Documents/Work",
            confidence_before=0.6,
            confidence_after=0.9
        )

        corrections = db_manager.get_corrections(
            correction_type="category_change",
            limit=10
        )

        assert len(corrections) == 1
        assert corrections[0]['category_old'] == "Documents/General"
        assert corrections[0]['category_new'] == "Documents/Work"

    def test_get_corrections(self, db_manager):
        """Test retrieving corrections."""
        # Add multiple corrections
        db_manager.add_correction("file_move", "/src1.txt", "/dst1.txt")
        db_manager.add_correction("file_move", "/src2.txt", "/dst2.txt")
        db_manager.add_correction("file_rename", "/old.txt", "/new.txt")

        # Get all corrections
        all_corrections = db_manager.get_corrections(limit=10)
        assert len(all_corrections) == 3

        # Get specific type
        move_corrections = db_manager.get_corrections(
            correction_type="file_move",
            limit=10
        )
        assert len(move_corrections) == 2

    def test_get_corrections_limit(self, db_manager):
        """Test correction retrieval limit."""
        # Add many corrections
        for i in range(20):
            db_manager.add_correction("file_move", f"/src{i}.txt", f"/dst{i}.txt")

        # Get with limit
        corrections = db_manager.get_corrections(limit=5)
        assert len(corrections) == 5

    def test_corrections_ordered_by_timestamp(self, db_manager):
        """Test that corrections are returned in chronological order."""
        import time

        # Add corrections with delays
        db_manager.add_correction("file_move", "/src1.txt", "/dst1.txt")
        time.sleep(0.01)
        db_manager.add_correction("file_move", "/src2.txt", "/dst2.txt")
        time.sleep(0.01)
        db_manager.add_correction("file_move", "/src3.txt", "/dst3.txt")

        corrections = db_manager.get_corrections(limit=10)

        # Should be in DESC order (most recent first)
        assert corrections[0]['source_path'] == "/src3.txt"
        assert corrections[1]['source_path'] == "/src2.txt"
        assert corrections[2]['source_path'] == "/src1.txt"


class TestStatistics:
    """Test statistics functionality."""

    def test_get_preference_stats_empty(self, db_manager):
        """Test stats for empty database."""
        stats = db_manager.get_preference_stats()

        assert stats['total_preferences'] == 0
        assert stats['average_confidence'] == 0.0
        assert stats['total_usage_count'] == 0
        assert len(stats['by_type']) == 0

    def test_get_preference_stats(self, db_manager):
        """Test preference statistics."""
        # Add preferences
        db_manager.add_preference("folder_mapping", "key1", "val1", 0.8, 5)
        db_manager.add_preference("folder_mapping", "key2", "val2", 0.6, 3)
        db_manager.add_preference("naming_pattern", "key3", "val3", 0.9, 2)

        stats = db_manager.get_preference_stats()

        assert stats['total_preferences'] == 3
        assert stats['total_usage_count'] == 10  # 5 + 3 + 2
        assert 'folder_mapping' in stats['by_type']
        assert 'naming_pattern' in stats['by_type']
        assert stats['by_type']['folder_mapping']['count'] == 2
        assert stats['by_type']['naming_pattern']['count'] == 1


class TestConcurrency:
    """Test thread-safety of database operations."""

    def test_concurrent_adds(self, db_manager):
        """Test concurrent preference additions."""
        import threading

        def add_prefs():
            for i in range(10):
                db_manager.add_preference(
                    "folder_mapping",
                    f"key_{threading.get_ident()}_{i}",
                    f"value_{i}",
                    0.5
                )

        # Create multiple threads
        threads = [threading.Thread(target=add_prefs) for _ in range(3)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify all preferences were added
        prefs = db_manager.get_preferences_by_type("folder_mapping")
        assert len(prefs) == 30  # 3 threads * 10 prefs each


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, temp_db):
        """Test database as context manager."""
        with PreferenceDatabaseManager(db_path=temp_db) as manager:
            manager.add_preference("folder_mapping", "key1", "value1")
            pref = manager.get_preference("folder_mapping", "key1")
            assert pref is not None

        # Database should be closed after context
        # Open again to verify data persisted
        with PreferenceDatabaseManager(db_path=temp_db) as manager:
            pref = manager.get_preference("folder_mapping", "key1")
            assert pref is not None
            assert pref['value'] == "value1"
