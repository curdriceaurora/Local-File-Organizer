"""Coverage tests for plugins.marketplace.reviews module."""

from __future__ import annotations

import json

import pytest

from file_organizer.plugins.marketplace.errors import MarketplaceReviewError
from file_organizer.plugins.marketplace.models import PluginReview
from file_organizer.plugins.marketplace.reviews import ReviewManager

pytestmark = pytest.mark.unit


def _review(
    plugin_name: str = "demo",
    user_id: str = "user1",
    rating: int = 4,
    title: str = "Good",
    content: str = "Works well",
    **kw,
) -> PluginReview:
    return PluginReview(
        plugin_name=plugin_name,
        user_id=user_id,
        rating=rating,
        title=title,
        content=content,
        **kw,
    )


class TestReviewManagerAddReview:
    def test_add_new_review(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review())
        reviews = mgr.get_reviews("demo")
        assert len(reviews) == 1
        assert reviews[0].user_id == "user1"

    def test_add_replaces_existing_from_same_user(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(rating=3, title="OK", content="first"))
        mgr.add_review(_review(rating=5, title="Great", content="updated"))
        reviews = mgr.get_reviews("demo")
        assert len(reviews) == 1
        assert reviews[0].rating == 5

    def test_add_preserves_created_at_on_replace(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(created_at="2024-01-01T00:00:00Z"))
        mgr.add_review(_review(rating=5, title="Updated", content="new content"))
        reviews = mgr.get_reviews("demo")
        assert reviews[0].created_at == "2024-01-01T00:00:00Z"

    def test_add_review_non_list_records_reset(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps({"demo": "not-a-list"}))
        mgr = ReviewManager(db)
        mgr.add_review(_review())
        reviews = mgr.get_reviews("demo")
        assert len(reviews) == 1


class TestReviewManagerUpdateReview:
    def test_update_existing_review(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review())
        mgr.update_review(_review(rating=5, title="Updated", content="better now"))
        reviews = mgr.get_reviews("demo")
        assert reviews[0].rating == 5

    def test_update_nonexistent_raises(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        with pytest.raises(MarketplaceReviewError, match="does not exist"):
            mgr.update_review(_review())

    def test_update_corrupt_records_raises(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps({"demo": "not-a-list"}))
        mgr = ReviewManager(db)
        with pytest.raises(MarketplaceReviewError, match="Corrupt"):
            mgr.update_review(_review())


class TestReviewManagerDeleteReview:
    def test_delete_existing(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review())
        mgr.delete_review("demo", "user1")
        reviews = mgr.get_reviews("demo")
        assert len(reviews) == 0

    def test_delete_nonexistent_no_error(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review())
        mgr.delete_review("demo", "nobody")

    def test_delete_corrupt_records_no_error(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps({"demo": "not-a-list"}))
        mgr = ReviewManager(db)
        mgr.delete_review("demo", "user1")  # Should not raise


class TestReviewManagerGetReviews:
    def test_get_reviews_sorted_by_updated(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(user_id="u1", updated_at="2024-01-01T00:00:00Z"))
        mgr.add_review(_review(user_id="u2", updated_at="2024-06-01T00:00:00Z"))
        reviews = mgr.get_reviews("demo")
        assert reviews[0].user_id == "u2"

    def test_get_reviews_limit(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        for i in range(5):
            mgr.add_review(_review(user_id=f"u{i}"))
        reviews = mgr.get_reviews("demo", limit=2)
        assert len(reviews) == 2

    def test_get_reviews_invalid_limit(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        with pytest.raises(MarketplaceReviewError, match="limit must be"):
            mgr.get_reviews("demo", limit=0)

    def test_get_reviews_corrupt_records_raises(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps({"demo": "not-a-list"}))
        mgr = ReviewManager(db)
        with pytest.raises(MarketplaceReviewError, match="Corrupt"):
            mgr.get_reviews("demo")

    def test_get_reviews_skips_non_dict(self, tmp_path):
        db = tmp_path / "reviews.json"
        review_dict = _review().to_dict()
        db.write_text(json.dumps({"demo": [review_dict, "not-a-dict", 42]}))
        mgr = ReviewManager(db)
        reviews = mgr.get_reviews("demo")
        assert len(reviews) == 1


class TestReviewManagerGetAverageRating:
    def test_no_reviews_returns_zero(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        assert mgr.get_average_rating("demo") == 0.0

    def test_average_calculation(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(user_id="u1", rating=3))
        mgr.add_review(_review(user_id="u2", rating=5))
        assert mgr.get_average_rating("demo") == 4.0


class TestReviewManagerMarkHelpful:
    def test_mark_helpful_increments(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(user_id="author"))
        mgr.mark_helpful("demo", "author", "reader")
        reviews = mgr.get_reviews("demo")
        assert reviews[0].helpful_count == 1

    def test_mark_own_review_raises(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        mgr.add_review(_review(user_id="same"))
        with pytest.raises(MarketplaceReviewError, match="own review"):
            mgr.mark_helpful("demo", "same", "same")

    def test_mark_nonexistent_review_raises(self, tmp_path):
        mgr = ReviewManager(tmp_path / "reviews.json")
        with pytest.raises(MarketplaceReviewError, match="does not exist"):
            mgr.mark_helpful("demo", "nobody", "reader")

    def test_mark_helpful_corrupt_records_raises(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps({"demo": "not-a-list"}))
        mgr = ReviewManager(db)
        with pytest.raises(MarketplaceReviewError, match="Corrupt"):
            mgr.mark_helpful("demo", "user1", "reader")


class TestReviewManagerPayload:
    def test_read_payload_invalid_json(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text("{bad json")
        mgr = ReviewManager(db)
        with pytest.raises(MarketplaceReviewError, match="Failed to read"):
            mgr._read_payload()

    def test_read_payload_non_dict(self, tmp_path):
        db = tmp_path / "reviews.json"
        db.write_text(json.dumps([1, 2]))
        mgr = ReviewManager(db)
        with pytest.raises(MarketplaceReviewError, match="must be a JSON object"):
            mgr._read_payload()

    def test_read_payload_missing_file(self, tmp_path):
        mgr = ReviewManager(tmp_path / "missing.json")
        assert mgr._read_payload() == {}
