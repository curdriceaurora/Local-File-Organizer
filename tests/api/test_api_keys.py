"""Tests for API key helpers."""

from __future__ import annotations
import pytest

import stat

from file_organizer.api.api_keys import (
    _main,
    _write_key,
    api_key_identifier,
    generate_api_key,
    hash_api_key,
    match_api_key_hash,
    verify_api_key,
)


@pytest.mark.unit
class TestGenerateApiKey:
    """Tests for generate_api_key."""

    def test_default_prefix(self):
        key = generate_api_key()
        assert key.startswith("fo_")

    def test_custom_prefix(self):
        key = generate_api_key(prefix="myapp")
        assert key.startswith("myapp_")

    def test_key_format_three_parts(self):
        key = generate_api_key()
        parts = key.split("_", 2)
        assert len(parts) == 3
        # prefix, 8-char hex id, base64url token
        assert parts[0] == "fo"
        assert len(parts[1]) == 8
        assert len(parts[2]) > 0

    def test_uniqueness(self):
        keys = {generate_api_key() for _ in range(10)}
        assert len(keys) == 10


@pytest.mark.unit
class TestHashApiKey:
    """Tests for hash_api_key."""

    def test_returns_bcrypt_hash(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert isinstance(hashed, str)
        assert hashed.startswith("$2")

    def test_different_hashes_for_same_key(self):
        key = generate_api_key()
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        # bcrypt uses random salt, hashes differ
        assert h1 != h2


@pytest.mark.unit
class TestMatchApiKeyHash:
    """Tests for match_api_key_hash."""

    def test_match_returns_stored_hash(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        result = match_api_key_hash(key, [hashed])
        assert result == hashed

    def test_no_match_returns_none(self):
        key = generate_api_key()
        other_hash = hash_api_key(generate_api_key())
        result = match_api_key_hash(key, [other_hash])
        assert result is None

    def test_empty_hashes_returns_none(self):
        key = generate_api_key()
        result = match_api_key_hash(key, [])
        assert result is None

    def test_invalid_hash_skipped(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        result = match_api_key_hash(key, ["not-a-valid-hash", hashed])
        assert result == hashed

    def test_multiple_hashes_finds_correct(self):
        key1 = generate_api_key()
        key2 = generate_api_key()
        h1 = hash_api_key(key1)
        h2 = hash_api_key(key2)
        result = match_api_key_hash(key2, [h1, h2])
        assert result == h2


@pytest.mark.unit
class TestVerifyApiKey:
    """Tests for verify_api_key."""

    def test_valid_key(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(key, [hashed]) is True

    def test_invalid_key(self):
        key = generate_api_key()
        other_hash = hash_api_key(generate_api_key())
        assert verify_api_key(key, [other_hash]) is False


@pytest.mark.unit
class TestApiKeyIdentifier:
    """Tests for api_key_identifier."""

    def test_returns_key_id_part(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        ident = api_key_identifier(key, [hashed])
        # Should return the 8-char hex part
        parts = key.split("_", 2)
        assert ident == parts[1]

    def test_no_match_returns_none(self):
        key = generate_api_key()
        other_hash = hash_api_key(generate_api_key())
        assert api_key_identifier(key, [other_hash]) is None

    def test_key_without_proper_format_falls_back(self):
        """Key with <3 parts falls back to last 12 chars of hash."""
        raw = "singletokennounderscores"
        hashed = hash_api_key(raw)
        ident = api_key_identifier(raw, [hashed])
        assert ident == hashed[-12:]

    def test_key_with_empty_id_part_falls_back(self):
        """Key like 'fo__token' has empty id part, should fallback."""
        raw = "fo__token"
        hashed = hash_api_key(raw)
        ident = api_key_identifier(raw, [hashed])
        # parts[1] is empty string, which is falsy
        assert ident == hashed[-12:]


@pytest.mark.unit
class TestWriteKey:
    """Tests for _write_key."""

    def test_creates_file_with_key(self, tmp_path):
        key_file = tmp_path / "subdir" / "key.txt"
        _write_key(key_file, "test-api-key-123")
        assert key_file.read_text() == "test-api-key-123"

    def test_file_permissions(self, tmp_path):
        key_file = tmp_path / "key.txt"
        _write_key(key_file, "secret")
        mode = key_file.stat().st_mode
        # File should be owner-read/write only (0o600)
        assert stat.S_IMODE(mode) == 0o600


@pytest.mark.unit
class TestMain:
    """Tests for _main CLI entrypoint."""

    def test_help_flag(self, capsys):
        result = _main(["--help"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_h_flag(self, capsys):
        result = _main(["-h"])
        assert result == 0

    def test_missing_output(self, capsys):
        result = _main([])
        assert result == 1
        captured = capsys.readouterr()
        assert "Missing --output" in captured.out

    def test_output_missing_value(self, capsys):
        result = _main(["--output"])
        assert result == 1

    def test_prefix_missing_value(self, capsys):
        result = _main(["--prefix"])
        assert result == 1

    def test_successful_generation(self, tmp_path, capsys):
        out_file = tmp_path / "api_key.txt"
        result = _main(["--output", str(out_file)])
        assert result == 0
        captured = capsys.readouterr()
        assert "API key saved to:" in captured.out
        assert "Bcrypt hash:" in captured.out
        content = out_file.read_text()
        assert content.startswith("fo_")

    def test_custom_prefix_generation(self, tmp_path, capsys):
        out_file = tmp_path / "api_key.txt"
        result = _main(["--prefix", "custom", "--output", str(out_file)])
        assert result == 0
        content = out_file.read_text()
        assert content.startswith("custom_")
