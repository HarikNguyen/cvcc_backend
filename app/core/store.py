"""
app/core/store.py
-----------------
In-memory job store with a clean interface.

Design rationale:
  - The store is the ONLY place that holds the canonical list of jobs.
  - All access is synchronised through this interface so that swapping it
    for a database (SQLite, PostgreSQL) only requires implementing the same
    interface in a new adapter — the service and router layers are untouched.
  - Thread-safety: a threading.Lock guards mutations because FastAPI runs
    BackgroundTasks in a threadpool. If switching to a fully async DB later,
    replace the Lock with asyncio.Lock and mark methods async.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from app.models.job import Job


class JobStore:
    """Thread-safe, in-memory store for Job objects."""

    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}
        self._lock = threading.Lock()

    # ── Write operations ───────────────────────────────────────────────────

    def save(self, job: Job) -> Job:
        """Insert or update a job. Returns the stored job."""
        with self._lock:
            self._store[job.id] = job
        return job

    # ── Read operations ────────────────────────────────────────────────────

    def get(self, job_id: str) -> Optional[Job]:
        """Return the job with the given ID, or None if not found."""
        with self._lock:
            return self._store.get(job_id)

    def list_all(self) -> List[Job]:
        """Return all jobs sorted by created_at descending."""
        with self._lock:
            jobs = list(self._store.values())
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    # ── Utility ────────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all jobs. Intended for use in tests only."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Singleton instance — imported directly by the service and router layers.
# In a production system this would be replaced by a DB session factory.
job_store = JobStore()
