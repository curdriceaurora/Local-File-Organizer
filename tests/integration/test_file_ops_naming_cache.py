"""Integration tests for file_ops, naming_analyzer, api/cache, and api/rate_limit.

Covers uncovered branches in:
  - core/file_ops.py           — collect_files, fallback_by_extension, organize_files,
                                  simulate_organization, cleanup_empty_dirs
  - services/intelligence/naming_analyzer.py — naming styles, normalize, semantic components
  - api/cache.py               — InMemoryCache TTL, build_cache_backend invalid URL
  - api/rate_limit.py          — max_entries sweep trigger
  - utils/text_processing.py  — clean_text, sanitize_filename, extract_keywords
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.api.cache import InMemoryCache, _is_valid_redis_url, build_cache_backend
from file_organizer.api.rate_limit import InMemoryRateLimiter
from file_organizer.core.file_ops import (
    cleanup_empty_dirs,
    collect_files,
    fallback_by_extension,
    organize_files,
    simulate_organization,
)
from file_organizer.services import ProcessedFile
from file_organizer.services.intelligence.naming_analyzer import NamingAnalyzer
from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# collect_files
# ---------------------------------------------------------------------------


class TestCollectFilesIsFile:
    def test_single_file_path(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        console = MagicMock()
        result = collect_files(f, console)
        assert result == [f]

    def test_single_file_console_print(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        console = MagicMock()
        collect_files(f, console)
        console.print.assert_called_once()

    def test_directory_skips_hidden_files(self, tmp_path: Path) -> None:
        visible = tmp_path / "visible.txt"
        hidden = tmp_path / ".hidden.txt"
        visible.write_text("v")
        hidden.write_text("h")
        console = MagicMock()
        result = collect_files(tmp_path, console)
        assert visible in result
        assert hidden not in result

    def test_directory_skips_hidden_dirs(self, tmp_path: Path) -> None:
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        nested = hidden_dir / "config"
        nested.write_text("x")
        console = MagicMock()
        result = collect_files(tmp_path, console)
        assert nested not in result

    def test_empty_directory(self, tmp_path: Path) -> None:
        console = MagicMock()
        result = collect_files(tmp_path, console)
        assert result == []


# ---------------------------------------------------------------------------
# fallback_by_extension
# ---------------------------------------------------------------------------


class TestFallbackByExtension:
    def test_audio_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "song.mp3"
        f.write_text("audio")
        results = fallback_by_extension([f])
        assert "Audio" in results[0].folder_name

    def test_video_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "clip.mp4"
        f.write_text("video")
        results = fallback_by_extension([f])
        assert "Video" in results[0].folder_name or "Videos" in results[0].folder_name

    def test_other_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xyz"
        f.write_text("data")
        results = fallback_by_extension([f])
        assert results[0].folder_name == "Other"

    def test_image_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.jpg"
        f.write_text("img")
        results = fallback_by_extension([f])
        assert "Images" in results[0].folder_name or "/" in results[0].folder_name

    def test_image_oserror_fallback(self, tmp_path: Path) -> None:
        # File doesn't exist → stat() raises OSError → year = "Unknown"
        f = tmp_path / "nonexistent_photo.jpg"
        results = fallback_by_extension([f])
        assert "Unknown" in results[0].folder_name

    def test_text_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.txt"
        f.write_text("text")
        results = fallback_by_extension([f])
        assert results[0].folder_name != "Other"

    def test_empty_list(self) -> None:
        assert fallback_by_extension([]) == []


# ---------------------------------------------------------------------------
# organize_files
# ---------------------------------------------------------------------------


def _make_processed_file(
    file_path: Path, folder: str = "Docs", name: str = "file"
) -> ProcessedFile:
    return ProcessedFile(
        file_path=file_path,
        description="test",
        folder_name=folder,
        filename=name,
        error=None,
    )


def _make_error_file(file_path: Path) -> ProcessedFile:
    return ProcessedFile(
        file_path=file_path,
        description="test",
        folder_name="Docs",
        filename="errfile",
        error="some error",
    )


class TestOrganizeFilesSkipExisting:
    def test_skip_existing_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "out"
        # Pre-create destination
        dest = out / "Docs" / "file.txt"
        dest.parent.mkdir(parents=True)
        dest.write_text("existing")

        result = organize_files(
            [_make_processed_file(src)],
            out,
            skip_existing=True,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )
        # File was skipped → not in result
        assert "Docs" not in result or "file.txt" not in result.get("Docs", [])

    def test_collision_increments_counter(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "myfile.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "out"
        # Pre-create same destination using same stem as filename param
        existing = out / "Docs" / "myfile.txt"
        existing.parent.mkdir(parents=True)
        existing.write_text("existing")

        result = organize_files(
            [_make_processed_file(src, name="myfile")],
            out,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )
        assert "Docs" in result
        assert any("_1" in name for name in result["Docs"])

    def test_error_file_skipped(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "bad.txt"
        src.parent.mkdir()
        src.write_text("x")
        out = tmp_path / "out"
        result = organize_files(
            [_make_error_file(src)],
            out,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )
        assert result == {}


class TestOrganizeFilesHardlinks:
    def test_hardlink_creates_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "doc.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "out"
        result = organize_files(
            [_make_processed_file(src)],
            out,
            skip_existing=False,
            use_hardlinks=True,
            undo_manager=None,
            transaction_id=None,
        )
        assert "Docs" in result

    def test_exception_on_organize_skipped(self, tmp_path: Path) -> None:
        # Source doesn't exist → shutil.copy2 raises → exception handled gracefully
        src = tmp_path / "nonexistent.txt"
        out = tmp_path / "out"
        result = organize_files(
            [_make_processed_file(src)],
            out,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )
        assert "Docs" not in result


class TestOrganizeFilesUndoManager:
    def test_undo_manager_log_called(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "doc.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "out"

        undo_manager = MagicMock()
        undo_manager.history.log_operation = MagicMock()

        organize_files(
            [_make_processed_file(src)],
            out,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=undo_manager,
            transaction_id="txn-001",
        )
        undo_manager.history.log_operation.assert_called_once()

    def test_undo_manager_none_skips_log(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "doc.txt"
        src.parent.mkdir()
        src.write_text("content")
        out = tmp_path / "out"
        result = organize_files(
            [_make_processed_file(src)],
            out,
            skip_existing=False,
            use_hardlinks=False,
            undo_manager=None,
            transaction_id=None,
        )
        assert "Docs" in result


# ---------------------------------------------------------------------------
# simulate_organization
# ---------------------------------------------------------------------------


class TestSimulateOrganization:
    def test_returns_folder_map(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.txt"
        src.write_text("x")
        result = simulate_organization([_make_processed_file(src)], tmp_path)
        assert "Docs" in result

    def test_error_file_excluded(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.txt"
        src.write_text("x")
        result = simulate_organization([_make_error_file(src)], tmp_path)
        assert result == {}

    def test_multiple_files_same_folder(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.txt"
        src2 = tmp_path / "b.txt"
        src1.write_text("x")
        src2.write_text("y")
        result = simulate_organization(
            [_make_processed_file(src1, name="a"), _make_processed_file(src2, name="b")],
            tmp_path,
        )
        assert len(result["Docs"]) == 2


# ---------------------------------------------------------------------------
# cleanup_empty_dirs
# ---------------------------------------------------------------------------


class TestCleanupEmptyDirs:
    def test_removes_empty_subdir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_sub"
        empty.mkdir()
        cleanup_empty_dirs(tmp_path)
        assert not empty.exists()

    def test_keeps_nonempty_subdir(self, tmp_path: Path) -> None:
        non_empty = tmp_path / "sub"
        non_empty.mkdir()
        (non_empty / "file.txt").write_text("content")
        cleanup_empty_dirs(tmp_path)
        assert non_empty.exists()

    def test_does_not_remove_root(self, tmp_path: Path) -> None:
        cleanup_empty_dirs(tmp_path)
        assert tmp_path.exists()

    def test_nested_empty_dirs_removed(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        cleanup_empty_dirs(tmp_path)
        assert not (tmp_path / "a").exists()


# ---------------------------------------------------------------------------
# NamingAnalyzer — naming styles and normalize
# ---------------------------------------------------------------------------


class TestNamingAnalyzerIdentifyStyle:
    def test_snake_case(self) -> None:
        a = NamingAnalyzer()
        assert a.identify_naming_style("my_file_name.txt") == "snake_case"

    def test_kebab_case(self) -> None:
        a = NamingAnalyzer()
        assert a.identify_naming_style("my-file-name.txt") == "kebab-case"

    def test_camel_case(self) -> None:
        a = NamingAnalyzer()
        assert a.identify_naming_style("myFileName.txt") == "camelCase"

    def test_pascal_case(self) -> None:
        a = NamingAnalyzer()
        assert a.identify_naming_style("MyFileName.txt") == "PascalCase"

    def test_space_separated(self) -> None:
        a = NamingAnalyzer()
        assert a.identify_naming_style("my file name.txt") == "space_separated"

    def test_mixed(self) -> None:
        a = NamingAnalyzer()
        result = a.identify_naming_style("My_file-NAME.txt")
        assert len(result) > 0


class TestNamingAnalyzerNormalize:
    def test_to_snake_case(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("myFileName.txt", target_style="snake_case")
        assert "_" in result

    def test_to_kebab_case(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file_name.txt", target_style="kebab-case")
        assert "-" in result

    def test_to_camel_case(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file_name.txt", target_style="camelCase")
        assert result[0].islower()

    def test_to_pascal_case(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file_name.txt", target_style="PascalCase")
        assert result[0].isupper()

    def test_to_space_separated(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file_name.txt", target_style="space_separated")
        assert " " in result

    def test_unknown_style_returns_original(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file_name.txt", target_style="unknown")
        assert "my_file_name" in result

    def test_preserves_extension(self) -> None:
        a = NamingAnalyzer()
        result = a.normalize_filename("my_file.pdf", target_style="kebab-case")
        assert result.endswith(".pdf")


class TestNamingAnalyzerSemanticComponents:
    def test_version_extracted(self) -> None:
        a = NamingAnalyzer()
        result = a.extract_semantic_components("report_v2.pdf")
        assert "version" in result

    def test_date_extracted(self) -> None:
        a = NamingAnalyzer()
        result = a.extract_semantic_components("meeting_2024-01-15.txt")
        assert "date" in result

    def test_metadata_tokens(self) -> None:
        a = NamingAnalyzer()
        result = a.extract_semantic_components("backup_final.zip")
        assert len(result["potential_metadata"]) > 0

    def test_no_version_no_date(self) -> None:
        a = NamingAnalyzer()
        result = a.extract_semantic_components("simple_document.txt")
        assert "version" not in result
        assert "date" not in result


class TestNamingAnalyzerCompare:
    def test_identical_files_high_similarity(self) -> None:
        a = NamingAnalyzer()
        result = a.compare_structures("report_2024.txt", "report_2024.txt")
        assert result["overall_similarity"] == pytest.approx(1.0)

    def test_different_files_lower_similarity(self) -> None:
        a = NamingAnalyzer()
        result = a.compare_structures("invoice_jan.pdf", "photo_vacation.jpg")
        assert result["overall_similarity"] < 1.0

    def test_find_common_pattern_empty(self) -> None:
        a = NamingAnalyzer()
        assert a.find_common_pattern([]) is None

    def test_find_common_pattern_single(self) -> None:
        a = NamingAnalyzer()
        result = a.find_common_pattern(["report.txt"])
        assert result is not None
        assert result["sample_size"] == 1

    def test_extract_pattern_differences(self) -> None:
        a = NamingAnalyzer()
        diff = a.extract_pattern_differences("my_file_draft.txt", "my_file_final.txt")
        assert isinstance(diff, dict)
        assert "edit_distance" in diff

    def test_delimiter_change_included(self) -> None:
        a = NamingAnalyzer()
        diff = a.extract_pattern_differences("my-file.txt", "my_file.txt")
        if diff["delimiter_change"]:
            assert "old_delimiters" in diff


class TestNamingAnalyzerDelimiterSimilarity:
    def test_both_empty_returns_one(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_delimiter_similarity([], []) == pytest.approx(1.0)

    def test_one_empty_returns_zero(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_delimiter_similarity(["_"], []) == pytest.approx(0.0)

    def test_matching_delimiters_high(self) -> None:
        a = NamingAnalyzer()
        result = a._calculate_delimiter_similarity(["_", "-"], ["_", "-"])
        assert result == pytest.approx(1.0)


class TestNamingAnalyzerTokenSimilarity:
    def test_both_empty_returns_zero(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_token_similarity([], []) == pytest.approx(0.0)

    def test_one_empty_returns_zero(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_token_similarity(["word"], []) == pytest.approx(0.0)


class TestNamingAnalyzerEditDistance:
    def test_empty_string(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_edit_distance("abc", "") == 3

    def test_short_str_swapped(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_edit_distance("ab", "abc") == 1

    def test_same_string(self) -> None:
        a = NamingAnalyzer()
        assert a._calculate_edit_distance("hello", "hello") == 0


# ---------------------------------------------------------------------------
# InMemoryCache
# ---------------------------------------------------------------------------


class TestInMemoryCacheTTL:
    def test_expired_entry_returns_none(self) -> None:
        cache = InMemoryCache()
        cache.set("k", "v", ttl_seconds=1)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cache.get("k") is None:
                break
        assert cache.get("k") is None

    def test_absent_key_returns_none(self) -> None:
        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_set_and_get_within_ttl(self) -> None:
        cache = InMemoryCache()
        cache.set("k", "value", ttl_seconds=60)
        assert cache.get("k") == "value"

    def test_delete_removes_entry(self) -> None:
        cache = InMemoryCache()
        cache.set("k", "value", ttl_seconds=60)
        cache.delete("k")
        assert cache.get("k") is None

    def test_close_clears_entries(self) -> None:
        cache = InMemoryCache()
        cache.set("a", "1", ttl_seconds=60)
        cache.set("b", "2", ttl_seconds=60)
        cache.close()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_zero_ttl_still_stores(self) -> None:
        cache = InMemoryCache()
        # ttl_seconds=0 → max(1, 0) = 1 → stored for at least 1 second
        cache.set("k", "v", ttl_seconds=0)
        assert cache.get("k") == "v"


class TestBuildCacheBackend:
    def test_none_url_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        backend = build_cache_backend(None)
        assert isinstance(backend, InMemoryCache)

    def test_empty_url_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        backend = build_cache_backend("")
        assert isinstance(backend, InMemoryCache)

    def test_invalid_scheme_returns_in_memory(self) -> None:
        from file_organizer.api.cache import InMemoryCache

        backend = build_cache_backend("ftp://localhost:6379")
        assert isinstance(backend, InMemoryCache)

    def test_valid_redis_url_attempts_connection(self) -> None:
        # A valid URL that fails to connect returns either RedisCache or InMemoryCache fallback
        backend = build_cache_backend("redis://nonexistent-host:9999/0")
        # Verify the backend implements CacheBackend protocol
        assert hasattr(backend, "get")
        assert hasattr(backend, "set")
        assert hasattr(backend, "delete")


class TestIsValidRedisUrl:
    def test_redis_scheme_valid(self) -> None:
        assert _is_valid_redis_url("redis://localhost:6379") is True

    def test_rediss_scheme_valid(self) -> None:
        assert _is_valid_redis_url("rediss://localhost:6380") is True

    def test_unix_scheme_valid(self) -> None:
        assert _is_valid_redis_url("unix:///var/run/redis.sock") is True

    def test_http_scheme_invalid(self) -> None:
        assert _is_valid_redis_url("http://localhost:6379") is False

    def test_ftp_scheme_invalid(self) -> None:
        assert _is_valid_redis_url("ftp://localhost") is False


# ---------------------------------------------------------------------------
# InMemoryRateLimiter — max_entries sweep
# ---------------------------------------------------------------------------


class TestInMemoryRateLimiterMaxEntries:
    def test_max_entries_triggers_sweep(self) -> None:
        # Set max_entries=2 and sweep_interval=9999 (won't time-trigger)
        # After 3 unique keys → size check triggers sweep
        limiter = InMemoryRateLimiter(max_entries=2, sweep_interval_seconds=9999)
        limiter.check("k1", limit=5, window_seconds=1)
        limiter.check("k2", limit=5, window_seconds=1)
        # k1/k2 windows are 1s; size-based sweep fires on the third unique key
        # The third check triggers the size-based sweep
        result = limiter.check("k3", limit=5, window_seconds=60)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# utils/text_processing
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_empty_input_returns_empty(self) -> None:
        assert clean_text("") == ""

    def test_removes_special_chars(self) -> None:
        result = clean_text("hello, world!")
        assert "," not in result
        assert "!" not in result

    def test_removes_numbers(self) -> None:
        result = clean_text("abc 123 def")
        # Numbers stripped, remaining words cleaned
        assert "123" not in result

    def test_camel_case_split(self) -> None:
        result = clean_text("alphaBravo")
        # camelCase split produces ["alpha", "bravo"], joined as "alpha_bravo"
        assert result == "alpha_bravo"

    def test_max_words_limit(self) -> None:
        text = "alpha beta gamma delta epsilon zeta"
        result = clean_text(text, max_words=3, remove_unwanted=False)
        words = result.split("_")
        assert len(words) < 4

    def test_remove_unwanted_false(self) -> None:
        result = clean_text("the file document", remove_unwanted=False)
        assert "the" in result

    def test_lemmatize_false(self) -> None:
        result = clean_text("running dogs", lemmatize=False)
        assert len(result) > 0


class TestSanitizeFilename:
    def test_normal_text(self) -> None:
        result = sanitize_filename("My Document Report")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_max_length_enforced(self) -> None:
        result = sanitize_filename("a" * 200, max_length=20)
        assert len(result) < 21

    def test_empty_after_clean_returns_untitled(self) -> None:
        # Only numbers → clean_text strips them → empty → "untitled"
        result = sanitize_filename("123456")
        assert result == "untitled"

    def test_result_is_lowercase(self) -> None:
        result = sanitize_filename("HelloWorld")
        assert result == result.lower()


class TestExtractKeywords:
    def test_returns_list(self) -> None:
        result = extract_keywords("machine learning neural network deep learning", top_n=3)
        assert len(result) >= 1

    def test_top_n_respected(self) -> None:
        result = extract_keywords("alpha beta gamma delta epsilon", top_n=2)
        assert len(result) < 3

    def test_empty_text(self) -> None:
        result = extract_keywords("")
        assert result == []


class TestEnsureNltkData:
    def test_runs_without_error(self) -> None:
        ensure_nltk_data()


class TestGetUnwantedWords:
    def test_returns_set(self) -> None:
        result = get_unwanted_words()
        assert len(result) > 0

    def test_contains_common_words(self) -> None:
        result = get_unwanted_words()
        assert "the" in result
        assert "and" in result
