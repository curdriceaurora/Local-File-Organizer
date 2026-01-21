"""Tests for TagRecommender."""

import pytest
from pathlib import Path
import tempfile
import shutil

from file_organizer.services.auto_tagging.tag_recommender import (
    TagRecommender,
    TagSuggestion,
    TagRecommendation
)
from file_organizer.services.auto_tagging.content_analyzer import ContentTagAnalyzer
from file_organizer.services.auto_tagging.tag_learning import TagLearningEngine


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def analyzer():
    """Create a ContentTagAnalyzer instance."""
    return ContentTagAnalyzer()


@pytest.fixture
def learning_engine(temp_dir):
    """Create a TagLearningEngine instance."""
    storage_path = temp_dir / "learning.json"
    return TagLearningEngine(storage_path=storage_path)


@pytest.fixture
def recommender(analyzer, learning_engine):
    """Create a TagRecommender instance."""
    return TagRecommender(
        content_analyzer=analyzer,
        learning_engine=learning_engine,
        min_confidence=30.0
    )


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file."""
    file_path = temp_dir / "python_tutorial.txt"
    content = """
    Python Programming Tutorial
    Learn Python basics, data structures, and algorithms.
    Machine learning with Python and scikit-learn.
    """
    file_path.write_text(content)
    return file_path


@pytest.fixture
def trained_recommender(recommender, temp_dir):
    """Create a recommender with some training data."""
    # Create training files
    for i in range(5):
        file_path = temp_dir / f"training_{i}.py"
        file_path.write_text("python code")
        recommender.learning_engine.record_tag_application(
            file_path,
            ['python', 'code', 'programming']
        )

    return recommender


class TestTagSuggestion:
    """Tests for TagSuggestion dataclass."""

    def test_initialization(self):
        """Test TagSuggestion initialization."""
        suggestion = TagSuggestion(
            tag='python',
            confidence=75.0,
            source='content',
            reasoning='Found in file content'
        )

        assert suggestion.tag == 'python'
        assert suggestion.confidence == 75.0
        assert suggestion.source == 'content'
        assert suggestion.reasoning == 'Found in file content'

    def test_to_dict(self):
        """Test converting to dictionary."""
        suggestion = TagSuggestion(
            tag='python',
            confidence=80.0,
            source='hybrid',
            reasoning='Multiple sources',
            metadata={'test': 'value'}
        )

        data = suggestion.to_dict()

        assert data['tag'] == 'python'
        assert data['confidence'] == 80.0
        assert data['source'] == 'hybrid'
        assert data['metadata']['test'] == 'value'

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            'tag': 'ml',
            'confidence': 65.0,
            'source': 'behavior',
            'reasoning': 'Usage pattern',
            'metadata': {}
        }

        suggestion = TagSuggestion.from_dict(data)

        assert suggestion.tag == 'ml'
        assert suggestion.confidence == 65.0
        assert suggestion.source == 'behavior'


class TestTagRecommendation:
    """Tests for TagRecommendation dataclass."""

    def test_initialization(self, sample_file):
        """Test TagRecommendation initialization."""
        suggestions = [
            TagSuggestion('python', 80.0, 'content', 'reason1'),
            TagSuggestion('tutorial', 60.0, 'content', 'reason2'),
            TagSuggestion('code', 40.0, 'behavior', 'reason3')
        ]

        recommendation = TagRecommendation(
            file_path=sample_file,
            suggestions=suggestions,
            existing_tags=['programming']
        )

        assert recommendation.file_path == sample_file
        assert len(recommendation.suggestions) == 3
        assert recommendation.existing_tags == ['programming']

    def test_get_high_confidence_tags(self, sample_file):
        """Test filtering high confidence tags."""
        suggestions = [
            TagSuggestion('python', 80.0, 'content', 'reason'),
            TagSuggestion('ml', 75.0, 'hybrid', 'reason'),
            TagSuggestion('code', 50.0, 'behavior', 'reason')
        ]

        recommendation = TagRecommendation(
            file_path=sample_file,
            suggestions=suggestions
        )

        high_conf = recommendation.get_high_confidence_tags()

        assert len(high_conf) == 2
        assert 'python' in high_conf
        assert 'ml' in high_conf
        assert 'code' not in high_conf

    def test_get_medium_confidence_tags(self, sample_file):
        """Test filtering medium confidence tags."""
        suggestions = [
            TagSuggestion('python', 80.0, 'content', 'reason'),
            TagSuggestion('tutorial', 60.0, 'content', 'reason'),
            TagSuggestion('code', 45.0, 'behavior', 'reason'),
            TagSuggestion('test', 30.0, 'behavior', 'reason')
        ]

        recommendation = TagRecommendation(
            file_path=sample_file,
            suggestions=suggestions
        )

        medium_conf = recommendation.get_medium_confidence_tags()

        assert len(medium_conf) == 2
        assert 'tutorial' in medium_conf
        assert 'code' in medium_conf

    def test_to_dict(self, sample_file):
        """Test converting to dictionary."""
        suggestions = [
            TagSuggestion('python', 75.0, 'content', 'reason')
        ]

        recommendation = TagRecommendation(
            file_path=sample_file,
            suggestions=suggestions
        )

        data = recommendation.to_dict()

        assert 'file_path' in data
        assert 'suggestions' in data
        assert len(data['suggestions']) == 1


class TestTagRecommender:
    """Tests for TagRecommender class."""

    def test_initialization(self, analyzer, learning_engine):
        """Test recommender initialization."""
        recommender = TagRecommender(
            content_analyzer=analyzer,
            learning_engine=learning_engine,
            min_confidence=50.0
        )

        assert recommender.content_analyzer == analyzer
        assert recommender.learning_engine == learning_engine
        assert recommender.min_confidence == 50.0

    def test_recommend_tags_basic(self, recommender, sample_file):
        """Test basic tag recommendation."""
        recommendation = recommender.recommend_tags(sample_file, top_n=10)

        assert isinstance(recommendation, TagRecommendation)
        assert recommendation.file_path == sample_file
        assert isinstance(recommendation.suggestions, list)
        assert len(recommendation.suggestions) > 0

    def test_recommend_tags_with_existing(self, recommender, sample_file):
        """Test recommendation with existing tags."""
        existing = ['programming', 'tutorial']
        recommendation = recommender.recommend_tags(
            sample_file,
            existing_tags=existing,
            top_n=10
        )

        # Should not suggest existing tags
        suggested_tags = [s.tag for s in recommendation.suggestions]
        assert 'programming' not in suggested_tags
        assert 'tutorial' not in suggested_tags

    def test_recommend_tags_nonexistent_file(self, recommender, temp_dir):
        """Test recommending for nonexistent file."""
        fake_path = temp_dir / "nonexistent.txt"
        recommendation = recommender.recommend_tags(fake_path)

        assert len(recommendation.suggestions) == 0

    def test_recommend_tags_top_n_limit(self, recommender, sample_file):
        """Test that top_n limit is respected."""
        recommendation = recommender.recommend_tags(sample_file, top_n=3)

        assert len(recommendation.suggestions) <= 3

    def test_recommend_tags_min_confidence(self, sample_file):
        """Test minimum confidence filtering."""
        recommender = TagRecommender(min_confidence=70.0)
        recommendation = recommender.recommend_tags(sample_file)

        # All suggestions should meet threshold
        for suggestion in recommendation.suggestions:
            assert suggestion.confidence >= 70.0

    def test_batch_recommend(self, recommender, temp_dir):
        """Test batch recommendation."""
        # Create multiple files
        files = []
        for i in range(3):
            file_path = temp_dir / f"test_{i}.txt"
            file_path.write_text(f"test content {i}")
            files.append(file_path)

        results = recommender.batch_recommend(files, top_n=5)

        assert len(results) == 3
        assert all(isinstance(r, TagRecommendation) for r in results.values())
        assert all(f in results for f in files)

    def test_calculate_confidence(self, recommender, sample_file):
        """Test confidence calculation for specific tag."""
        confidence = recommender.calculate_confidence('python', sample_file)

        assert 0 <= confidence <= 100
        assert isinstance(confidence, float)

    def test_explain_tag(self, trained_recommender, temp_dir):
        """Test tag explanation generation."""
        file_path = temp_dir / "test.py"
        file_path.write_text("python code")

        explanation = trained_recommender.explain_tag('python', file_path)

        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_explain_tag_with_existing(self, trained_recommender, temp_dir):
        """Test explanation with existing tags."""
        file_path = temp_dir / "test.py"
        file_path.write_text("python code")

        explanation = trained_recommender.explain_tag(
            'code',
            file_path,
            existing_tags=['python']
        )

        assert isinstance(explanation, str)

    def test_content_suggestions(self, recommender, sample_file):
        """Test getting content-based suggestions."""
        suggestions = recommender._get_content_suggestions(sample_file)

        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        # Check format
        for tag, confidence in suggestions:
            assert isinstance(tag, str)
            assert 0 <= confidence <= 100

    def test_behavior_suggestions(self, trained_recommender, temp_dir):
        """Test getting behavior-based suggestions."""
        file_path = temp_dir / "new.py"
        file_path.write_text("code")

        suggestions = trained_recommender._get_behavior_suggestions(
            file_path,
            existing_tags=[]
        )

        assert isinstance(suggestions, list)
        # Should have learned from training data
        if suggestions:
            tags = [tag for tag, _ in suggestions]
            assert 'python' in tags or 'code' in tags

    def test_related_suggestions(self, trained_recommender):
        """Test getting related tag suggestions."""
        # Training data has python, code, programming together
        suggestions = trained_recommender._get_related_suggestions(['python'])

        assert isinstance(suggestions, list)
        if suggestions:
            tags = [tag for tag, _ in suggestions]
            assert 'code' in tags or 'programming' in tags

    def test_combine_confidences(self, recommender):
        """Test combining confidence scores."""
        combined = recommender._combine_confidences(
            70.0, 80.0,
            'content', 'behavior'
        )

        assert 0 <= combined <= 100
        # Should be somewhere between the two values
        assert 70.0 <= combined <= 90.0

    def test_rank_suggestions(self, recommender):
        """Test suggestion ranking."""
        suggestions = [
            TagSuggestion('tag1', 60.0, 'content', 'reason'),
            TagSuggestion('tag2', 80.0, 'hybrid', 'reason'),
            TagSuggestion('tag3', 70.0, 'behavior', 'reason'),
            TagSuggestion('tag4', 80.0, 'content', 'reason')
        ]

        ranked = recommender._rank_suggestions(suggestions)

        # Should be sorted by confidence (descending)
        confidences = [s.confidence for s in ranked]
        assert confidences == sorted(confidences, reverse=True)

        # Higher priority sources should come first for same confidence
        # (hybrid > behavior > content)
        same_conf_80 = [s for s in ranked if s.confidence == 80.0]
        if len(same_conf_80) == 2:
            assert same_conf_80[0].source == 'hybrid'

    def test_multiple_source_combination(self, recommender, sample_file):
        """Test combining suggestions from multiple sources."""
        # Train with some data
        recommender.learning_engine.record_tag_application(
            sample_file,
            ['python', 'tutorial']
        )

        recommendation = recommender.recommend_tags(sample_file)

        # Should have suggestions from both content and behavior
        sources = {s.source for s in recommendation.suggestions}
        # Might have content, behavior, or hybrid
        assert len(sources) > 0

    def test_suggestion_reasoning(self, recommender):
        """Test reasoning generation for suggestions."""
        content_reason = recommender._generate_content_reasoning(
            'python',
            Path('test.py')
        )
        assert 'content' in content_reason.lower() or 'metadata' in content_reason.lower()

        behavior_reason = recommender._generate_behavior_reasoning(
            'python',
            Path('test.py')
        )
        assert 'pattern' in behavior_reason.lower()

        hybrid_reason = recommender._generate_hybrid_reasoning(
            'python',
            Path('test.py')
        )
        assert 'content' in hybrid_reason.lower() and 'pattern' in hybrid_reason.lower()

    def test_empty_learning_data(self, recommender, sample_file):
        """Test recommendation with no learning data."""
        # Fresh recommender with no training
        recommendation = recommender.recommend_tags(sample_file)

        # Should still provide content-based suggestions
        assert len(recommendation.suggestions) > 0
        # All suggestions should be from content analysis
        sources = {s.source for s in recommendation.suggestions}
        assert sources == {'content'}

    def test_recommendation_confidence_filtering(self, sample_file):
        """Test that low confidence suggestions are filtered."""
        recommender = TagRecommender(min_confidence=80.0)
        recommendation = recommender.recommend_tags(sample_file)

        # All suggestions should meet high threshold
        for suggestion in recommendation.suggestions:
            assert suggestion.confidence >= 80.0

    def test_source_weights(self, recommender):
        """Test that source weights are properly configured."""
        assert 'content' in recommender.source_weights
        assert 'behavior' in recommender.source_weights
        assert 'hybrid' in recommender.source_weights

        # Weights should be reasonable
        for weight in recommender.source_weights.values():
            assert 0 < weight <= 1.0
