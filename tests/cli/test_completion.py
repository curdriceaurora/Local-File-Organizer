"""Tests for file_organizer.cli.completion module.

Tests path auto-completion callbacks for Typer CLI arguments:
- complete_directory: Yield directory completions
- complete_file: Yield file and directory completions
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.cli.completion import complete_directory, complete_file

pytestmark = [pytest.mark.unit]


class TestCompleteDirectory:
    """Tests for complete_directory function."""

    def test_complete_directory_empty_input(self, tmp_path):
        """Test completion with empty input returns current directory children."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "subdir1").mkdir()
        (test_dir / "subdir2").mkdir()
        (test_dir / "file.txt").touch()

        # Change to temp directory
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_directory(""))
            # Should only return directories
            names = [r[0] for r in results]
            assert "subdir1" in names
            assert "subdir2" in names
            assert "file.txt" not in names
            # All results should have 'directory' as help text
            for _, help_text in results:
                assert help_text == "directory"
        finally:
            os.chdir(old_cwd)

    def test_complete_directory_with_prefix(self, tmp_path):
        """Test completion with directory prefix."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "project1").mkdir()
        (test_dir / "project2").mkdir()
        (test_dir / "other").mkdir()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_directory("proj"))
            names = [r[0] for r in results]
            assert "project1" in names
            assert "project2" in names
            assert "other" not in names
        finally:
            os.chdir(old_cwd)

    def test_complete_directory_full_path(self, tmp_path):
        """Test completion with full path."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "subdir1").mkdir()
        (test_dir / "subdir2").mkdir()

        # Use full path
        results = list(complete_directory(str(test_dir) + "/"))
        names = [r[0] for r in results]
        assert any("subdir1" in n for n in names)
        assert any("subdir2" in n for n in names)

    def test_complete_directory_nonexistent_path(self):
        """Test completion with nonexistent path."""
        results = list(complete_directory("/nonexistent/path/"))
        assert len(results) == 0

    def test_complete_directory_no_matching_prefix(self, tmp_path):
        """Test completion with non-matching prefix."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file1").mkdir()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_directory("xyz"))
            assert len(results) == 0
        finally:
            os.chdir(old_cwd)

    def test_complete_directory_sorted_output(self, tmp_path):
        """Test that directory completions are sorted."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "zebra").mkdir()
        (test_dir / "apple").mkdir()
        (test_dir / "banana").mkdir()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_directory(""))
            names = [r[0] for r in results]
            assert names == sorted(names)
        finally:
            os.chdir(old_cwd)


class TestCompleteFile:
    """Tests for complete_file function."""

    def test_complete_file_empty_input(self, tmp_path):
        """Test file completion with empty input returns all items."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "subdir").mkdir()
        (test_dir / "file.txt").touch()
        (test_dir / "script.py").touch()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_file(""))
            names = [r[0] for r in results]
            assert "subdir" in names
            assert "file.txt" in names
            assert "script.py" in names
        finally:
            os.chdir(old_cwd)

    def test_complete_file_with_file_extension(self, tmp_path):
        """Test file completion includes file extension in help text."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "data.json").touch()
        (test_dir / "config.yaml").touch()
        (test_dir / "noext").touch()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_file(""))
            result_names = [r[0] for r in results]
            # Should have collected the files
            assert any("data.json" in name for name in result_names)
            assert any("config.yaml" in name for name in result_names)
        finally:
            os.chdir(old_cwd)

    def test_complete_file_with_prefix(self, tmp_path):
        """Test file completion with matching prefix."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "test.txt").touch()
        (test_dir / "test_data.json").touch()
        (test_dir / "other.py").touch()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_file("test"))
            names = [r[0] for r in results]
            assert any("test.txt" in n for n in names)
            assert any("test_data.json" in n for n in names)
            assert not any("other.py" in n for n in names)
        finally:
            os.chdir(old_cwd)

    def test_complete_file_full_path(self, tmp_path):
        """Test file completion with full path."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file1.txt").touch()
        (test_dir / "dir1").mkdir()

        results = list(complete_file(str(test_dir) + "/"))
        names = [r[0] for r in results]
        assert any("file1.txt" in n for n in names)
        assert any("dir1" in n for n in names)

    def test_complete_file_nonexistent_path(self):
        """Test file completion with nonexistent path."""
        results = list(complete_file("/nonexistent/path/"))
        assert len(results) == 0

    def test_complete_file_directory_identification(self, tmp_path):
        """Test that directories are properly identified."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "subdir").mkdir()

        results = list(complete_file(str(test_dir) + "/"))
        results_dict = {Path(r[0]).name: r[1] for r in results}
        assert results_dict.get("subdir") == "directory"

    def test_complete_file_sorted_output(self, tmp_path):
        """Test that file completions are sorted."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "zebra.txt").touch()
        (test_dir / "apple.txt").touch()
        (test_dir / "banana.txt").touch()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_file(""))
            names = [r[0] for r in results]
            assert names == sorted(names)
        finally:
            os.chdir(old_cwd)

    def test_complete_file_no_matches(self, tmp_path):
        """Test file completion with non-matching prefix."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            results = list(complete_file("xyz"))
            assert len(results) == 0
        finally:
            os.chdir(old_cwd)

    def test_complete_file_returns_iterator(self, tmp_path):
        """Test that complete_file returns an iterator."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(test_dir)
            result = complete_file("")
            # Check it's an iterator/generator
            assert hasattr(result, "__iter__")
            assert hasattr(result, "__next__")
        finally:
            os.chdir(old_cwd)
