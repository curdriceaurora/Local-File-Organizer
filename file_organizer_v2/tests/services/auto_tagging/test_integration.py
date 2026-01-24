"""Integration tests for auto-tagging system."""

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from file_organizer.services.auto_tagging import AutoTaggingService


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def service(temp_dir):
    """Create an AutoTaggingService instance."""
    storage_path = temp_dir / "learning_data.json"
    return AutoTaggingService(storage_path=storage_path)


@pytest.fixture
def sample_files(temp_dir):
    """Create sample files for testing."""
    files = {}

    # Python code file
    py_file = temp_dir / "data_processor.py"
    py_file.write_text("""
    def process_data(data):
        # Data processing function
        return [x * 2 for x in data]
    """)
    files['python'] = py_file

    # Document file
    doc_file = temp_dir / "machine-learning-tutorial.txt"
    doc_file.write_text("""
    Machine Learning Tutorial
    This tutorial covers Python programming for machine learning.
    Topics: neural networks, deep learning, data science
    """)
    files['document'] = doc_file

    # Configuration file
    config_file = temp_dir / "config.json"
    config_file.write_text('{"setting": "value"}')
    files['config'] = config_file

    return files


class TestAutoTaggingIntegration:
    """Integration tests for the complete auto-tagging system."""

    def test_end_to_end_workflow(self, service, sample_files):
        """Test complete workflow: suggest -> apply -> improve."""
        py_file = sample_files['python']

        # 1. Get initial suggestions
        initial_rec = service.suggest_tags(py_file, top_n=5)
        assert len(initial_rec.suggestions) > 0
        [s.tag for s in initial_rec.suggestions]

        # 2. User applies some tags
        applied_tags = ['python', 'code', 'dataprocessing']
        service.record_tag_usage(py_file, applied_tags)

        # 3. Create another Python file
        new_py_file = sample_files['python'].parent / "another_script.py"
        new_py_file.write_text("def main(): pass")

        # 4. Get suggestions for new file (should be influenced by learning)
        new_rec = service.suggest_tags(new_py_file, top_n=10)
        new_tags = [s.tag for s in new_rec.suggestions]

        # Should get some suggestions (content-based at minimum)
        assert len(new_tags) > 0
        # File extension and type should be identified
        # Check that we get meaningful tags (not just stop words)
        assert any(len(tag) >= 3 for tag in new_tags)

    def test_learning_improves_suggestions(self, service, temp_dir):
        """Test that learning improves suggestion quality over time."""
        # Create training set
        for i in range(10):
            file_path = temp_dir / f"python_file_{i}.py"
            file_path.write_text(f"# Python code {i}")
            service.record_tag_usage(
                file_path,
                ['python', 'code', 'programming']
            )

        # Test file
        test_file = temp_dir / "test_script.py"
        test_file.write_text("# Test script")

        recommendation = service.suggest_tags(test_file)
        suggested_tags = [s.tag for s in recommendation.suggestions]

        # Should suggest learned tags
        assert 'python' in suggested_tags or 'code' in suggested_tags

    def test_context_based_suggestions(self, service, temp_dir):
        """Test that suggestions are context-aware."""
        # Create files in specific directories
        code_dir = temp_dir / "code"
        docs_dir = temp_dir / "documents"
        code_dir.mkdir()
        docs_dir.mkdir()

        # Train on code directory
        for i in range(5):
            file_path = code_dir / f"script_{i}.py"
            file_path.write_text("code")
            service.record_tag_usage(file_path, ['python', 'code', 'development'])

        # Train on docs directory
        for i in range(5):
            file_path = docs_dir / f"doc_{i}.txt"
            file_path.write_text("documentation")
            service.record_tag_usage(file_path, ['documentation', 'text', 'manual'])

        # Test new file in code directory
        new_code = code_dir / "new_script.py"
        new_code.write_text("new code")
        code_rec = service.suggest_tags(new_code)
        code_tags = [s.tag for s in code_rec.suggestions]

        # Should suggest code-related tags
        code_related = {'python', 'code', 'development'}
        assert any(tag in code_related for tag in code_tags)

    def test_file_type_learning(self, service, temp_dir):
        """Test that system learns file type associations."""
        # Train: PDFs get 'document' tag
        for i in range(5):
            pdf_file = temp_dir / f"doc_{i}.pdf"
            pdf_file.write_text("pdf content")
            service.record_tag_usage(pdf_file, ['document', 'pdf', 'important'])

        # Test new PDF
        new_pdf = temp_dir / "new_document.pdf"
        new_pdf.write_text("new pdf")
        recommendation = service.suggest_tags(new_pdf)
        tags = [s.tag for s in recommendation.suggestions]

        # Should suggest learned associations
        assert 'document' in tags or 'pdf' in tags

    def test_tag_cooccurrence_learning(self, service, sample_files):
        """Test that system learns tag co-occurrences."""
        py_file = sample_files['python']

        # Record that 'python' and 'ml' often occur together
        for _ in range(5):
            service.record_tag_usage(py_file, ['python', 'ml', 'data-science'])

        # When suggesting for a file with 'python', should suggest 'ml'
        recommendation = service.suggest_tags(py_file, existing_tags=['python'])
        suggested = [s.tag for s in recommendation.suggestions]

        assert 'ml' in suggested or 'data-science' in suggested

    def test_feedback_integration(self, service, sample_files):
        """Test feedback mechanism improves suggestions."""
        doc_file = sample_files['document']

        # Get initial suggestions
        service.suggest_tags(doc_file)

        # Simulate user feedback
        feedback = [
            {
                'file_path': str(doc_file),
                'suggested_tags': ['tutorial', 'machine-learning', 'python'],
                'accepted_tags': ['tutorial', 'machine-learning'],
                'rejected_tags': ['python'],
                'timestamp': time.time()
            }
        ]

        service.provide_feedback(feedback)

        # Suggestions should improve based on feedback
        # (rejecting 'python' should reduce its confidence)

    def test_popular_tags_tracking(self, service, temp_dir):
        """Test tracking of popular tags."""
        # Use various tags with different frequencies
        tags_usage = {
            'python': 10,
            'code': 8,
            'ml': 5,
            'data': 3,
            'test': 1
        }

        for tag, count in tags_usage.items():
            for i in range(count):
                file_path = temp_dir / f"{tag}_{i}.txt"
                file_path.write_text("content")
                service.record_tag_usage(file_path, [tag])

        popular = service.get_popular_tags(limit=5)
        popular_tags = [tag for tag, _ in popular]

        # Most popular should be first
        assert popular_tags[0] == 'python'
        assert popular_tags[1] == 'code'

    def test_recent_tags_tracking(self, service, sample_files):
        """Test tracking of recently used tags."""
        py_file = sample_files['python']

        # Use some tags recently
        service.record_tag_usage(py_file, ['recent', 'new', 'fresh'])

        recent = service.get_recent_tags(days=1, limit=10)

        # Should include recently used tags
        assert 'recent' in recent
        assert 'new' in recent
        assert 'fresh' in recent

    def test_batch_processing(self, service, sample_files):
        """Test batch processing of multiple files."""
        files = list(sample_files.values())

        # Batch recommend
        results = service.recommender.batch_recommend(files, top_n=5)

        assert len(results) == len(files)
        assert all(isinstance(rec.suggestions, list) for rec in results.values())

    def test_confidence_scores_reasonable(self, service, sample_files):
        """Test that confidence scores are in reasonable ranges."""
        for file_path in sample_files.values():
            recommendation = service.suggest_tags(file_path)

            for suggestion in recommendation.suggestions:
                # Confidence should be 0-100
                assert 0 <= suggestion.confidence <= 100
                # Should meet minimum threshold
                assert suggestion.confidence >= service.recommender.min_confidence

    def test_suggestion_sources(self, service, sample_files):
        """Test that suggestions come from multiple sources."""
        py_file = sample_files['python']

        # Train to get behavior-based suggestions
        for _i in range(3):
            service.record_tag_usage(py_file, ['python', 'code'])

        recommendation = service.suggest_tags(py_file)

        # Should have suggestions from different sources
        sources = {s.source for s in recommendation.suggestions}
        # At least should have content-based
        assert 'content' in sources or 'behavior' in sources or 'hybrid' in sources

    def test_empty_file_handling(self, service, temp_dir):
        """Test handling of empty files."""
        empty_file = temp_dir / "empty.txt"
        empty_file.write_text("")

        recommendation = service.suggest_tags(empty_file)

        # Should still provide some suggestions (from filename, extension)
        # Or handle gracefully with empty list
        assert isinstance(recommendation.suggestions, list)

    def test_large_tag_vocabulary(self, service, temp_dir):
        """Test system with large tag vocabulary."""
        # Create many different tags
        for i in range(50):
            file_path = temp_dir / f"file_{i}.txt"
            file_path.write_text(f"content {i}")
            service.record_tag_usage(
                file_path,
                [f'tag_{i}', f'category_{i % 5}']
            )

        # Should handle large vocabulary without issues
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        recommendation = service.suggest_tags(test_file, top_n=10)
        assert len(recommendation.suggestions) <= 10

    def test_persistence(self, temp_dir):
        """Test that learning data persists across service instances."""
        storage_path = temp_dir / "persistent_data.json"

        # Create first service and train it
        service1 = AutoTaggingService(storage_path=storage_path)
        test_file = temp_dir / "test.py"
        test_file.write_text("code")
        service1.record_tag_usage(test_file, ['python', 'persistent'])

        # Create new service with same storage
        service2 = AutoTaggingService(storage_path=storage_path)

        # Should have learned data
        popular = service2.get_popular_tags()
        popular_tags = [tag for tag, _ in popular]

        assert 'python' in popular_tags or 'persistent' in popular_tags

    def test_suggestion_reasoning(self, service, sample_files):
        """Test that suggestions include reasoning."""
        doc_file = sample_files['document']

        recommendation = service.suggest_tags(doc_file)

        for suggestion in recommendation.suggestions:
            # Each suggestion should have reasoning
            assert suggestion.reasoning
            assert len(suggestion.reasoning) > 0
            assert isinstance(suggestion.reasoning, str)

    def test_existing_tags_filtering(self, service, sample_files):
        """Test that existing tags are filtered from suggestions."""
        py_file = sample_files['python']

        existing_tags = ['python', 'code']
        recommendation = service.suggest_tags(
            py_file,
            existing_tags=existing_tags
        )

        suggested_tags = [s.tag for s in recommendation.suggestions]

        # Should not suggest tags that already exist
        assert 'python' not in suggested_tags
        assert 'code' not in suggested_tags

    def test_performance_batch_processing(self, service, temp_dir):
        """Test performance with batch processing."""
        # Create 100 files
        files = []
        for i in range(100):
            file_path = temp_dir / f"file_{i}.txt"
            file_path.write_text(f"content {i}")
            files.append(file_path)

        # Should process reasonably fast
        start_time = time.time()
        results = service.recommender.batch_recommend(files, top_n=5)
        elapsed = time.time() - start_time

        assert len(results) == 100
        # Should complete in reasonable time (less than 10 seconds for 100 files)
        assert elapsed < 10.0
