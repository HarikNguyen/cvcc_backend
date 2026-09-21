"""
app/services/job_service.py
----------------------------
Business-logic layer that sits between the router and the AI pipeline.

Responsibilities:
  - Create and persist Job objects.
  - Dispatch background generation tasks.
  - Expose query helpers for the router.

The actual AI pipeline (validate_prompt, gen_scripts, gen_code, etc.)
is injected via the `pipeline` callable so it can be swapped for a
stub/mock in tests without touching this service.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from app.core.store import JobStore, job_store as _default_store
from app.models.job import Job, JobStatus


# Type alias for the generation callable accepted by the service.
# Signature: pipeline(job: Job, store: JobStore) -> None
PipelineCallable = Callable[[Job, JobStore], None]


def _noop_pipeline(job: Job, store: JobStore) -> None:
    """
    Placeholder pipeline used when the AI pipeline is not yet wired.
    Keeps the job in PROCESSING state indefinitely — fine for API-only tests.
    In production this is replaced by the real pipeline from app.services.pipeline.
    """
    pass  # pragma: no cover


class JobService:
    """
    Orchestrates job lifecycle.

    Parameters
    ----------
    store:    The JobStore adapter to use (defaults to the global singleton).
    pipeline: Callable that drives the full generation pipeline. Injected
              so tests can pass a stub without spawning real AI calls.
    """

    def __init__(
        self,
        store: JobStore = _default_store,
        pipeline: PipelineCallable = _noop_pipeline,
    ) -> None:
        self._store = store
        self._pipeline = pipeline

    # ── Commands ───────────────────────────────────────────────────────────

    def submit(self, prompt: str, background_tasks=None) -> Job:
        """
        Create a new job, persist it, and enqueue the generation pipeline.

        Parameters
        ----------
        prompt:           The learner's chemistry question.
        background_tasks: FastAPI BackgroundTasks instance. When None (e.g.,
                          in unit tests) the pipeline is NOT dispatched, which
                          lets callers verify job creation independently.

        Returns
        -------
        The newly created Job (status == WAITING).
        """
        job = Job(prompt=prompt)
        self._store.save(job)

        if background_tasks is not None:
            background_tasks.add_task(self._pipeline, job, self._store)

        return job

    # ── Queries ────────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[Job]:
        """Return a single Job by ID, or None."""
        return self._store.get(job_id)

    def list_jobs(self) -> List[Job]:
        """Return all jobs ordered by creation date descending."""
        return self._store.list_all()

    def get_video_path(self, job_id: str) -> Optional[str]:
        """
        Return the filesystem path to the video artifact, or None if not
        available (job not found, not completed, or path missing).
        """
        job = self._store.get(job_id)
        if job is None or job.status != JobStatus.COMPLETED:
            return None
        return job.video_path


# Module-level default instance — routers import this directly.
job_service = JobService()
