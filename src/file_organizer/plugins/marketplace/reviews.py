"""Marketplace review storage and lookup."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from file_organizer.plugins.marketplace.errors import MarketplaceReviewError
from file_organizer.plugins.marketplace.models import PluginReview, utc_now_iso


class ReviewManager:
    """Manage plugin reviews in a local JSON store."""

    def __init__(self, db_path: Path) -> None:
        """Set up the review manager backed by the given database path."""
        self.db_path = db_path

    def add_review(self, review: PluginReview) -> None:
        """Add or replace a review from the same user."""
        payload = self._read_payload()
        records = payload.setdefault(review.plugin_name, [])
        if not isinstance(records, list):
            records = []
            payload[review.plugin_name] = records

        replaced = False
        for index, raw in enumerate(records):
            if isinstance(raw, dict) and raw.get("user_id") == review.user_id:
                previous = PluginReview.from_dict(raw)
                records[index] = PluginReview(
                    plugin_name=review.plugin_name,
                    user_id=review.user_id,
                    rating=review.rating,
                    title=review.title,
                    content=review.content,
                    created_at=previous.created_at,
                    updated_at=utc_now_iso(),
                    helpful_count=previous.helpful_count,
                ).to_dict()
                replaced = True
                break
        if not replaced:
            records.append(review.to_dict())
        self._write_payload(payload)

    def update_review(self, review: PluginReview) -> None:
        """Update an existing review from the same user."""
        payload = self._read_payload()
        records = payload.get(review.plugin_name, [])
        if not isinstance(records, list):
            raise MarketplaceReviewError("Corrupt review payload for plugin.")
        for index, raw in enumerate(records):
            if isinstance(raw, dict) and raw.get("user_id") == review.user_id:
                previous = PluginReview.from_dict(raw)
                records[index] = PluginReview(
                    plugin_name=review.plugin_name,
                    user_id=review.user_id,
                    rating=review.rating,
                    title=review.title,
                    content=review.content,
                    created_at=previous.created_at,
                    updated_at=utc_now_iso(),
                    helpful_count=previous.helpful_count,
                ).to_dict()
                self._write_payload(payload)
                return
        raise MarketplaceReviewError("Review does not exist.")

    def delete_review(self, plugin_name: str, user_id: str) -> None:
        """Delete a review if it exists."""
        payload = self._read_payload()
        records = payload.get(plugin_name, [])
        if not isinstance(records, list):
            return
        payload[plugin_name] = [
            raw
            for raw in records
            if not (isinstance(raw, dict) and str(raw.get("user_id", "")) == user_id)
        ]
        self._write_payload(payload)

    def get_reviews(self, plugin_name: str, *, limit: int = 10) -> list[PluginReview]:
        """Return most recently updated reviews."""
        if limit < 1:
            raise MarketplaceReviewError("limit must be >= 1.")
        payload = self._read_payload()
        records = payload.get(plugin_name, [])
        if not isinstance(records, list):
            raise MarketplaceReviewError("Corrupt review payload for plugin.")
        parsed: list[PluginReview] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            parsed.append(PluginReview.from_dict(raw))
        parsed.sort(key=lambda review: review.updated_at, reverse=True)
        return parsed[:limit]

    def get_average_rating(self, plugin_name: str) -> float:
        """Return average rating for a plugin, or 0 when no reviews exist."""
        reviews = self.get_reviews(plugin_name, limit=1000)
        if not reviews:
            return 0.0
        return sum(review.rating for review in reviews) / float(len(reviews))

    def mark_helpful(self, plugin_name: str, user_id: str, reviewer_id: str) -> None:
        """Increment helpful count for a specific review."""
        if user_id == reviewer_id:
            raise MarketplaceReviewError("Users cannot mark their own review as helpful.")
        payload = self._read_payload()
        records = payload.get(plugin_name, [])
        if not isinstance(records, list):
            raise MarketplaceReviewError("Corrupt review payload for plugin.")
        for index, raw in enumerate(records):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("user_id", "")) != user_id:
                continue
            review = PluginReview.from_dict(raw)
            records[index] = PluginReview(
                plugin_name=review.plugin_name,
                user_id=review.user_id,
                rating=review.rating,
                title=review.title,
                content=review.content,
                created_at=review.created_at,
                updated_at=utc_now_iso(),
                helpful_count=review.helpful_count + 1,
            ).to_dict()
            self._write_payload(payload)
            return
        raise MarketplaceReviewError("Review does not exist.")

    def _read_payload(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {}
        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MarketplaceReviewError(f"Failed to read review store: {self.db_path}") from exc
        if not isinstance(payload, dict):
            raise MarketplaceReviewError("Review store root must be a JSON object.")
        return payload

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.db_path.parent),
            prefix=f".{self.db_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            Path(tmp_path).replace(self.db_path)
        except OSError as exc:
            raise MarketplaceReviewError(f"Failed to write review store: {self.db_path}") from exc
        finally:
            leftover = Path(tmp_path)
            if leftover.exists():
                leftover.unlink(missing_ok=True)
