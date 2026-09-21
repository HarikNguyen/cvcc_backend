"""
tests/test_job_model.py
------------------------
Unit tests for the Job domain model and its state transition helpers.
These tests have zero network / file-system / AI dependencies.
"""

from __future__ import annotations

import time

import pytest

from app.models.job import Job, JobStatus


class TestJobDefaults:
    def test_default_status_is_waiting(self):
        job = Job(prompt="test")
        assert job.status == JobStatus.WAITING

    def test_id_is_uuid_string(self):
        job = Job(prompt="test")
        import uuid
        uuid.UUID(job.id)  # raises ValueError if not a valid UUID

    def test_two_jobs_have_different_ids(self):
        a = Job(prompt="test")
        b = Job(prompt="test")
        assert a.id != b.id

    def test_created_at_equals_updated_at_on_creation(self):
        job = Job(prompt="test")
        assert job.created_at == job.updated_at

    def test_progress_and_video_path_and_error_are_none_by_default(self):
        job = Job(prompt="test")
        assert job.progress is None
        assert job.video_path is None
        assert job.error_reason is None


class TestJobTransitions:
    def test_mark_processing_changes_status(self):
        job = Job(prompt="test")
        job.mark_processing()
        assert job.status == JobStatus.PROCESSING

    def test_mark_processing_sets_default_progress(self):
        job = Job(prompt="test")
        job.mark_processing()
        assert job.progress == "Starting pipeline..."

    def test_mark_processing_accepts_custom_progress(self):
        job = Job(prompt="test")
        job.mark_processing(progress="Validating prompt...")
        assert job.progress == "Validating prompt..."

    def test_advance_progress_updates_label(self):
        job = Job(prompt="test")
        job.mark_processing()
        job.advance_progress("Generating script...")
        assert job.progress == "Generating script..."
        assert job.status == JobStatus.PROCESSING

    def test_mark_completed_sets_status_and_path(self):
        job = Job(prompt="test")
        job.mark_processing()
        job.mark_completed("/artifacts/video.mp4")
        assert job.status == JobStatus.COMPLETED
        assert job.video_path == "/artifacts/video.mp4"
        assert job.progress is None

    def test_mark_failed_sets_status_and_reason(self):
        job = Job(prompt="test")
        job.mark_failed("Prompt is not chemistry-related.")
        assert job.status == JobStatus.FAILED
        assert job.error_reason == "Prompt is not chemistry-related."
        assert job.progress is None

    def test_mark_failed_from_processing(self):
        job = Job(prompt="test")
        job.mark_processing()
        job.mark_failed("Render timed out.")
        assert job.status == JobStatus.FAILED

    def test_transition_bumps_updated_at(self):
        job = Job(prompt="test")
        original = job.updated_at
        time.sleep(0.01)  # ensure clock advances
        job.mark_processing()
        assert job.updated_at > original
