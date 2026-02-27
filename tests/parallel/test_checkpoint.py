"""
Unit tests for CheckpointManager.

Tests checkpoint creation, loading, updating, hash verification,
and file change detection.
"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.parallel.checkpoint import (
    CheckpointManager,
    compute_file_hash,
)
from file_organizer.parallel.models import Checkpoint


@pytest.mark.unit
class TestComputeFileHash(unittest.TestCase):
    """Test the compute_file_hash utility function."""

    def setUp(self) -> None:
        """Set up temp directory."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_hash_known_content(self) -> None:
        """Test hash matches expected SHA-256 digest."""
        f = self.tmp_path / "hello.txt"
        content = b"hello world"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(compute_file_hash(f), expected)

    def test_hash_empty_file(self) -> None:
        """Test hash of an empty file."""
        f = self.tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        self.assertEqual(compute_file_hash(f), expected)

    def test_hash_nonexistent_raises(self) -> None:
        """Test that hashing a missing file raises OSError."""
        with self.assertRaises(OSError):
            compute_file_hash(self.tmp_path / "nonexistent.txt")

    def test_hash_binary_file(self) -> None:
        """Test hash of binary content."""
        f = self.tmp_path / "binary.bin"
        content = bytes(range(256))
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(compute_file_hash(f), expected)


@pytest.mark.unit
class TestCheckpointManagerInit(unittest.TestCase):
    """Test CheckpointManager initialization."""

    def test_default_dir(self) -> None:
        """Test that default directory is under home."""
        mgr = CheckpointManager()
        self.assertEqual(
            mgr.checkpoints_dir,
            Path.home() / ".file-organizer" / "checkpoints",
        )

    def test_custom_dir(self) -> None:
        """Test that custom directory is used."""
        custom = Path("/tmp/test-checkpoints")
        mgr = CheckpointManager(checkpoints_dir=custom)
        self.assertEqual(mgr.checkpoints_dir, custom)


@pytest.mark.unit
class TestCreateCheckpoint(unittest.TestCase):
    """Test checkpoint creation."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_create_saves_file(self) -> None:
        """Test that creating a checkpoint saves a JSON file."""
        f1 = self.tmp_path / "a.txt"
        f2 = self.tmp_path / "b.txt"
        f1.write_text("aaa", encoding="utf-8")
        f2.write_text("bbb", encoding="utf-8")

        ckpt = self.mgr.create_checkpoint(
            job_id="ckpt-1",
            completed_files=[f1],
            pending_files=[f2],
        )
        self.assertEqual(ckpt.job_id, "ckpt-1")
        self.assertEqual(len(ckpt.completed_paths), 1)
        self.assertEqual(len(ckpt.pending_paths), 1)
        self.assertTrue((self.ckpt_dir / "ckpt-1.checkpoint.json").exists())

    def test_create_computes_hashes(self) -> None:
        """Test that file hashes are computed for all files."""
        f1 = self.tmp_path / "x.txt"
        f2 = self.tmp_path / "y.txt"
        f1.write_text("xxx", encoding="utf-8")
        f2.write_text("yyy", encoding="utf-8")

        ckpt = self.mgr.create_checkpoint(
            job_id="hash-test",
            completed_files=[f1],
            pending_files=[f2],
        )
        self.assertIn(str(f1), ckpt.file_hashes)
        self.assertIn(str(f2), ckpt.file_hashes)
        self.assertEqual(
            ckpt.file_hashes[str(f1)],
            compute_file_hash(f1),
        )

    def test_create_handles_nonexistent_files(self) -> None:
        """Test that nonexistent files are skipped during hashing."""
        missing = self.tmp_path / "ghost.txt"
        ckpt = self.mgr.create_checkpoint(
            job_id="missing-files",
            completed_files=[],
            pending_files=[missing],
        )
        self.assertNotIn(str(missing), ckpt.file_hashes)
        self.assertEqual(len(ckpt.pending_paths), 1)


@pytest.mark.unit
class TestLoadCheckpoint(unittest.TestCase):
    """Test checkpoint loading."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_roundtrip(self) -> None:
        """Test that checkpoint can be saved and loaded."""
        f1 = self.tmp_path / "data.txt"
        f1.write_text("data", encoding="utf-8")

        self.mgr.create_checkpoint(
            job_id="load-test",
            completed_files=[f1],
            pending_files=[],
        )
        loaded = self.mgr.load_checkpoint("load-test")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.job_id, "load-test")
        self.assertEqual(len(loaded.completed_paths), 1)
        self.assertEqual(loaded.completed_paths[0], f1)

    def test_load_nonexistent_returns_none(self) -> None:
        """Test loading a missing checkpoint returns None."""
        self.assertIsNone(self.mgr.load_checkpoint("no-such-job"))

    def test_load_corrupted_returns_none(self) -> None:
        """Test loading a corrupted checkpoint file returns None."""
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        path = self.ckpt_dir / "bad.checkpoint.json"
        path.write_text("corrupted data!!!", encoding="utf-8")
        self.assertIsNone(self.mgr.load_checkpoint("bad"))


@pytest.mark.unit
class TestUpdateCheckpoint(unittest.TestCase):
    """Test checkpoint updates."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_update_moves_file_to_completed(self) -> None:
        """Test that updating moves a file from pending to completed."""
        f1 = self.tmp_path / "a.txt"
        f2 = self.tmp_path / "b.txt"
        f1.write_text("aaa", encoding="utf-8")
        f2.write_text("bbb", encoding="utf-8")

        self.mgr.create_checkpoint(
            job_id="update-test",
            completed_files=[],
            pending_files=[f1, f2],
        )

        updated = self.mgr.update_checkpoint("update-test", f1)
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertIn(f1, updated.completed_paths)
        self.assertNotIn(f1, updated.pending_paths)
        self.assertIn(f2, updated.pending_paths)

    def test_update_nonexistent_checkpoint_returns_none(self) -> None:
        """Test updating a missing checkpoint returns None."""
        result = self.mgr.update_checkpoint("no-checkpoint", Path("/tmp/x.txt"))
        self.assertIsNone(result)

    def test_update_does_not_duplicate_completed(self) -> None:
        """Test updating with already-completed file does not duplicate."""
        f1 = self.tmp_path / "dup.txt"
        f1.write_text("dup", encoding="utf-8")

        self.mgr.create_checkpoint(
            job_id="no-dup",
            completed_files=[f1],
            pending_files=[],
        )
        updated = self.mgr.update_checkpoint("no-dup", f1)
        assert updated is not None
        count = updated.completed_paths.count(f1)
        self.assertEqual(count, 1)


@pytest.mark.unit
class TestCheckpointAtomicWrites(unittest.TestCase):
    """Test atomic write behavior for checkpoint persistence."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_checkpoint_uses_temp_file_then_replace(self) -> None:
        """Test save_checkpoint writes temp file before replacing target."""
        f1 = self.tmp_path / "a.txt"
        f1.write_text("a", encoding="utf-8")
        ckpt = self.mgr.create_checkpoint("atomic-1", [f1], [])

        checkpoint_path = self.ckpt_dir / "atomic-1.checkpoint.json"
        original_replace = Path.replace
        saw_temp_file_before_replace = False

        def wrapped_replace(path_self: Path, target: Path) -> Path:
            nonlocal saw_temp_file_before_replace
            if path_self.suffix == ".tmp":
                saw_temp_file_before_replace = path_self.exists()
            return original_replace(path_self, target)

        with patch.object(Path, "replace", autospec=True, side_effect=wrapped_replace):
            self.mgr.save_checkpoint(ckpt)

        self.assertTrue(saw_temp_file_before_replace)
        self.assertTrue(checkpoint_path.exists())
        self.assertFalse(checkpoint_path.with_suffix(".tmp").exists())

    def test_save_checkpoint_failure_keeps_existing_file(self) -> None:
        """Test failed temp write does not corrupt existing checkpoint file."""
        f1 = self.tmp_path / "a.txt"
        f2 = self.tmp_path / "b.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")
        ckpt = self.mgr.create_checkpoint("atomic-2", [f1], [f2])

        checkpoint_path = self.ckpt_dir / "atomic-2.checkpoint.json"
        original_contents = checkpoint_path.read_text(encoding="utf-8")
        original_write_text = Path.write_text

        def failing_temp_write(path_self: Path, data: str, encoding: str = "utf-8") -> int:
            if path_self.suffix == ".tmp":
                raise OSError("simulated write failure")
            return original_write_text(path_self, data, encoding=encoding)

        ckpt.completed_paths.append(f2)
        ckpt.pending_paths = []

        with patch.object(Path, "write_text", autospec=True, side_effect=failing_temp_write):
            with self.assertRaises(OSError):
                self.mgr.save_checkpoint(ckpt)

        self.assertEqual(
            checkpoint_path.read_text(encoding="utf-8"),
            original_contents,
            "Existing checkpoint file should remain intact on failed save",
        )
        self.assertFalse(checkpoint_path.with_suffix(".tmp").exists())


@pytest.mark.unit
class TestDeleteCheckpoint(unittest.TestCase):
    """Test checkpoint deletion."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_delete_existing(self) -> None:
        """Test deleting an existing checkpoint returns True."""
        f = self.tmp_path / "x.txt"
        f.write_text("x", encoding="utf-8")
        self.mgr.create_checkpoint("del-test", [f], [])
        self.assertTrue(self.mgr.delete_checkpoint("del-test"))

    def test_delete_nonexistent(self) -> None:
        """Test deleting nonexistent checkpoint returns False."""
        self.assertFalse(self.mgr.delete_checkpoint("nope"))


@pytest.mark.unit
class TestHasFileChanged(unittest.TestCase):
    """Test file change detection."""

    def setUp(self) -> None:
        """Set up temp directory and manager."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmpdir)
        self.ckpt_dir = self.tmp_path / "checkpoints"
        self.mgr = CheckpointManager(checkpoints_dir=self.ckpt_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_unchanged_file_returns_false(self) -> None:
        """Test that an unchanged file is detected as not changed."""
        f = self.tmp_path / "stable.txt"
        f.write_text("stable content", encoding="utf-8")

        ckpt = self.mgr.create_checkpoint("change-test", [f], [])
        self.assertFalse(self.mgr.has_file_changed(ckpt, f))

    def test_modified_file_returns_true(self) -> None:
        """Test that a modified file is detected as changed."""
        f = self.tmp_path / "mutable.txt"
        f.write_text("original", encoding="utf-8")

        ckpt = self.mgr.create_checkpoint("mod-test", [f], [])
        f.write_text("modified!", encoding="utf-8")
        self.assertTrue(self.mgr.has_file_changed(ckpt, f))

    def test_missing_hash_returns_true(self) -> None:
        """Test that a file with no stored hash is considered changed."""
        f = self.tmp_path / "new.txt"
        f.write_text("new", encoding="utf-8")

        ckpt = Checkpoint(job_id="no-hash", file_hashes={})
        self.assertTrue(self.mgr.has_file_changed(ckpt, f))

    def test_deleted_file_returns_true(self) -> None:
        """Test that a deleted file is considered changed."""
        f = self.tmp_path / "gone.txt"
        f.write_text("gone soon", encoding="utf-8")

        ckpt = self.mgr.create_checkpoint("del-file-test", [f], [])
        f.unlink()
        self.assertTrue(self.mgr.has_file_changed(ckpt, f))


if __name__ == "__main__":
    unittest.main()
