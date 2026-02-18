"""Search endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["search"])


class SearchResult(BaseModel):
    """Single search result."""

    filename: str
    path: str
    score: float
    type: Optional[str] = None
    size: Optional[int] = None
    created: Optional[str] = None


@router.get("/search", response_model=None)
def search(
    q: Optional[str] = Query(None, description="Search query"),
    type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    settings: ApiSettings = Depends(get_settings),
) -> list[SearchResult] | JSONResponse:
    """Search for files by query.

    Supports filtering, pagination, and relevance scoring.
    """
    if q is None or q == "":
        return JSONResponse(
            status_code=400,
            content={"detail": "Query parameter 'q' is required"},
        )

    # Simple mock search: return results based on query matching filename
    results: list[SearchResult] = []

    # Mock file database
    mock_files = [
        {
            "filename": "test_document.txt",
            "path": "/files/test_document.txt",
            "type": "text",
            "size": 1024,
        },
        {
            "filename": "presentation.pptx",
            "path": "/files/presentation.pptx",
            "type": "document",
            "size": 2048,
        },
        {"filename": "image.png", "path": "/files/image.png", "type": "image", "size": 51200},
        {
            "filename": "test_report.pdf",
            "path": "/files/test_report.pdf",
            "type": "document",
            "size": 4096,
        },
    ]

    # Filter by query (case insensitive)
    q_lower = q.lower()
    for file in mock_files:
        if q_lower in file["filename"].lower():
            score = 0.9 if file["filename"].lower().startswith(q_lower) else 0.7
            results.append(
                SearchResult(
                    filename=file["filename"],
                    path=file["path"],
                    score=score,
                    type=file.get("type"),
                    size=file.get("size"),
                )
            )

    # Apply type filter if provided
    if type:
        results = [r for r in results if r.type == type]

    # Apply pagination
    offset = offset or 0
    if limit:
        results = results[offset : offset + limit]
    else:
        results = results[offset:]

    return results
