"""Tests for ``SentimentLexicon`` (D6 externalized lexicons).

The audio content analyzer previously embedded ~420 LOC of
sentiment/keyword dicts inline. D6 moves those into a JSON data
file loaded by ``SentimentLexicon``. These tests pin:

- The bundled default JSON parses and yields non-empty, typed fields.
- An override path can replace the bundled file (test injection).
- The loader rejects malformed or incomplete JSON loudly.
- The module-level constants in ``content_analyzer`` still exist
  and carry the expected shape (backward compat).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from file_organizer.services.audio.lexicons import (
    SentimentLexicon,
    SentimentLexiconError,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestDefaultBundledLexicon:
    """The default JSON shipped alongside the module loads cleanly."""

    def test_load_default_returns_populated_lexicon(self) -> None:
        lex = SentimentLexicon.load_default()
        assert isinstance(lex.stop_words, frozenset)
        assert isinstance(lex.topic_categories, dict)
        assert isinstance(lex.positive_words, frozenset)
        assert isinstance(lex.negative_words, frozenset)
        assert isinstance(lex.neutral_words, frozenset)
        # Non-empty — pin the rough sizes so a future JSON edit that
        # empties a field fails loudly rather than silently degrading
        # the content analyzer.
        assert len(lex.stop_words) >= 100
        assert len(lex.topic_categories) >= 5
        assert len(lex.positive_words) >= 20
        assert len(lex.negative_words) >= 20
        assert len(lex.neutral_words) >= 10

    def test_default_load_is_cached(self) -> None:
        """Two calls return the same instance — no reparse on every hit."""
        first = SentimentLexicon.load_default()
        second = SentimentLexicon.load_default()
        assert first is second

    def test_known_sentiment_words_present(self) -> None:
        """Pin a few representative entries so a regression on the
        JSON file (e.g. accidental truncation) fails immediately."""
        lex = SentimentLexicon.load_default()
        assert "excellent" in lex.positive_words
        assert "terrible" in lex.negative_words
        assert "however" in lex.neutral_words
        assert "the" in lex.stop_words

    def test_topic_categories_values_are_lists(self) -> None:
        lex = SentimentLexicon.load_default()
        for category, keywords in lex.topic_categories.items():
            assert isinstance(category, str)
            assert isinstance(keywords, list)
            assert all(isinstance(k, str) for k in keywords)
            assert len(keywords) >= 1


class TestLoadFromPath:
    """Loading from an arbitrary JSON path enables test injection."""

    def test_load_from_path_parses_valid_json(self, tmp_path: Path) -> None:
        data = {
            "stop_words": ["the", "a"],
            "topic_categories": {"Tech": ["cloud", "ai"]},
            "positive_words": ["great"],
            "negative_words": ["bad"],
            "neutral_words": ["however"],
        }
        lexicon_path = tmp_path / "lex.json"
        lexicon_path.write_text(json.dumps(data))

        lex = SentimentLexicon.load_from_path(lexicon_path)

        assert lex.stop_words == frozenset({"the", "a"})
        assert lex.topic_categories == {"Tech": ["cloud", "ai"]}
        assert lex.positive_words == frozenset({"great"})
        assert lex.negative_words == frozenset({"bad"})
        assert lex.neutral_words == frozenset({"however"})

    def test_load_from_path_is_not_cached(self, tmp_path: Path) -> None:
        """Unlike ``load_default``, arbitrary-path loads are not
        singletons — each call reparses (simpler; tests don't need
        caching for overrides)."""
        data = {
            "stop_words": ["x"],
            "topic_categories": {},
            "positive_words": [],
            "negative_words": [],
            "neutral_words": [],
        }
        p = tmp_path / "lex.json"
        p.write_text(json.dumps(data))
        first = SentimentLexicon.load_from_path(p)
        second = SentimentLexicon.load_from_path(p)
        assert first is not second
        assert first.stop_words == second.stop_words


class TestLoaderErrorHandling:
    """The loader fails loudly on malformed JSON or missing keys."""

    def test_missing_file_raises_sentiment_lexicon_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.json"
        with pytest.raises(SentimentLexiconError, match="not found"):
            SentimentLexicon.load_from_path(missing)

    def test_malformed_json_raises_sentiment_lexicon_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{ not valid json")
        with pytest.raises(SentimentLexiconError, match="invalid JSON"):
            SentimentLexicon.load_from_path(bad)

    def test_missing_required_key_raises_sentiment_lexicon_error(self, tmp_path: Path) -> None:
        incomplete = tmp_path / "incomplete.json"
        # Missing ``negative_words`` and ``neutral_words``.
        incomplete.write_text(
            json.dumps(
                {
                    "stop_words": [],
                    "topic_categories": {},
                    "positive_words": [],
                }
            )
        )
        with pytest.raises(SentimentLexiconError, match="missing required key"):
            SentimentLexicon.load_from_path(incomplete)

    def test_wrong_type_for_lexicon_field_raises(self, tmp_path: Path) -> None:
        wrong = tmp_path / "wrong.json"
        wrong.write_text(
            json.dumps(
                {
                    "stop_words": "not a list",
                    "topic_categories": {},
                    "positive_words": [],
                    "negative_words": [],
                    "neutral_words": [],
                }
            )
        )
        with pytest.raises(SentimentLexiconError, match="must be a list"):
            SentimentLexicon.load_from_path(wrong)

    def test_topic_categories_not_an_object_raises(self, tmp_path: Path) -> None:
        """``_as_topic_dict`` branch 1 — non-object value."""
        bad = tmp_path / "topics_not_dict.json"
        bad.write_text(
            json.dumps(
                {
                    "stop_words": [],
                    "topic_categories": ["not", "an", "object"],
                    "positive_words": [],
                    "negative_words": [],
                    "neutral_words": [],
                }
            )
        )
        with pytest.raises(SentimentLexiconError, match="must be an object"):
            SentimentLexicon.load_from_path(bad)

    def test_topic_categories_non_list_value_raises(self, tmp_path: Path) -> None:
        """``_as_topic_dict`` branch 3 — value is not a list of strings."""
        bad = tmp_path / "topics_non_list.json"
        bad.write_text(
            json.dumps(
                {
                    "stop_words": [],
                    "topic_categories": {"Tech": "cloud,ai"},
                    "positive_words": [],
                    "negative_words": [],
                    "neutral_words": [],
                }
            )
        )
        with pytest.raises(SentimentLexiconError, match="must be a list of strings"):
            SentimentLexicon.load_from_path(bad)

    def test_topic_categories_non_string_keyword_raises(self, tmp_path: Path) -> None:
        """``_as_topic_dict`` branch 3 variant — list contains non-string."""
        bad = tmp_path / "topics_non_string_kw.json"
        bad.write_text(
            json.dumps(
                {
                    "stop_words": [],
                    "topic_categories": {"Tech": ["cloud", 42]},
                    "positive_words": [],
                    "negative_words": [],
                    "neutral_words": [],
                }
            )
        )
        with pytest.raises(SentimentLexiconError, match="must be a list of strings"):
            SentimentLexicon.load_from_path(bad)


class TestBackwardCompatModuleConstants:
    """The content_analyzer module-level constants remain usable
    after the extraction — pre-D6 consumers import STOP_WORDS etc.
    directly and must not break."""

    def test_module_constants_still_exist(self) -> None:
        from file_organizer.services.audio.content_analyzer import (
            NEGATIVE_WORDS,
            NEUTRAL_WORDS,
            POSITIVE_WORDS,
            STOP_WORDS,
            TOPIC_CATEGORIES,
        )

        assert isinstance(STOP_WORDS, frozenset)
        assert isinstance(TOPIC_CATEGORIES, dict)
        assert isinstance(POSITIVE_WORDS, frozenset)
        assert isinstance(NEGATIVE_WORDS, frozenset)
        assert isinstance(NEUTRAL_WORDS, frozenset)

    def test_content_analyzer_import_does_not_load_default_lexicon(self, monkeypatch) -> None:
        """Non-audio commands must be able to import the organizer without lexicon I/O."""
        module_name = "file_organizer.services.audio.content_analyzer"
        parent = importlib.import_module("file_organizer.services.audio")
        sys.modules.pop(module_name, None)
        if hasattr(parent, "content_analyzer"):
            delattr(parent, "content_analyzer")

        calls = 0
        lexicon = SentimentLexicon(
            stop_words=frozenset({"the"}),
            topic_categories={"Technology": ["ai"]},
            positive_words=frozenset({"great"}),
            negative_words=frozenset({"bad"}),
            neutral_words=frozenset({"however"}),
        )

        def fake_load_default(cls) -> SentimentLexicon:
            nonlocal calls
            calls += 1
            return lexicon

        monkeypatch.setattr(SentimentLexicon, "load_default", classmethod(fake_load_default))

        module = importlib.import_module(module_name)

        assert calls == 0
        assert module.STOP_WORDS == frozenset({"the"})
        assert calls == 1

    def test_module_constants_match_default_lexicon(self) -> None:
        """The constants ARE the default lexicon's fields — not a copy."""
        from file_organizer.services.audio import content_analyzer as ca

        default = SentimentLexicon.load_default()
        assert ca.STOP_WORDS == default.stop_words
        assert ca.TOPIC_CATEGORIES == default.topic_categories
        assert ca.POSITIVE_WORDS == default.positive_words
        assert ca.NEGATIVE_WORDS == default.negative_words
        assert ca.NEUTRAL_WORDS == default.neutral_words
