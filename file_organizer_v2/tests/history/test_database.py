"""
Tests for database manager.
"""

import pytest
import tempfile
from pathlib import Path
from file_organizer.history.database import DatabaseManager


class TestDatabaseManager:
    """Test suite for DatabaseManager."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        # Clean up WAL and SHM files if they exist
        for suffix in ['-wal', '-shm']:
            wal_file = Path(str(db_path) + suffix)
            if wal_file.exists():
                wal_file.unlink()

    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create database manager instance."""
        db = DatabaseManager(temp_db_path)
        db.initialize()
        yield db
        db.close()

    def test_initialization(self, temp_db_path):
        """Test database initialization."""
        db = DatabaseManager(temp_db_path)
        db.initialize()

        # Check that database file was created
        assert temp_db_path.exists()

        # Check that tables were created
        conn = db.get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert 'operations' in tables
        assert 'transactions' in tables
        assert 'schema_version' in tables

        db.close()

    def test_wal_mode_enabled(self, db_manager):
        """Test that WAL mode is enabled."""
        conn = db_manager.get_connection()
        cursor = conn.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        assert result[0].lower() == 'wal'

    def test_indexes_created(self, db_manager):
        """Test that indexes were created."""
        conn = db_manager.get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = [
            'idx_operations_timestamp',
            'idx_operations_transaction',
            'idx_operations_type',
            'idx_operations_status',
            'idx_transactions_status'
        ]

        for idx in expected_indexes:
            assert idx in indexes

    def test_transaction_context_manager(self, db_manager):
        """Test transaction context manager."""
        with db_manager.transaction() as conn:
            conn.execute("INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
                        ('move', '2024-01-01T00:00:00Z', '/test/path', 'completed'))

        # Verify insert succeeded
        result = db_manager.fetch_one("SELECT COUNT(*) as count FROM operations")
        assert result['count'] == 1

    def test_transaction_rollback_on_error(self, db_manager):
        """Test that transaction rolls back on error."""
        try:
            with db_manager.transaction() as conn:
                conn.execute("INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
                            ('move', '2024-01-01T00:00:00Z', '/test/path', 'completed'))
                # Trigger an error
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify insert was rolled back
        result = db_manager.fetch_one("SELECT COUNT(*) as count FROM operations")
        assert result['count'] == 0

    def test_execute_query(self, db_manager):
        """Test execute_query method."""
        db_manager.execute_query(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            ('move', '2024-01-01T00:00:00Z', '/test/path', 'completed')
        )
        db_manager.get_connection().commit()

        result = db_manager.fetch_one("SELECT * FROM operations")
        assert result is not None
        assert result['operation_type'] == 'move'

    def test_execute_many(self, db_manager):
        """Test batch insert with execute_many."""
        data = [
            ('move', '2024-01-01T00:00:00Z', '/test/path1', 'completed'),
            ('rename', '2024-01-01T00:00:01Z', '/test/path2', 'completed'),
            ('delete', '2024-01-01T00:00:02Z', '/test/path3', 'completed'),
        ]

        db_manager.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            data
        )

        result = db_manager.fetch_one("SELECT COUNT(*) as count FROM operations")
        assert result['count'] == 3

    def test_fetch_all(self, db_manager):
        """Test fetch_all method."""
        # Insert test data
        data = [
            ('move', '2024-01-01T00:00:00Z', '/test/path1', 'completed'),
            ('rename', '2024-01-01T00:00:01Z', '/test/path2', 'completed'),
        ]
        db_manager.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            data
        )

        results = db_manager.fetch_all("SELECT * FROM operations ORDER BY timestamp")
        assert len(results) == 2
        assert results[0]['operation_type'] == 'move'
        assert results[1]['operation_type'] == 'rename'

    def test_get_database_size(self, db_manager):
        """Test get_database_size method."""
        size = db_manager.get_database_size()
        assert size > 0  # Database should have some size after initialization

    def test_get_operation_count(self, db_manager):
        """Test get_operation_count method."""
        # Initially empty
        assert db_manager.get_operation_count() == 0

        # Insert operations
        data = [
            ('move', '2024-01-01T00:00:00Z', '/test/path1', 'completed'),
            ('rename', '2024-01-01T00:00:01Z', '/test/path2', 'completed'),
        ]
        db_manager.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            data
        )

        assert db_manager.get_operation_count() == 2

    def test_vacuum(self, db_manager):
        """Test vacuum operation."""
        # Insert and delete data to create free space
        data = [('move', '2024-01-01T00:00:00Z', f'/test/path{i}', 'completed') for i in range(100)]
        db_manager.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            data
        )

        db_manager.execute_query("DELETE FROM operations")
        db_manager.get_connection().commit()

        # Vacuum should succeed without error
        db_manager.vacuum()

    def test_context_manager(self, temp_db_path):
        """Test database manager as context manager."""
        with DatabaseManager(temp_db_path) as db:
            assert db._connection is not None

        # Connection should be closed after exit
        # Note: We can't easily test this without accessing private attributes

    def test_row_factory(self, db_manager):
        """Test that row factory is set for easy data access."""
        db_manager.execute_query(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) VALUES (?, ?, ?, ?)",
            ('move', '2024-01-01T00:00:00Z', '/test/path', 'completed')
        )
        db_manager.get_connection().commit()

        result = db_manager.fetch_one("SELECT * FROM operations")
        # Should be able to access by column name
        assert result['operation_type'] == 'move'
        assert result['source_path'] == '/test/path'
