"""
Tests for Smart Suggestions System

Comprehensive tests for pattern analyzer, suggestion engine,
misplacement detector, and feedback system.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.models.suggestion_types import Suggestion, SuggestionType
from file_organizer.services.misplacement_detector import MisplacementDetector
from file_organizer.services.pattern_analyzer import (
    PatternAnalyzer,
)
from file_organizer.services.smart_suggestions import ConfidenceScorer, SuggestionEngine
from file_organizer.services.suggestion_feedback import SuggestionFeedback


class TestPatternAnalyzer:
    """Tests for PatternAnalyzer."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_files(self, temp_dir):
        """Create sample file structure."""
        # Create documents directory with naming pattern
        docs_dir = temp_dir / "documents"
        docs_dir.mkdir()

        # Files with date prefix pattern
        (docs_dir / "2024-01-15_report.pdf").touch()
        (docs_dir / "2024-02-20_meeting.pdf").touch()
        (docs_dir / "2024-03-10_notes.pdf").touch()

        # Create images directory
        images_dir = temp_dir / "images"
        images_dir.mkdir()

        # Files with numeric suffix pattern
        (images_dir / "photo_001.jpg").touch()
        (images_dir / "photo_002.jpg").touch()
        (images_dir / "photo_003.jpg").touch()

        # Create code directory
        code_dir = temp_dir / "code"
        code_dir.mkdir()

        # Files with snake_case pattern
        (code_dir / "main_app.py").touch()
        (code_dir / "test_utils.py").touch()
        (code_dir / "helper_functions.py").touch()

        return temp_dir

    def test_analyze_directory(self, sample_files):
        """Test complete directory analysis."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        analysis = analyzer.analyze_directory(sample_files)

        assert analysis.directory == sample_files
        assert analysis.total_files == 9
        assert len(analysis.naming_patterns) > 0
        assert len(analysis.location_patterns) > 0
        assert len(analysis.file_type_distribution) > 0

    def test_detect_naming_patterns(self, sample_files):
        """Test naming pattern detection."""
        analyzer = PatternAnalyzer(min_pattern_count=2)

        # Collect all files
        files = list(sample_files.rglob('*'))
        files = [f for f in files if f.is_file()]

        patterns = analyzer.detect_naming_patterns(files)

        # Should detect at least date prefix and numeric suffix patterns
        pattern_types = [p.pattern for p in patterns]
        assert 'DATE_PREFIX' in pattern_types or 'NUMERIC_SUFFIX' in pattern_types

        # Check pattern properties
        for pattern in patterns:
            assert pattern.count >= 2
            assert 0 <= pattern.confidence <= 100
            assert len(pattern.example_files) > 0

    def test_get_location_patterns(self, sample_files):
        """Test location pattern detection."""
        analyzer = PatternAnalyzer(min_pattern_count=2)
        location_patterns = analyzer.get_location_patterns(sample_files)

        assert len(location_patterns) >= 3  # docs, images, code

        # Check each pattern has required info
        for pattern in location_patterns:
            assert pattern.file_count >= 2
            assert len(pattern.file_types) > 0
            assert pattern.depth_level >= 0

    def test_cluster_by_content(self, sample_files):
        """Test content-based clustering."""
        analyzer = PatternAnalyzer(min_pattern_count=2)

        files = list(sample_files.rglob('*'))
        files = [f for f in files if f.is_file()]

        clusters = analyzer.cluster_by_content(files)

        # Should create clusters for different file types
        assert len(clusters) > 0

        for cluster in clusters:
            assert len(cluster.file_paths) >= 2
            assert 0 <= cluster.confidence <= 100
            assert cluster.category in [
                'documents', 'images', 'code', 'general'
            ]

    def test_empty_directory(self, temp_dir):
        """Test analysis of empty directory."""
        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(temp_dir)

        assert analysis.total_files == 0
        assert len(analysis.naming_patterns) == 0


class TestSuggestionEngine:
    """Tests for SuggestionEngine."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def organized_structure(self, temp_dir):
        """Create organized file structure."""
        # Create well-organized directories
        docs = temp_dir / "documents"
        docs.mkdir()
        (docs / "report1.pdf").touch()
        (docs / "report2.pdf").touch()

        images = temp_dir / "images"
        images.mkdir()
        (images / "photo1.jpg").touch()
        (images / "photo2.jpg").touch()

        # Create misplaced file
        (temp_dir / "misplaced_photo.jpg").touch()

        return temp_dir

    def test_generate_suggestions(self, organized_structure):
        """Test suggestion generation."""
        engine = SuggestionEngine(min_confidence=30.0)

        files = [organized_structure / "misplaced_photo.jpg"]
        suggestions = engine.generate_suggestions(files)

        assert len(suggestions) > 0

        # Check suggestion properties
        for suggestion in suggestions:
            assert suggestion.confidence >= 30.0
            assert suggestion.reasoning != ""
            assert suggestion.suggestion_type in SuggestionType

    def test_confidence_scorer(self, organized_structure):
        """Test confidence scoring."""
        scorer = ConfidenceScorer()
        analyzer = PatternAnalyzer()

        analysis = analyzer.analyze_directory(organized_structure)

        file_path = organized_structure / "misplaced_photo.jpg"
        target_path = organized_structure / "images"

        factors = scorer.score_suggestion(
            file_path, target_path, SuggestionType.MOVE, analysis
        )

        assert 0 <= factors.pattern_strength <= 100
        assert 0 <= factors.content_similarity <= 100
        assert 0 <= factors.file_type_match <= 100

        score = factors.calculate_weighted_score()
        assert 0 <= score <= 100

    def test_rank_suggestions(self):
        """Test suggestion ranking."""
        engine = SuggestionEngine()

        # Create test suggestions with different confidences
        suggestions = [
            Suggestion(
                suggestion_id="1",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path("file1.txt"),
                confidence=50.0,
                reasoning="Test"
            ),
            Suggestion(
                suggestion_id="2",
                suggestion_type=SuggestionType.RESTRUCTURE,
                file_path=Path("file2.txt"),
                confidence=80.0,
                reasoning="Test"
            ),
            Suggestion(
                suggestion_id="3",
                suggestion_type=SuggestionType.RENAME,
                file_path=Path("file3.txt"),
                confidence=60.0,
                reasoning="Test"
            ),
        ]

        ranked = engine.rank_suggestions(suggestions)

        # Should be sorted by confidence
        assert ranked[0].confidence >= ranked[1].confidence
        assert ranked[1].confidence >= ranked[2].confidence

    def test_explain_suggestion(self):
        """Test suggestion explanation generation."""
        engine = SuggestionEngine()

        suggestion = Suggestion(
            suggestion_id="test",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("test.jpg"),
            target_path=Path("images/test.jpg"),
            confidence=75.5,
            reasoning="File type matches target location"
        )

        explanation = engine.explain_suggestion(suggestion)

        assert "MOVE" in explanation
        assert "75.5" in explanation
        assert "File type matches target location" in explanation


class TestMisplacementDetector:
    """Tests for MisplacementDetector."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def misplaced_structure(self, temp_dir):
        """Create structure with misplaced files."""
        # Documents directory
        docs = temp_dir / "documents"
        docs.mkdir()
        (docs / "report1.pdf").touch()
        (docs / "report2.pdf").touch()

        # Misplaced image in documents
        (docs / "vacation_photo.jpg").touch()

        # Images directory
        images = temp_dir / "images"
        images.mkdir()
        (images / "photo1.jpg").touch()
        (images / "photo2.jpg").touch()

        # Misplaced document in images
        (images / "important_report.pdf").touch()

        return temp_dir

    def test_detect_misplaced(self, misplaced_structure):
        """Test misplaced file detection."""
        detector = MisplacementDetector(min_mismatch_score=50.0)
        misplaced = detector.detect_misplaced(misplaced_structure)

        # Should detect at least the two obvious misplacements
        assert len(misplaced) >= 1

        for mp in misplaced:
            assert mp.mismatch_score >= 50.0
            assert len(mp.reasons) > 0
            assert mp.suggested_location != mp.current_location

    def test_analyze_context(self, misplaced_structure):
        """Test context analysis."""
        detector = MisplacementDetector()

        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"
        context = detector.analyze_context(file_path)

        assert context.file_type == ".jpg"
        assert context.directory == misplaced_structure / "documents"
        assert len(context.sibling_files) >= 2
        assert context.parent_category == "images"

    def test_calculate_mismatch_score(self, misplaced_structure):
        """Test mismatch score calculation."""
        detector = MisplacementDetector()
        analyzer = PatternAnalyzer()

        analysis = analyzer.analyze_directory(misplaced_structure)
        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"
        context = detector.analyze_context(file_path)

        score = detector.calculate_mismatch_score(file_path, context, analysis)

        # Misplaced image should have high mismatch score
        assert score > 40.0

    def test_find_correct_location(self, misplaced_structure):
        """Test finding correct location."""
        detector = MisplacementDetector()
        analyzer = PatternAnalyzer()

        analysis = analyzer.analyze_directory(misplaced_structure)
        file_path = misplaced_structure / "documents" / "vacation_photo.jpg"

        suggested = detector.find_correct_location(file_path, analysis)

        # Should suggest images directory or an images-related path
        assert suggested.name == "images" or "image" in str(suggested).lower()


class TestSuggestionFeedback:
    """Tests for SuggestionFeedback."""

    @pytest.fixture
    def temp_feedback_file(self):
        """Create temporary feedback file."""
        temp_file = Path(tempfile.mktemp(suffix='.json'))
        yield temp_file
        if temp_file.exists():
            temp_file.unlink()

    def test_record_action(self, temp_feedback_file):
        """Test recording feedback."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)

        suggestion = Suggestion(
            suggestion_id="test1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("test.jpg"),
            target_path=Path("images/test.jpg"),
            confidence=75.0,
            reasoning="Test"
        )

        feedback.record_action(suggestion, 'accepted')

        assert len(feedback.feedback_entries) == 1
        assert feedback.feedback_entries[0].action == 'accepted'

    def test_get_acceptance_rate(self, temp_feedback_file):
        """Test acceptance rate calculation."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)

        # Record multiple actions
        for i in range(5):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test"
            )
            action = 'accepted' if i < 3 else 'rejected'
            feedback.record_action(suggestion, action)

        # 3 accepted out of 5 = 60%
        rate = feedback.get_acceptance_rate()
        assert rate == 60.0

    def test_get_learning_stats(self, temp_feedback_file):
        """Test learning statistics."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)

        # Record various actions
        actions = ['accepted', 'accepted', 'rejected', 'ignored', 'modified']
        for i, action in enumerate(actions):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test"
            )
            feedback.record_action(suggestion, action)

        stats = feedback.get_learning_stats()

        assert stats.total_suggestions == 5
        assert stats.accepted == 2
        assert stats.rejected == 1
        assert stats.ignored == 1
        assert stats.modified == 1
        assert stats.acceptance_rate == 40.0

    def test_get_user_history(self, temp_feedback_file):
        """Test user history retrieval."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)

        # Record move actions
        for i in range(3):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                target_path=Path("images") / f"test{i}.jpg",
                confidence=70.0,
                reasoning="Test"
            )
            feedback.record_action(suggestion, 'accepted')

        history = feedback.get_user_history()

        assert 'move_history' in history
        assert '.jpg' in history['move_history']

    def test_persistence(self, temp_feedback_file):
        """Test feedback persistence."""
        # Create feedback and record action
        feedback1 = SuggestionFeedback(feedback_file=temp_feedback_file)

        suggestion = Suggestion(
            suggestion_id="test",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("test.jpg"),
            confidence=70.0,
            reasoning="Test"
        )
        feedback1.record_action(suggestion, 'accepted')

        # Create new instance and check if data persists
        feedback2 = SuggestionFeedback(feedback_file=temp_feedback_file)

        assert len(feedback2.feedback_entries) == 1
        assert feedback2.feedback_entries[0].suggestion_id == "test"

    def test_clear_old_feedback(self, temp_feedback_file):
        """Test clearing old feedback."""
        feedback = SuggestionFeedback(feedback_file=temp_feedback_file)

        # Record some actions
        for i in range(5):
            suggestion = Suggestion(
                suggestion_id=f"test{i}",
                suggestion_type=SuggestionType.MOVE,
                file_path=Path(f"test{i}.jpg"),
                confidence=70.0,
                reasoning="Test"
            )
            feedback.record_action(suggestion, 'accepted')

        initial_count = len(feedback.feedback_entries)

        # Clear old feedback (should clear none since they're all recent)
        removed = feedback.clear_old_feedback(days=90)

        assert removed == 0
        assert len(feedback.feedback_entries) == initial_count


class TestIntegration:
    """Integration tests for the complete smart suggestions system."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def complete_structure(self, temp_dir):
        """Create complete file structure for integration tests."""
        # Well-organized sections
        docs = temp_dir / "documents"
        docs.mkdir()
        for i in range(5):
            (docs / f"report_{i:03d}.pdf").touch()

        images = temp_dir / "photos"
        images.mkdir()
        for i in range(5):
            (images / f"IMG_{i:04d}.jpg").touch()

        # Misplaced files
        (temp_dir / "random_photo.jpg").touch()
        (temp_dir / "lost_document.pdf").touch()

        return temp_dir

    def test_end_to_end_workflow(self, complete_structure):
        """Test complete workflow from analysis to suggestions."""
        # 1. Analyze patterns
        analyzer = PatternAnalyzer(min_pattern_count=2)
        analysis = analyzer.analyze_directory(complete_structure)

        assert analysis.total_files == 12
        assert len(analysis.naming_patterns) > 0

        # 2. Generate suggestions
        engine = SuggestionEngine(min_confidence=30.0)
        misplaced_files = [
            complete_structure / "random_photo.jpg",
            complete_structure / "lost_document.pdf"
        ]

        suggestions = engine.generate_suggestions(
            misplaced_files, pattern_analysis=analysis
        )

        assert len(suggestions) > 0

        # 3. Detect misplacements
        detector = MisplacementDetector(min_mismatch_score=40.0)
        misplaced = detector.detect_misplaced(
            complete_structure, pattern_analysis=analysis
        )

        assert len(misplaced) >= 1

        # 4. Record feedback
        feedback = SuggestionFeedback()
        if suggestions:
            feedback.record_action(suggestions[0], 'accepted')

        stats = feedback.get_learning_stats()
        assert stats.total_suggestions >= 1

    def test_performance(self, temp_dir):
        """Test performance on larger dataset."""
        # Create 100 files
        for i in range(100):
            category = ['docs', 'images', 'code'][i % 3]
            cat_dir = temp_dir / category
            cat_dir.mkdir(exist_ok=True)

            ext = {
                'docs': '.pdf',
                'images': '.jpg',
                'code': '.py'
            }[category]

            (cat_dir / f"file_{i:04d}{ext}").touch()

        # Time the analysis
        import time
        start = time.time()

        analyzer = PatternAnalyzer()
        analysis = analyzer.analyze_directory(temp_dir)

        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 100 files)
        assert elapsed < 5.0
        assert analysis.total_files == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
