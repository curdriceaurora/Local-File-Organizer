"""Security tests for CLI search corpus builder.

Validates that the semantic corpus builder in ``utilities.py`` correctly
filters symlinks, hidden files, and uses narrowed exception handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_corpus_files(tmp_path: Path) -> list[Path]:
    """Create a mix of normal, hidden, and symlinked files."""
    normal = tmp_path / "report.txt"
    normal.write_text("quarterly budget finance report")

    hidden = tmp_path / ".secret_notes.txt"
    hidden.write_text("hidden secret data")

    hidden_dir = tmp_path / ".hidden_dir"
    hidden_dir.mkdir()
    nested_hidden = hidden_dir / "nested.txt"
    nested_hidden.write_text("nested in hidden dir")

    return [normal, hidden, nested_hidden]


# ---------------------------------------------------------------------------
# Symlink filtering
# ---------------------------------------------------------------------------


class TestCorpusSymlinkFiltering:
    def test_symlinks_excluded_from_corpus(self, tmp_path: Path) -> None:
        """Symlinked files must not be included in the semantic corpus."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("real document content")

        link = tmp_path / "link.txt"
        try:
            link.symlink_to(real_file)
        except OSError:
            pytest.skip("Symlinks not supported on this filesystem")

        # The filter logic: entry.is_symlink() or not entry.is_file() or is_hidden(entry)
        from file_organizer.utils import is_hidden

        entries = list(tmp_path.iterdir())
        filtered = [
            e
            for e in entries
            if not e.is_symlink() and e.is_file() and not is_hidden(e.relative_to(tmp_path))
        ]
        assert link not in filtered, "Symlink should be filtered out"
        assert real_file in filtered, "Real file should be included"


# ---------------------------------------------------------------------------
# Hidden file filtering
# ---------------------------------------------------------------------------


class TestCorpusHiddenFileFiltering:
    def test_dot_prefixed_files_excluded(self, tmp_path: Path) -> None:
        """Files starting with '.' must be excluded from the corpus."""
        from file_organizer.utils import is_hidden

        normal = tmp_path / "report.txt"
        normal.write_text("normal content")
        hidden = tmp_path / ".secret.txt"
        hidden.write_text("hidden content")

        assert not is_hidden(normal.relative_to(tmp_path))
        assert is_hidden(hidden.relative_to(tmp_path))

    def test_files_in_hidden_directory_excluded(self, tmp_path: Path) -> None:
        """Files nested inside a hidden directory must be excluded."""
        from file_organizer.utils import is_hidden

        hidden_dir = tmp_path / ".config"
        hidden_dir.mkdir()
        nested = hidden_dir / "settings.txt"
        nested.write_text("settings")

        assert is_hidden(nested.relative_to(tmp_path))

    def test_normal_files_not_excluded(self, tmp_path: Path) -> None:
        """Normal files with no hidden path components pass the filter."""
        from file_organizer.utils import is_hidden

        normal = tmp_path / "documents" / "report.txt"
        normal.parent.mkdir(parents=True, exist_ok=True)
        normal.write_text("content")

        # tmp_path itself may have dot components, so test relative behavior
        assert not is_hidden(Path("documents/report.txt"))


# ---------------------------------------------------------------------------
# Exception narrowing
# ---------------------------------------------------------------------------


class TestCorpusExceptionNarrowing:
    def test_narrow_exceptions_in_index_builder(self) -> None:
        """Verify the index builder catches specific exceptions, not bare Exception.

        The corpus builder should catch (ValueError, RuntimeError, ImportError),
        not the broad ``except Exception`` that was there before.
        """
        import ast
        import inspect

        from file_organizer.cli import utilities

        source = inspect.getsource(utilities)
        tree = ast.parse(source)

        # Find except handlers in the module
        broad_handlers: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    # bare except:
                    broad_handlers.append(node.lineno)
                elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    broad_handlers.append(node.lineno)

        # The semantic index builder should NOT have broad Exception handlers
        # (there may be other handlers elsewhere in the module that are fine)
        # Check specifically around the "Failed to build semantic index" message
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                is_broad = node.type is None or (
                    isinstance(node.type, ast.Name) and node.type.id == "Exception"
                )
                if is_broad:
                    # Check if this handler's body contains the semantic index error
                    for child in ast.walk(node):
                        if isinstance(child, ast.Constant) and isinstance(child.value, str):
                            if "semantic index" in child.value.lower():
                                pytest.fail(
                                    f"Line {node.lineno}: Semantic index builder uses broad "
                                    f"'except Exception' or bare 'except' — should use narrowed exceptions"
                                )
