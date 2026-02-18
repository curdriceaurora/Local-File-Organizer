"""
Unit tests for the TaskScheduler.

Tests file ordering strategies including size-based sorting,
type grouping, and custom priority functions.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from file_organizer.parallel.scheduler import PriorityStrategy, TaskScheduler


class TestTaskScheduler(unittest.TestCase):
    """Test cases for TaskScheduler."""

    def setUp(self) -> None:
        """Set up test fixtures with temporary files of varying sizes."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.scheduler = TaskScheduler()

        # Create files with known sizes
        self.small_file = self.test_dir / "small.txt"
        self.small_file.write_text("a")  # 1 byte

        self.medium_file = self.test_dir / "medium.dat"
        self.medium_file.write_text("a" * 100)  # 100 bytes

        self.large_file = self.test_dir / "large.bin"
        self.large_file.write_text("a" * 1000)  # 1000 bytes

        self.py_file = self.test_dir / "script.py"
        self.py_file.write_text("print('hello')")

        self.js_file = self.test_dir / "app.js"
        self.js_file.write_text("console.log('hi')")

        self.another_py = self.test_dir / "utils.py"
        self.another_py.write_text("pass")

    def tearDown(self) -> None:
        """Clean up temporary files."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_empty_list(self) -> None:
        """Test scheduling an empty file list."""
        result = self.scheduler.schedule([])
        self.assertEqual(result, [])

    def test_size_asc_default(self) -> None:
        """Test default strategy sorts small files first."""
        files = [self.large_file, self.small_file, self.medium_file]
        result = self.scheduler.schedule(files)
        sizes = [f.stat().st_size for f in result]
        self.assertEqual(sizes, sorted(sizes))

    def test_size_asc_explicit(self) -> None:
        """Test explicit SIZE_ASC sorts smallest first."""
        files = [self.large_file, self.medium_file, self.small_file]
        result = self.scheduler.schedule(files, strategy=PriorityStrategy.SIZE_ASC)
        self.assertEqual(result[0], self.small_file)
        self.assertEqual(result[-1], self.large_file)

    def test_size_desc(self) -> None:
        """Test SIZE_DESC sorts largest first."""
        files = [self.small_file, self.medium_file, self.large_file]
        result = self.scheduler.schedule(files, strategy=PriorityStrategy.SIZE_DESC)
        self.assertEqual(result[0], self.large_file)
        self.assertEqual(result[-1], self.small_file)

    def test_type_grouped(self) -> None:
        """Test TYPE_GROUPED groups files by extension."""
        files = [
            self.py_file,
            self.js_file,
            self.another_py,
            self.small_file,
        ]
        result = self.scheduler.schedule(files, strategy=PriorityStrategy.TYPE_GROUPED)
        # Files should be grouped: .js, .py, .txt
        extensions = [f.suffix for f in result]
        # Check that same extensions are adjacent
        seen: set[str] = set()
        current_ext = None
        for ext in extensions:
            if ext != current_ext:
                self.assertNotIn(
                    ext,
                    seen,
                    f"Extension {ext} appeared in a non-contiguous group",
                )
                current_ext = ext
            seen.add(ext)

    def test_type_grouped_sorts_within_group(self) -> None:
        """Test TYPE_GROUPED sorts files by name within each group."""
        files = [self.another_py, self.py_file]  # utils.py, script.py
        result = self.scheduler.schedule(files, strategy=PriorityStrategy.TYPE_GROUPED)
        # Both .py files, should be sorted by name
        self.assertEqual(result[0], self.py_file)  # script.py
        self.assertEqual(result[1], self.another_py)  # utils.py

    def test_custom_strategy(self) -> None:
        """Test CUSTOM strategy with a user-provided function."""
        files = [self.large_file, self.small_file, self.medium_file]
        # Custom: sort by filename length
        result = self.scheduler.schedule(
            files,
            strategy=PriorityStrategy.CUSTOM,
            priority_fn=lambda p: len(p.name),
        )
        name_lengths = [len(f.name) for f in result]
        self.assertEqual(name_lengths, sorted(name_lengths))

    def test_custom_strategy_requires_fn(self) -> None:
        """Test CUSTOM strategy raises ValueError without priority_fn."""
        with self.assertRaises(ValueError) as ctx:
            self.scheduler.schedule(
                [self.small_file],
                strategy=PriorityStrategy.CUSTOM,
            )
        self.assertIn("priority_fn is required", str(ctx.exception))

    def test_nonexistent_files_sort_first_asc(self) -> None:
        """Test that non-existent files get size 0 and sort first ascending."""
        missing = Path(self.test_dir / "missing.txt")
        files = [self.large_file, missing, self.small_file]
        result = self.scheduler.schedule(files, strategy=PriorityStrategy.SIZE_ASC)
        self.assertEqual(result[0], missing)

    def test_single_file(self) -> None:
        """Test scheduling a single file returns it unchanged."""
        result = self.scheduler.schedule([self.small_file])
        self.assertEqual(result, [self.small_file])

    def test_returns_new_list(self) -> None:
        """Test that schedule returns a new list, not the original."""
        original = [self.small_file, self.large_file]
        result = self.scheduler.schedule(original)
        self.assertIsNot(result, original)

    def test_priority_strategy_enum_values(self) -> None:
        """Test PriorityStrategy enum string values."""
        self.assertEqual(PriorityStrategy.SIZE_ASC, "size_asc")
        self.assertEqual(PriorityStrategy.SIZE_DESC, "size_desc")
        self.assertEqual(PriorityStrategy.TYPE_GROUPED, "type_grouped")
        self.assertEqual(PriorityStrategy.CUSTOM, "custom")


if __name__ == "__main__":
    unittest.main()
