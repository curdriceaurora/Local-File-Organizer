"""Middleware setup for the API layer."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from file_organizer.api.config import ApiSettings


def setup_middleware(app: FastAPI, settings: ApiSettings) -> None:
    """Configure middleware on the FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
