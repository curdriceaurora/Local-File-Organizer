"""Tests for API background jobs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from file_organizer.api.jobs import create_job, get_job, list_jobs, update_job


class TestAPIJobs:
    """Tests for API jobs."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture(autouse=True)
    def mock_realtime(self):
        """Mock realtime manager to prevent connection errors during tests."""
        with patch("file_organizer.api.jobs.realtime_manager"):
            yield

    @pytest.mark.asyncio
    async def test_create_job(self, mock_db):
        """Test creating a new job."""
        job_id = str(uuid4())
        job_type = "organize"

        with patch("file_organizer.api.jobs.uuid4", return_value=MagicMock(hex=job_id)):
            job = create_job(job_type)

            assert job.job_id == job_id
            assert job.job_type == job_type
            assert job.status == "queued"

    @pytest.mark.asyncio
    async def test_get_job(self):
        """Test retrieving a job."""
        job = create_job("analyze")

        retrieved_job = get_job(job.job_id)
        assert retrieved_job == job

        # Test non-existent job
        assert get_job("non-existent") is None

    @pytest.mark.asyncio
    async def test_update_job(self):
        """Test updating a job status."""
        job = create_job("dedupe")

        updated_job = update_job(job.job_id, status="completed", result={"duplicates": 5})

        assert updated_job.status == "completed"
        assert updated_job.result == {"duplicates": 5}

        # Verify get returns updated state
        retrieved = get_job(job.job_id)
        assert retrieved.status == "completed"

    @pytest.mark.asyncio
    async def test_list_jobs(self):
        """Test listing jobs."""
        job = create_job("organize")

        jobs = list_jobs()
        assert any(j.job_id == job.job_id for j in jobs)
