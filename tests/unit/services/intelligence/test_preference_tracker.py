import pytest
from datetime import datetime, UTC
from pathlib import Path

from file_organizer.services.intelligence.preference_tracker import (
    PreferenceTracker,
    PreferenceType,
    CorrectionType,
    PreferenceMetadata,
    Preference,
    Correction,
    create_tracker,
    track_file_move,
    track_file_rename,
    track_category_change,
)

@pytest.fixture
def tracker():
    return PreferenceTracker()

@pytest.fixture
def mock_paths():
    return {
        "src_txt": Path("/docs/test.txt"),
        "dst_txt": Path("/docs/text/test.txt"),
        "src_img": Path("/images/pic.png"),
        "dst_img": Path("/images/vacation/pic.png"),
    }

class TestPreferenceMetadata:
    def test_to_dict_and_from_dict(self):
        now = datetime.now(UTC)
        metadata = PreferenceMetadata(
            created=now,
            updated=now,
            confidence=0.8,
            frequency=5,
            last_used=now,
            source="test"
        )
        
        data = metadata.to_dict()
        assert data["confidence"] == 0.8
        assert data["frequency"] == 5
        assert data["source"] == "test"
        
        restored = PreferenceMetadata.from_dict(data)
        assert restored.confidence == 0.8
        assert restored.frequency == 5
        assert restored.source == "test"

class TestPreference:
    def test_to_dict_and_from_dict(self):
        now = datetime.now(UTC)
        metadata = PreferenceMetadata(created=now, updated=now)
        pref = Preference(
            preference_type=PreferenceType.FOLDER_MAPPING,
            key="test_key",
            value="/test/path",
            metadata=metadata,
            context={"test": "data"}
        )
        
        data = pref.to_dict()
        assert data["preference_type"] == PreferenceType.FOLDER_MAPPING.value
        assert data["key"] == "test_key"
        assert data["value"] == "/test/path"
        assert data["context"] == {"test": "data"}
        
        restored = Preference.from_dict(data)
        assert restored.preference_type == PreferenceType.FOLDER_MAPPING
        assert restored.key == "test_key"
        assert restored.value == "/test/path"

class TestCorrection:
    def test_get_pattern_key(self, mock_paths):
        now = datetime.now(UTC)
        correction = Correction(
            correction_type=CorrectionType.FILE_MOVE,
            source=mock_paths["src_txt"],
            destination=mock_paths["dst_txt"],
            timestamp=now
        )
        key = correction.get_pattern_key()
        assert key == "file_move|.txt|text"
        
    def test_get_pattern_key_no_extension(self):
        now = datetime.now(UTC)
        correction = Correction(
            correction_type=CorrectionType.FILE_MOVE,
            source=Path("/test/file"),
            destination=Path("/test/dir/file"),
            timestamp=now
        )
        key = correction.get_pattern_key()
        assert key == "file_move|no_ext|dir"
        
class TestPreferenceTracker:
    def test_init(self, tracker):
        stats = tracker.get_statistics()
        assert stats["total_corrections"] == 0
        assert stats["total_preferences"] == 0
        assert len(tracker.get_all_preferences()) == 0

    def test_track_file_move(self, tracker, mock_paths):
        tracker.track_correction(
            mock_paths["src_txt"],
            mock_paths["dst_txt"],
            CorrectionType.FILE_MOVE
        )
        
        prefs = tracker.get_all_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(prefs) == 1
        assert prefs[0].value == str(mock_paths["dst_txt"].parent)
        assert prefs[0].metadata.frequency == 1
        
        stats = tracker.get_statistics()
        assert stats["total_corrections"] == 1
        assert stats["total_preferences"] == 1

    def test_track_file_rename(self, tracker, mock_paths):
        tracker.track_correction(
            mock_paths["src_txt"],
            Path("/docs/renamed.txt"),
            CorrectionType.FILE_RENAME
        )
        
        prefs = tracker.get_all_preferences(PreferenceType.NAMING_PATTERN)
        assert len(prefs) == 1
        assert prefs[0].value == "renamed.txt"

    def test_track_category_change(self, tracker, mock_paths):
        tracker.track_correction(
            mock_paths["src_txt"],
            mock_paths["src_txt"],
            CorrectionType.CATEGORY_CHANGE,
            context={"new_category": "Documents"}
        )
        
        prefs = tracker.get_all_preferences(PreferenceType.CATEGORY_OVERRIDE)
        assert len(prefs) == 1
        assert prefs[0].value == "Documents"

    def test_track_other_correction(self, tracker, mock_paths):
        tracker.track_correction(
            mock_paths["src_txt"],
            mock_paths["dst_txt"],
            CorrectionType.MANUAL_OVERRIDE
        )
        
        prefs = tracker.get_all_preferences(PreferenceType.CUSTOM)
        assert len(prefs) == 1
        assert isinstance(prefs[0].value, dict)
        assert prefs[0].value["source"] == str(mock_paths["src_txt"])
        assert prefs[0].value["destination"] == str(mock_paths["dst_txt"])

    def test_extract_preferences_existing(self, tracker, mock_paths):
        # Apply the same correction 3 times
        for _ in range(3):
            tracker.track_correction(
                mock_paths["src_txt"],
                mock_paths["dst_txt"],
                CorrectionType.FILE_MOVE
            )
            
        prefs = tracker.get_all_preferences()
        assert len(prefs) == 1  # Should only be one preference
        pref = prefs[0]
        
        assert pref.metadata.frequency == 3
        # Confidence should increase: 0.5 -> 0.55 -> 0.595 -> etc
        assert pref.metadata.confidence > 0.5

    def test_extract_preferences_value_change(self, tracker, mock_paths):
        # 1st time
        tracker.track_correction(
            mock_paths["src_txt"],
            mock_paths["dst_txt"],
            CorrectionType.FILE_MOVE
        )
        
        # 2nd time, to a different dict
        dst_2 = Path("/docs/other/test.txt")
        # Need to match the pattern_key though...
        # For FILE_MOVE, pattern key is: `file_move|.txt|<dest_parent_name>`
        # So changing the dest path changes the pattern key! 
        # Thus it becomes a NEW preference. Let's verify that.
        tracker.track_correction(
            mock_paths["src_txt"],
            dst_2,
            CorrectionType.FILE_MOVE
        )
        
        prefs = tracker.get_all_preferences()
        assert len(prefs) == 2

    def test_get_preference_folder_mapping(self, tracker):
        # Train two models for .jpg
        tracker.track_correction(Path("/src/a.jpg"), Path("/dst/photos/a.jpg"), CorrectionType.FILE_MOVE)
        tracker.track_correction(Path("/src/b.jpg"), Path("/dst/images/b.jpg"), CorrectionType.FILE_MOVE)
        # Train images twice to give it higher confidence
        tracker.track_correction(Path("/src/c.jpg"), Path("/dst/images/c.jpg"), CorrectionType.FILE_MOVE)
        
        # Should return the one with higher confidence (images)
        pref = tracker.get_preference(Path("/src/unknown.jpg"), PreferenceType.FOLDER_MAPPING)
        assert pref is not None
        assert "images" in pref.value

    def test_get_preference_exact_match(self, tracker, mock_paths):
        tracker.track_correction(
            mock_paths["src_txt"],
            mock_paths["src_txt"],
            CorrectionType.CATEGORY_CHANGE,
            {"new_category": "Code"}
        )
        all_prefs = tracker.get_all_preferences()
        pref = tracker.get_preference(mock_paths["src_txt"], PreferenceType.CATEGORY_OVERRIDE)
        assert pref is not None
        assert pref.value == "Code"
        
        pref = tracker.get_preference(Path("/unknown/path.txt"), PreferenceType.CATEGORY_OVERRIDE)
        assert pref is None

    def test_update_preference_confidence(self, tracker, mock_paths):
        tracker.track_correction(mock_paths["src_txt"], mock_paths["dst_txt"], CorrectionType.FILE_MOVE)
        pref = tracker.get_all_preferences()[0]
        
        initial_confidence = pref.metadata.confidence
        
        # Success
        tracker.update_preference_confidence(pref, success=True)
        assert pref.metadata.confidence > initial_confidence
        
        # Failure
        confidence_after_success = pref.metadata.confidence
        tracker.update_preference_confidence(pref, success=False)
        assert pref.metadata.confidence < confidence_after_success

    def test_clear_preferences(self, tracker, mock_paths):
        tracker.track_correction(mock_paths["src_txt"], mock_paths["dst_txt"], CorrectionType.FILE_MOVE)
        tracker.track_correction(mock_paths["src_txt"], mock_paths["src_txt"], CorrectionType.CATEGORY_CHANGE, {"new_category": "Doc"})
        
        assert len(tracker.get_all_preferences()) == 2
        
        # Clear specific
        tracker.clear_preferences(PreferenceType.FILE_EXTENSION)  # Clears none
        assert len(tracker.get_all_preferences()) == 2
        
        tracker.clear_preferences(PreferenceType.FOLDER_MAPPING)  # Clears 1
        assert len(tracker.get_all_preferences()) == 1
        
        # Clear all
        tracker.clear_preferences()
        assert len(tracker.get_all_preferences()) == 0

    def test_export_import_data(self, tracker, mock_paths):
        tracker.track_correction(mock_paths["src_txt"], mock_paths["dst_txt"], CorrectionType.FILE_MOVE)
        
        data = tracker.export_data()
        assert "preferences" in data
        assert "corrections" in data
        assert "statistics" in data
        
        tracker2 = PreferenceTracker()
        tracker2.import_data(data)
        
        assert len(tracker2.get_all_preferences()) == 1
        assert tracker2.get_statistics()["total_corrections"] == 1

    def test_import_data_no_statistics(self, tracker):
        data = {
            "preferences": {},
            "corrections": []
        }
        tracker.import_data(data)
        stats = tracker.get_statistics()
        assert stats["total_corrections"] == 0

    def test_get_corrections_for_file(self, tracker, mock_paths):
        tracker.track_correction(mock_paths["src_txt"], mock_paths["dst_txt"], CorrectionType.FILE_MOVE)
        tracker.track_correction(mock_paths["src_img"], mock_paths["dst_img"], CorrectionType.FILE_MOVE)
        
        corrs = tracker.get_corrections_for_file(mock_paths["src_txt"])
        assert len(corrs) == 1
        assert corrs[0].source == mock_paths["src_txt"]

    def test_get_recent_corrections(self, tracker, mock_paths):
        for i in range(15):
            tracker.track_correction(Path(f"/src/{i}.txt"), Path(f"/dst/{i}.txt"), CorrectionType.FILE_MOVE)
            
        recent = tracker.get_recent_corrections(limit=5)
        assert len(recent) == 5

class TestConvenienceFunctions:
    def test_create_tracker(self):
        tracker = create_tracker()
        assert isinstance(tracker, PreferenceTracker)

    def test_track_file_move(self, tracker, mock_paths):
        track_file_move(tracker, mock_paths["src_txt"], mock_paths["dst_txt"])
        prefs = tracker.get_all_preferences(PreferenceType.FOLDER_MAPPING)
        assert len(prefs) == 1

    def test_track_file_rename(self, tracker, mock_paths):
        track_file_rename(tracker, mock_paths["src_txt"], Path("/docs/renamed.txt"))
        prefs = tracker.get_all_preferences(PreferenceType.NAMING_PATTERN)
        assert len(prefs) == 1

    def test_track_category_change(self, tracker, mock_paths):
        track_category_change(tracker, mock_paths["src_txt"], "Old", "New")
        prefs = tracker.get_all_preferences(PreferenceType.CATEGORY_OVERRIDE)
        assert len(prefs) == 1
        assert prefs[0].value == "New"
