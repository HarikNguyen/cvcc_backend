"""
app/models/job.py
-----------------
Domain model for a video generation Job.
This is the internal state object; it is NOT directly serialised to API clients.
Persistence adapters (storage layer) convert between this and any storage format.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class JobStatus(str, Enum):
    """
    Lifecycle of a video generation request.

    Transitions:
        WAITING --> PROCESSING --> COMPLETED
                 \\            \\-> FAILED
                  \\-> FAILED (prompt validation failure)
    """
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(BaseModel):
    """
    Internal domain model representing one video generation job.

    Fields that are only meaningful in certain statuses:
      - video_path:   populated when status == COMPLETED
      - error_reason: populated when status == FAILED
      - progress:     populated while status == PROCESSING (current pipeline step)
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    status: JobStatus = JobStatus.WAITING
    progress: Optional[str] = None       # current pipeline step description
    video_path: Optional[str] = None     # absolute path on disk
    error_reason: Optional[str] = None   # human-readable failure reason
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None  # set to created_at in __init__

    def model_post_init(self, __context) -> None:
        """Ensure updated_at mirrors created_at on construction (same instant)."""
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", self.created_at)

    # ── Transition helpers ─────────────────────────────────────────────────
    # Each helper enforces valid state transitions and always bumps updated_at.

    def mark_processing(self, progress: str = "Starting pipeline...") -> None:
        """WAITING -> PROCESSING"""
        self.status = JobStatus.PROCESSING
        self.progress = progress
        self.updated_at = _utcnow()

    def advance_progress(self, progress: str) -> None:
        """Update progress label while remaining in PROCESSING."""
        self.progress = progress
        self.updated_at = _utcnow()

    def mark_completed(self, video_path: str) -> None:
        """PROCESSING -> COMPLETED"""
        self.status = JobStatus.COMPLETED
        self.video_path = video_path
        self.progress = None
        self.updated_at = _utcnow()

    def mark_failed(self, reason: str) -> None:
        """WAITING/PROCESSING -> FAILED"""
        self.status = JobStatus.FAILED
        self.error_reason = reason
        self.progress = None
        self.updated_at = _utcnow()
