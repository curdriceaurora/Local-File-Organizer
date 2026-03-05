"""Tests for SDK testing utilities: PluginTestCase helpers."""

from __future__ import annotations

import pytest

from file_organizer.plugins.sdk.testing import PluginTestCase

pytestmark = pytest.mark.unit


@pytest.fixture
def tc() -> PluginTestCase:
    """Provide a PluginTestCase with automatic setUp/tearDown."""
    instance = PluginTestCase()
    instance.setUp()
    yield instance
    instance.tearDown()


# ---------------------------------------------------------------------------
# PluginTestCase lifecycle
# ---------------------------------------------------------------------------


class TestPluginTestCaseLifecycle:
    """Test that setUp/tearDown create and clean up a temporary directory."""

    def test_setup_creates_test_dir(self, tc) -> None:
        assert tc.test_dir.exists()
        assert tc.test_dir.is_dir()

    def test_teardown_removes_test_dir(self) -> None:
        instance = PluginTestCase()
        instance.setUp()
        test_dir = instance.test_dir
        instance.tearDown()
        assert not test_dir.exists()

    def test_test_dir_prefix(self, tc) -> None:
        assert "fo-plugin-test-" in tc.test_dir.name


# ---------------------------------------------------------------------------
# create_test_file
# ---------------------------------------------------------------------------


class TestCreateTestFile:
    """Tests for PluginTestCase.create_test_file helper."""

    def test_creates_file_with_content(self, tc) -> None:
        path = tc.create_test_file("hello.txt", "hello world")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello world"
        assert path.parent == tc.test_dir

    def test_creates_nested_directories(self, tc) -> None:
        path = tc.create_test_file("sub/dir/file.txt", "nested")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "nested"

    def test_creates_empty_file_by_default(self, tc) -> None:
        path = tc.create_test_file("empty.txt")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == ""

    def test_returns_absolute_path(self, tc) -> None:
        path = tc.create_test_file("file.txt")
        assert path.is_absolute()


# ---------------------------------------------------------------------------
# assert_file_exists / assert_file_not_exists
# ---------------------------------------------------------------------------


class TestFileAssertions:
    """Tests for assert_file_exists and assert_file_not_exists."""

    def test_assert_file_exists_passes(self, tc) -> None:
        path = tc.create_test_file("exists.txt")
        tc.assert_file_exists(path)  # Should not raise

    def test_assert_file_exists_fails(self, tc) -> None:
        fake_path = tc.test_dir / "nonexistent.txt"
        with pytest.raises(AssertionError, match="Expected file to exist"):
            tc.assert_file_exists(fake_path)

    def test_assert_file_not_exists_passes(self, tc) -> None:
        fake_path = tc.test_dir / "nonexistent.txt"
        tc.assert_file_not_exists(fake_path)  # Should not raise

    def test_assert_file_not_exists_fails(self, tc) -> None:
        path = tc.create_test_file("exists.txt")
        with pytest.raises(AssertionError, match="Expected file to be absent"):
            tc.assert_file_not_exists(path)


# ---------------------------------------------------------------------------
# Integration: using PluginTestCase as a unittest base
# ---------------------------------------------------------------------------


class TestPluginTestCaseAsBase(PluginTestCase):
    """Verify PluginTestCase works when used as a unittest base class via pytest."""

    def test_test_dir_available(self) -> None:
        """self.test_dir should be available when inheriting from PluginTestCase."""
        assert self.test_dir.exists()

    def test_create_and_assert(self) -> None:
        path = self.create_test_file("integration.txt", "data")
        self.assert_file_exists(path)
        assert path.read_text(encoding="utf-8") == "data"
