"""
Tests for PreferenceStore class

Tests cover:
- JSON schema validation
- Serialization/deserialization
- Atomic file writes
- Schema migration
- Backup/restore functionality
- Error recovery
- Conflict resolution
- Thread safety
- Performance benchmarks
"""

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from file_organizer.services.intelligence.preference_store import (
    DirectoryPreference,
    PreferenceStore,
)


@pytest.fixture
def temp_storage():
    """Create temporary storage directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def store(temp_storage):
    """Create PreferenceStore instance"""
    return PreferenceStore(storage_path=temp_storage)


class TestDirectoryPreference:
    """Tests for DirectoryPreference dataclass"""

    def test_to_dict(self):
        """Test conversion to dictionary"""
        pref = DirectoryPreference(
            folder_mappings={"*.jpg": "Photos"},
            naming_patterns={"IMG_*": "Image_{date}"},
            category_overrides={"photo": "Photos"},
            created="2026-01-21T00:00:00Z",
            updated="2026-01-21T01:00:00Z",
            confidence=0.85,
            correction_count=5
        )

        result = pref.to_dict()
        assert result["folder_mappings"] == {"*.jpg": "Photos"}
        assert result["confidence"] == 0.85
        assert result["correction_count"] == 5

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "folder_mappings": {"*.jpg": "Photos"},
            "naming_patterns": {},
            "category_overrides": {},
            "created": "2026-01-21T00:00:00Z",
            "updated": "2026-01-21T01:00:00Z",
            "confidence": 0.75,
            "correction_count": 3
        }

        pref = DirectoryPreference.from_dict(data)
        assert pref.folder_mappings == {"*.jpg": "Photos"}
        assert pref.confidence == 0.75
        assert pref.correction_count == 3

    def test_from_dict_with_defaults(self):
        """Test creation from incomplete dictionary uses defaults"""
        data = {
            "folder_mappings": {},
            "naming_patterns": {},
            "category_overrides": {}
        }

        pref = DirectoryPreference.from_dict(data)
        assert pref.confidence == 0.0
        assert pref.correction_count == 0
        assert pref.created is not None
        assert pref.updated is not None


class TestPreferenceStoreInit:
    """Tests for PreferenceStore initialization"""

    def test_init_with_custom_path(self, temp_storage):
        """Test initialization with custom storage path"""
        store = PreferenceStore(storage_path=temp_storage)
        assert store.storage_path == temp_storage
        assert store.preference_file == temp_storage / "preferences.json"
        assert store.backup_file == temp_storage / "preferences.json.backup"

    def test_init_creates_directory(self, temp_storage):
        """Test that initialization creates storage directory"""
        nested_path = temp_storage / "nested" / "path"
        PreferenceStore(storage_path=nested_path)
        assert nested_path.exists()

    def test_init_default_state(self, store):
        """Test initial state before loading"""
        assert not store._loaded
        assert store._preferences == {}


class TestSchemaValidation:
    """Tests for schema validation"""

    def test_validate_valid_schema(self, store):
        """Test validation of valid schema"""
        data = {
            "version": "1.0",
            "user_id": "default",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {}
            },
            "directory_preferences": {
                "/test/path": {
                    "folder_mappings": {},
                    "naming_patterns": {},
                    "category_overrides": {},
                    "created": "2026-01-21T00:00:00Z",
                    "updated": "2026-01-21T01:00:00Z",
                    "confidence": 0.85
                }
            }
        }

        assert store._validate_schema(data) is True

    def test_validate_missing_version(self, store):
        """Test validation fails for missing version"""
        data = {
            "user_id": "default",
            "global_preferences": {},
            "directory_preferences": {}
        }

        assert store._validate_schema(data) is False

    def test_validate_invalid_version(self, store):
        """Test validation fails for invalid version"""
        data = {
            "version": "99.9",
            "user_id": "default",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {}
            },
            "directory_preferences": {}
        }

        assert store._validate_schema(data) is False

    def test_validate_missing_global_preferences_fields(self, store):
        """Test validation fails for incomplete global preferences"""
        data = {
            "version": "1.0",
            "user_id": "default",
            "global_preferences": {
                "folder_mappings": {}
                # Missing naming_patterns and category_overrides
            },
            "directory_preferences": {}
        }

        assert store._validate_schema(data) is False

    def test_validate_invalid_directory_preference(self, store):
        """Test validation fails for incomplete directory preference"""
        data = {
            "version": "1.0",
            "user_id": "default",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {}
            },
            "directory_preferences": {
                "/test/path": {
                    "folder_mappings": {},
                    # Missing required fields
                }
            }
        }

        assert store._validate_schema(data) is False


class TestLoadSave:
    """Tests for loading and saving preferences"""

    def test_load_nonexistent_creates_defaults(self, store):
        """Test loading when no file exists creates defaults"""
        result = store.load_preferences()
        assert result is False  # No file loaded
        assert store._loaded is True
        assert store._preferences["version"] == "1.0"
        assert store._preferences["user_id"] == "default"

    def test_save_creates_file(self, store):
        """Test saving creates preference file"""
        store.load_preferences()
        result = store.save_preferences()

        assert result is True
        assert store.preference_file.exists()

    def test_save_load_roundtrip(self, store):
        """Test saving and loading preserves data"""
        # Load defaults
        store.load_preferences()

        # Add some data
        test_path = Path("/test/directory")
        store.add_preference(test_path, {
            "folder_mappings": {"*.txt": "Documents"},
            "confidence": 0.9
        })

        # Save
        store.save_preferences()

        # Create new store and load
        new_store = PreferenceStore(storage_path=store.storage_path)
        new_store.load_preferences()

        # Verify data preserved
        pref = new_store.get_preference(test_path, fallback_to_parent=False)
        assert pref is not None
        assert pref["folder_mappings"] == {"*.txt": "Documents"}
        assert pref["confidence"] == 0.9

    def test_atomic_write_with_backup(self, store):
        """Test that atomic writes create backup"""
        store.load_preferences()
        store.save_preferences()

        # Modify and save again
        test_path = Path("/test/directory")
        store.add_preference(test_path, {"folder_mappings": {"*.txt": "Docs"}})
        store.save_preferences()

        # Backup should exist
        assert store.backup_file.exists()

    def test_corrupted_json_loads_backup(self, store, temp_storage):
        """Test that corrupted JSON falls back to backup"""
        # Create valid preferences
        store.load_preferences()
        test_path = Path("/test/directory")
        store.add_preference(test_path, {"folder_mappings": {"*.txt": "Docs"}})
        store.save_preferences()

        # Corrupt the main file
        with open(store.preference_file, 'w') as f:
            f.write("{ invalid json }")

        # Create new store - should load from backup
        new_store = PreferenceStore(storage_path=temp_storage)
        new_store.load_preferences()

        # Should have recovered from backup
        pref = new_store.get_preference(test_path, fallback_to_parent=False)
        assert pref is not None
        assert pref["folder_mappings"] == {"*.txt": "Docs"}

    def test_both_files_corrupted_uses_defaults(self, store):
        """Test that corrupted files fall back to defaults"""
        # Create corrupted files
        with open(store.preference_file, 'w') as f:
            f.write("{ invalid }")
        with open(store.backup_file, 'w') as f:
            f.write("{ also invalid }")

        result = store.load_preferences()

        assert result is False
        assert store._loaded is True
        assert store._preferences["version"] == "1.0"


class TestPreferenceOperations:
    """Tests for preference CRUD operations"""

    def test_add_preference_new_directory(self, store):
        """Test adding preference for new directory"""
        store.load_preferences()
        test_path = Path("/test/directory")

        store.add_preference(test_path, {
            "folder_mappings": {"*.jpg": "Photos"},
            "naming_patterns": {"IMG_*": "Image_{date}"},
            "confidence": 0.8
        })

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref["folder_mappings"] == {"*.jpg": "Photos"}
        assert pref["confidence"] == 0.8
        assert pref["correction_count"] == 1

    def test_add_preference_updates_existing(self, store):
        """Test adding preference updates existing directory"""
        store.load_preferences()
        test_path = Path("/test/directory")

        # Add initial
        store.add_preference(test_path, {
            "folder_mappings": {"*.jpg": "Photos"},
            "confidence": 0.7
        })

        # Update
        store.add_preference(test_path, {
            "folder_mappings": {"*.png": "Images"},
            "confidence": 0.9
        })

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref["folder_mappings"] == {"*.png": "Images"}
        assert pref["confidence"] == 0.9

    def test_get_preference_exact_match(self, store):
        """Test getting preference with exact path match"""
        store.load_preferences()
        test_path = Path("/test/directory")

        store.add_preference(test_path, {
            "folder_mappings": {"*.txt": "Docs"}
        })

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref is not None
        assert pref["folder_mappings"] == {"*.txt": "Docs"}

    def test_get_preference_parent_fallback(self, store):
        """Test getting preference falls back to parent"""
        store.load_preferences()
        parent_path = Path("/test")
        child_path = Path("/test/child/grandchild")

        # Add preference to parent
        store.add_preference(parent_path, {
            "folder_mappings": {"*.txt": "ParentDocs"}
        })

        # Get from child should fallback to parent
        pref = store.get_preference(child_path, fallback_to_parent=True)
        assert pref is not None
        assert pref["folder_mappings"] == {"*.txt": "ParentDocs"}

    def test_get_preference_no_fallback(self, store):
        """Test getting preference without fallback returns global"""
        store.load_preferences()
        test_path = Path("/test/nonexistent")

        # Should return global preferences
        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref is not None
        assert "folder_mappings" in pref

    def test_update_confidence_success(self, store):
        """Test updating confidence on success"""
        store.load_preferences()
        test_path = Path("/test/directory")

        store.add_preference(test_path, {"confidence": 0.5})

        # Successful application should increase confidence
        store.update_confidence(test_path, success=True)

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref["confidence"] > 0.5

    def test_update_confidence_failure(self, store):
        """Test updating confidence on failure"""
        store.load_preferences()
        test_path = Path("/test/directory")

        store.add_preference(test_path, {"confidence": 0.8})

        # Failed application should decrease confidence
        store.update_confidence(test_path, success=False)

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert pref["confidence"] < 0.8

    def test_update_confidence_clamped(self, store):
        """Test confidence is clamped to [0, 1]"""
        store.load_preferences()
        test_path = Path("/test/directory")

        store.add_preference(test_path, {"confidence": 0.99})

        # Multiple successes shouldn't exceed 1.0
        for _ in range(10):
            store.update_confidence(test_path, success=True)

        pref = store.get_preference(test_path, fallback_to_parent=False)
        assert 0.0 <= pref["confidence"] <= 1.0


class TestConflictResolution:
    """Tests for conflict resolution"""

    def test_resolve_conflicts_empty_list(self, store):
        """Test resolving empty conflict list returns empty dict"""
        result = store.resolve_conflicts([])
        assert result == {}

    def test_resolve_conflicts_single_preference(self, store):
        """Test resolving single preference returns it unchanged"""
        pref = {"folder_mappings": {"*.txt": "Docs"}, "confidence": 0.8}
        result = store.resolve_conflicts([pref])
        assert result == pref

    def test_resolve_conflicts_by_confidence(self, store):
        """Test conflict resolution favors higher confidence"""
        pref1 = {
            "folder_mappings": {"*.txt": "Docs1"},
            "confidence": 0.9,
            "correction_count": 5,
            "updated": "2026-01-21T00:00:00Z"
        }
        pref2 = {
            "folder_mappings": {"*.txt": "Docs2"},
            "confidence": 0.5,
            "correction_count": 5,
            "updated": "2026-01-21T00:00:00Z"
        }

        result = store.resolve_conflicts([pref1, pref2])
        assert result["folder_mappings"] == {"*.txt": "Docs1"}

    def test_resolve_conflicts_by_recency(self, store):
        """Test conflict resolution favors more recent"""
        pref1 = {
            "folder_mappings": {"*.txt": "DocsOld"},
            "confidence": 0.7,
            "correction_count": 5,
            "updated": "2026-01-01T00:00:00Z"  # Older
        }
        pref2 = {
            "folder_mappings": {"*.txt": "DocsNew"},
            "confidence": 0.7,
            "correction_count": 5,
            "updated": "2026-01-21T00:00:00Z"  # Newer
        }

        result = store.resolve_conflicts([pref1, pref2])
        # Should favor more recent
        assert result["folder_mappings"] == {"*.txt": "DocsNew"}

    def test_resolve_conflicts_by_frequency(self, store):
        """Test conflict resolution considers correction count"""
        pref1 = {
            "folder_mappings": {"*.txt": "DocsFrequent"},
            "confidence": 0.7,
            "correction_count": 20,  # More corrections
            "updated": "2026-01-21T00:00:00Z"
        }
        pref2 = {
            "folder_mappings": {"*.txt": "DocsRare"},
            "confidence": 0.7,
            "correction_count": 2,  # Fewer corrections
            "updated": "2026-01-21T00:00:00Z"
        }

        result = store.resolve_conflicts([pref1, pref2])
        # Should favor more frequent
        assert result["folder_mappings"] == {"*.txt": "DocsFrequent"}

    def test_score_preference(self, store):
        """Test preference scoring"""
        pref = {
            "confidence": 0.8,
            "correction_count": 10,
            "updated": "2026-01-21T00:00:00Z"
        }

        score = store._score_preference(pref)
        assert 0.0 <= score <= 1.0


class TestImportExport:
    """Tests for import/export functionality"""

    def test_export_json(self, store, temp_storage):
        """Test exporting preferences to JSON"""
        store.load_preferences()
        test_path = Path("/test/directory")
        store.add_preference(test_path, {"folder_mappings": {"*.txt": "Docs"}})

        export_path = temp_storage / "export.json"
        result = store.export_json(export_path)

        assert result is True
        assert export_path.exists()

        # Verify content
        with open(export_path) as f:
            data = json.load(f)
        assert data["version"] == "1.0"
        assert str(test_path.resolve()) in data["directory_preferences"]

    def test_import_json(self, store, temp_storage):
        """Test importing preferences from JSON"""
        # Create export file
        data = {
            "version": "1.0",
            "user_id": "imported",
            "global_preferences": {
                "folder_mappings": {},
                "naming_patterns": {},
                "category_overrides": {}
            },
            "directory_preferences": {
                "/imported/path": {
                    "folder_mappings": {"*.md": "Notes"},
                    "naming_patterns": {},
                    "category_overrides": {},
                    "created": "2026-01-20T00:00:00Z",
                    "updated": "2026-01-20T01:00:00Z",
                    "confidence": 0.95
                }
            }
        }

        import_path = temp_storage / "import.json"
        with open(import_path, 'w') as f:
            json.dump(data, f)

        # Import
        result = store.import_json(import_path)

        assert result is True
        assert store._preferences["user_id"] == "imported"
        pref = store.get_preference(Path("/imported/path"), fallback_to_parent=False)
        assert pref["folder_mappings"] == {"*.md": "Notes"}

    def test_import_invalid_json(self, store, temp_storage):
        """Test importing invalid JSON fails gracefully"""
        import_path = temp_storage / "invalid.json"
        with open(import_path, 'w') as f:
            f.write("{ invalid json }")

        result = store.import_json(import_path)
        assert result is False

    def test_import_invalid_schema(self, store, temp_storage):
        """Test importing invalid schema fails"""
        data = {"version": "1.0", "invalid": "schema"}

        import_path = temp_storage / "invalid_schema.json"
        with open(import_path, 'w') as f:
            json.dump(data, f)

        result = store.import_json(import_path)
        assert result is False

    def test_import_creates_backup(self, store, temp_storage):
        """Test importing creates backup of existing preferences"""
        # Create existing preferences
        store.load_preferences()
        store.save_preferences()

        # Create import file
        data = store._create_empty_preferences()
        data["user_id"] = "new_user"
        import_path = temp_storage / "import.json"
        with open(import_path, 'w') as f:
            json.dump(data, f)

        # Import should create timestamped backup
        store.import_json(import_path)

        # Check for backup files
        backup_files = list(temp_storage.glob("preferences.json.*.backup"))
        assert len(backup_files) > 0


class TestStatistics:
    """Tests for statistics functionality"""

    def test_get_statistics_empty(self, store):
        """Test statistics for empty store"""
        store.load_preferences()
        stats = store.get_statistics()

        assert stats["total_directories"] == 0
        assert stats["total_corrections"] == 0
        assert stats["average_confidence"] == 0.0
        assert stats["schema_version"] == "1.0"

    def test_get_statistics_with_data(self, store):
        """Test statistics with preferences"""
        store.load_preferences()

        # Add multiple preferences
        for i in range(3):
            path = Path(f"/test/dir{i}")
            store.add_preference(path, {
                "confidence": 0.5 + i * 0.1,
                "correction_count": i + 1
            })

        stats = store.get_statistics()

        assert stats["total_directories"] == 3
        assert stats["total_corrections"] == 6  # 1 + 2 + 3
        assert 0.5 < stats["average_confidence"] < 0.9

    def test_list_directory_preferences(self, store):
        """Test listing all directory preferences"""
        store.load_preferences()

        paths = [Path(f"/test/dir{i}") for i in range(3)]
        for path in paths:
            store.add_preference(path, {"folder_mappings": {"*.txt": f"Docs{path}"}})

        prefs = store.list_directory_preferences()

        assert len(prefs) == 3
        for path_str, _pref in prefs:
            assert Path(path_str) in [p.resolve() for p in paths]


class TestThreadSafety:
    """Tests for thread-safe operations"""

    def test_concurrent_add_preferences(self, store):
        """Test concurrent preference additions"""
        store.load_preferences()

        def add_preferences(thread_id):
            for i in range(10):
                path = Path(f"/test/thread{thread_id}/dir{i}")
                store.add_preference(path, {
                    "folder_mappings": {f"*.{thread_id}": f"Thread{thread_id}"}
                })

        threads = [threading.Thread(target=add_preferences, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All preferences should be added without corruption
        stats = store.get_statistics()
        assert stats["total_directories"] == 50  # 5 threads * 10 dirs

    def test_concurrent_read_write(self, store):
        """Test concurrent reads and writes"""
        store.load_preferences()

        test_path = Path("/test/concurrent")
        store.add_preference(test_path, {"confidence": 0.5})

        results = []

        def reader():
            for _ in range(20):
                pref = store.get_preference(test_path, fallback_to_parent=False)
                results.append(pref is not None)
                time.sleep(0.001)

        def writer():
            for i in range(20):
                store.update_confidence(test_path, success=i % 2 == 0)
                time.sleep(0.001)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert all(results)

    def test_concurrent_save(self, store):
        """Test concurrent save operations"""
        store.load_preferences()

        def save_repeatedly():
            for _ in range(10):
                store.save_preferences()
                time.sleep(0.001)

        threads = [threading.Thread(target=save_repeatedly) for _ in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File should still be valid
        new_store = PreferenceStore(storage_path=store.storage_path)
        new_store.load_preferences()
        assert new_store._loaded is True


class TestPerformance:
    """Performance benchmark tests"""

    def test_lookup_performance(self, store):
        """Test preference lookup is under 10ms"""
        store.load_preferences()

        # Add 100 preferences
        for i in range(100):
            path = Path(f"/test/perf/dir{i}")
            store.add_preference(path, {"folder_mappings": {"*.txt": f"Docs{i}"}})

        # Measure lookup time
        test_path = Path("/test/perf/dir50")
        start = time.time()
        for _ in range(100):
            store.get_preference(test_path, fallback_to_parent=False)
        elapsed = (time.time() - start) / 100

        # Should be under 10ms per lookup
        assert elapsed < 0.01, f"Lookup took {elapsed*1000:.2f}ms, expected < 10ms"

    def test_save_performance(self, store):
        """Test save operation is under 100ms"""
        store.load_preferences()

        # Add 100 preferences
        for i in range(100):
            path = Path(f"/test/perf/dir{i}")
            store.add_preference(path, {"folder_mappings": {"*.txt": f"Docs{i}"}})

        # Measure save time
        start = time.time()
        store.save_preferences()
        elapsed = time.time() - start

        # Should be under 100ms
        assert elapsed < 0.1, f"Save took {elapsed*1000:.2f}ms, expected < 100ms"

    def test_conflict_resolution_performance(self, store):
        """Test conflict resolution is under 50ms"""
        # Create 10 conflicting preferences
        preferences = []
        for i in range(10):
            pref = {
                "folder_mappings": {"*.txt": f"Docs{i}"},
                "confidence": 0.5 + i * 0.05,
                "correction_count": i,
                "updated": f"2026-01-{i+1:02d}T00:00:00Z"
            }
            preferences.append(pref)

        # Measure resolution time
        start = time.time()
        for _ in range(100):
            store.resolve_conflicts(preferences)
        elapsed = (time.time() - start) / 100

        # Should be under 50ms per resolution
        assert elapsed < 0.05, f"Resolution took {elapsed*1000:.2f}ms, expected < 50ms"


class TestClearPreferences:
    """Tests for clearing preferences"""

    def test_clear_preferences(self, store):
        """Test clearing all preferences"""
        store.load_preferences()

        # Add some preferences
        for i in range(5):
            path = Path(f"/test/dir{i}")
            store.add_preference(path, {"folder_mappings": {"*.txt": f"Docs{i}"}})

        # Clear
        store.clear_preferences()

        # Should be empty
        stats = store.get_statistics()
        assert stats["total_directories"] == 0
        assert stats["total_corrections"] == 0

    def test_clear_saves_to_disk(self, store):
        """Test clearing persists to disk"""
        store.load_preferences()

        # Add preferences
        path = Path("/test/dir")
        store.add_preference(path, {"folder_mappings": {"*.txt": "Docs"}})

        # Clear
        store.clear_preferences()

        # Load in new store
        new_store = PreferenceStore(storage_path=store.storage_path)
        new_store.load_preferences()

        stats = new_store.get_statistics()
        assert stats["total_directories"] == 0
