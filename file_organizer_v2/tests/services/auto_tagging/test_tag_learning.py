"""Tests for TagLearningEngine."""

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from file_organizer.services.auto_tagging.tag_learning import (
    TagLearningEngine,
    TagPattern,
    TagUsage,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def storage_path(temp_dir):
    """Create a storage path for learning data."""
    return temp_dir / "tag_learning.json"


@pytest.fixture
def engine(storage_path):
    """Create a TagLearningEngine instance."""
    return TagLearningEngine(storage_path=storage_path)


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file."""
    file_path = temp_dir / "test_document.pdf"
    file_path.write_text("sample content")
    return file_path


class TestTagUsage:
    """Tests for TagUsage dataclass."""

    def test_initialization(self):
        """Test TagUsage initialization."""
        now = datetime.now()
        usage = TagUsage(
            tag="python",
            count=5,
            first_used=now,
            last_used=now
        )

        assert usage.tag == "python"
        assert usage.count == 5
        assert usage.first_used == now
        assert usage.last_used == now
        assert isinstance(usage.file_types, set)
        assert isinstance(usage.contexts, list)

    def test_to_dict(self):
        """Test converting to dictionary."""
        now = datetime.now()
        usage = TagUsage(tag="python", count=3, first_used=now, last_used=now)
        usage.file_types.add('.py')
        usage.contexts.append('{"type": "code"}')

        data = usage.to_dict()

        assert data['tag'] == "python"
        assert data['count'] == 3
        assert '.py' in data['file_types']
        assert len(data['contexts']) == 1

    def test_from_dict(self):
        """Test creating from dictionary."""
        now = datetime.now()
        data = {
            'tag': 'python',
            'count': 5,
            'first_used': now.isoformat(),
            'last_used': now.isoformat(),
            'file_types': ['.py', '.pyw'],
            'contexts': ['{"test": 1}']
        }

        usage = TagUsage.from_dict(data)

        assert usage.tag == "python"
        assert usage.count == 5
        assert len(usage.file_types) == 2


class TestTagPattern:
    """Tests for TagPattern dataclass."""

    def test_initialization(self):
        """Test TagPattern initialization."""
        pattern = TagPattern(
            pattern_type='frequency',
            tags=['python'],
            frequency=10.0,
            confidence=85.0
        )

        assert pattern.pattern_type == 'frequency'
        assert pattern.tags == ['python']
        assert pattern.frequency == 10.0
        assert pattern.confidence == 85.0

    def test_to_from_dict(self):
        """Test dictionary conversion."""
        now = datetime.now()
        pattern = TagPattern(
            pattern_type='co-occurrence',
            tags=['python', 'ml'],
            frequency=5.0,
            confidence=75.0,
            last_seen=now
        )

        data = pattern.to_dict()
        restored = TagPattern.from_dict(data)

        assert restored.pattern_type == pattern.pattern_type
        assert restored.tags == pattern.tags
        assert restored.frequency == pattern.frequency


class TestTagLearningEngine:
    """Tests for TagLearningEngine class."""

    def test_initialization(self, engine, storage_path):
        """Test engine initialization."""
        assert engine.storage_path == storage_path
        assert isinstance(engine.tag_usage, dict)
        assert isinstance(engine.tag_cooccurrence, dict)
        assert isinstance(engine.file_type_tags, dict)
        assert isinstance(engine.directory_tags, dict)

    def test_record_tag_application_single(self, engine, sample_file):
        """Test recording a single tag application."""
        engine.record_tag_application(sample_file, ['python'])

        assert 'python' in engine.tag_usage
        usage = engine.tag_usage['python']
        assert usage.count == 1
        assert usage.first_used is not None
        assert usage.last_used is not None
        assert '.pdf' in usage.file_types

    def test_record_tag_application_multiple(self, engine, sample_file):
        """Test recording multiple tags."""
        tags = ['python', 'machine-learning', 'tutorial']
        engine.record_tag_application(sample_file, tags)

        assert len(engine.tag_usage) == 3
        assert all(tag in engine.tag_usage for tag in tags)

        # Check co-occurrence tracking
        assert 'machine-learning' in engine.tag_cooccurrence['python']
        assert 'tutorial' in engine.tag_cooccurrence['python']

    def test_record_multiple_applications(self, engine, sample_file):
        """Test recording the same tag multiple times."""
        engine.record_tag_application(sample_file, ['python'])
        engine.record_tag_application(sample_file, ['python'])

        usage = engine.tag_usage['python']
        assert usage.count == 2

    def test_get_tag_patterns(self, engine, sample_file):
        """Test getting learned patterns."""
        # Record some data (need multiple occurrences for co-occurrence patterns)
        engine.record_tag_application(sample_file, ['python', 'ml'])
        engine.record_tag_application(sample_file, ['python', 'ml'])  # Second occurrence
        engine.record_tag_application(sample_file, ['python', 'data'])

        patterns = engine.get_tag_patterns()

        assert len(patterns) > 0
        # Should have frequency patterns
        freq_patterns = [p for p in patterns if p.pattern_type == 'frequency']
        assert len(freq_patterns) > 0

        # Should have co-occurrence patterns (requires at least 2 co-occurrences)
        cooccur_patterns = [p for p in patterns if p.pattern_type == 'co-occurrence']
        assert len(cooccur_patterns) > 0

    def test_get_tag_patterns_by_file_type(self, engine, temp_dir):
        """Test filtering patterns by file type."""
        # Create files with different extensions
        py_file = temp_dir / "script.py"
        txt_file = temp_dir / "doc.txt"
        py_file.write_text("code")
        txt_file.write_text("text")

        engine.record_tag_application(py_file, ['python', 'code'])
        engine.record_tag_application(txt_file, ['document', 'text'])

        # Get patterns for Python files
        py_patterns = engine.get_tag_patterns(file_type='.py')
        py_tags = {tag for p in py_patterns for tag in p.tags}

        assert 'python' in py_tags or 'code' in py_tags

    def test_predict_tags(self, engine, temp_dir):
        """Test tag prediction."""
        # Train with some data
        py_file = temp_dir / "script.py"
        py_file.write_text("code")

        engine.record_tag_application(py_file, ['python', 'code'])
        engine.record_tag_application(py_file, ['python', 'script'])

        # Predict for new file
        new_file = temp_dir / "new_script.py"
        new_file.write_text("new code")

        predictions = engine.predict_tags(new_file, max_predictions=5)

        assert isinstance(predictions, list)
        assert len(predictions) > 0
        # Should return (tag, confidence) tuples
        for tag, confidence in predictions:
            assert isinstance(tag, str)
            assert 0 <= confidence <= 100

    def test_get_related_tags(self, engine, sample_file):
        """Test getting related tags."""
        # Record co-occurring tags
        engine.record_tag_application(sample_file, ['python', 'ml', 'data'])
        engine.record_tag_application(sample_file, ['python', 'ml'])

        related = engine.get_related_tags('python', max_related=5)

        assert 'ml' in related
        assert isinstance(related, list)

    def test_update_model_with_feedback(self, engine, sample_file):
        """Test updating model with user feedback."""
        # Initial data
        engine.record_tag_application(sample_file, ['python'])

        # Feedback
        feedback = [
            {
                'file_path': str(sample_file),
                'suggested_tags': ['python', 'java'],
                'accepted_tags': ['python'],
                'rejected_tags': ['java'],
                'timestamp': datetime.now().isoformat()
            }
        ]

        initial_python_count = engine.tag_usage['python'].count
        engine.update_model(feedback)

        # Python count should increase
        assert engine.tag_usage['python'].count > initial_python_count

    def test_get_popular_tags(self, engine, sample_file):
        """Test getting popular tags."""
        # Record different frequencies
        engine.record_tag_application(sample_file, ['python'])
        engine.record_tag_application(sample_file, ['python'])
        engine.record_tag_application(sample_file, ['python'])
        engine.record_tag_application(sample_file, ['java'])

        popular = engine.get_popular_tags(limit=10)

        assert len(popular) > 0
        # Python should be more popular
        tags_dict = dict(popular)
        assert tags_dict['python'] > tags_dict['java']

    def test_get_recent_tags(self, engine, sample_file):
        """Test getting recent tags."""
        engine.record_tag_application(sample_file, ['python', 'recent'])

        recent = engine.get_recent_tags(days=30, limit=10)

        assert 'python' in recent
        assert 'recent' in recent

    def test_get_tag_suggestions_for_context(self, engine, temp_dir):
        """Test context-based suggestions."""
        # Record tags in specific context
        py_file = temp_dir / "code" / "script.py"
        py_file.parent.mkdir(exist_ok=True)
        py_file.write_text("code")

        engine.record_tag_application(py_file, ['python', 'code'])

        # Get suggestions for similar context
        suggestions = engine.get_tag_suggestions_for_context(
            file_type='.py',
            directory=str(py_file.parent),
            limit=5
        )

        assert len(suggestions) > 0
        tags = [tag for tag, _ in suggestions]
        assert 'python' in tags or 'code' in tags

    def test_get_tag_suggestions_with_existing_tags(self, engine, sample_file):
        """Test suggestions based on existing tags."""
        # Record co-occurring tags
        engine.record_tag_application(sample_file, ['python', 'ml'])
        engine.record_tag_application(sample_file, ['python', 'data'])

        # Get suggestions given 'python'
        suggestions = engine.get_tag_suggestions_for_context(
            existing_tags=['python'],
            limit=5
        )

        tags = [tag for tag, _ in suggestions]
        # Should suggest tags that co-occur with python
        assert 'ml' in tags or 'data' in tags
        # Should not suggest python itself
        assert 'python' not in tags

    def test_calculate_tag_confidence(self, engine):
        """Test confidence calculation."""
        now = datetime.now()

        # Recent, frequent tag
        recent_usage = TagUsage(
            tag='python',
            count=10,
            first_used=now,
            last_used=now
        )
        recent_usage.file_types.add('.py')
        recent_usage.file_types.add('.pyw')

        confidence = engine._calculate_tag_confidence(recent_usage)
        assert confidence > 50  # Should be high

        # Old, infrequent tag
        old_usage = TagUsage(
            tag='old',
            count=1,
            first_used=now - timedelta(days=200),
            last_used=now - timedelta(days=200)
        )

        confidence = engine._calculate_tag_confidence(old_usage)
        assert confidence < 50  # Should be lower

    def test_save_and_load_data(self, engine, sample_file, storage_path):
        """Test saving and loading learning data."""
        # Record some data
        engine.record_tag_application(sample_file, ['python', 'test'])

        # Create new engine with same storage
        new_engine = TagLearningEngine(storage_path=storage_path)

        # Should load existing data
        assert 'python' in new_engine.tag_usage
        assert 'test' in new_engine.tag_usage

    def test_file_type_tags_tracking(self, engine, temp_dir):
        """Test tracking tags by file type."""
        py_file = temp_dir / "script.py"
        txt_file = temp_dir / "doc.txt"
        py_file.write_text("code")
        txt_file.write_text("text")

        engine.record_tag_application(py_file, ['python'])
        engine.record_tag_application(txt_file, ['document'])

        assert '.py' in engine.file_type_tags
        assert 'python' in engine.file_type_tags['.py']
        assert '.txt' in engine.file_type_tags
        assert 'document' in engine.file_type_tags['.txt']

    def test_directory_tags_tracking(self, engine, temp_dir):
        """Test tracking tags by directory."""
        subdir = temp_dir / "projects"
        subdir.mkdir()
        file_path = subdir / "test.txt"
        file_path.write_text("content")

        engine.record_tag_application(file_path, ['project'])

        assert str(subdir) in engine.directory_tags
        assert 'project' in engine.directory_tags[str(subdir)]

    def test_empty_tags_list(self, engine, sample_file):
        """Test recording with empty tags list."""
        engine.record_tag_application(sample_file, [])

        # Should not crash, should not add anything
        assert len(engine.tag_usage) == 0

    def test_tag_cooccurrence_symmetry(self, engine, sample_file):
        """Test that tag co-occurrence is symmetric."""
        engine.record_tag_application(sample_file, ['tag1', 'tag2'])

        assert 'tag2' in engine.tag_cooccurrence['tag1']
        assert 'tag1' in engine.tag_cooccurrence['tag2']
        assert (engine.tag_cooccurrence['tag1']['tag2'] ==
                engine.tag_cooccurrence['tag2']['tag1'])
