"""
app/schemas/job.py
------------------
Pydantic schemas for the Job API request/response contract.
Intentionally separate from the internal domain model (app.models.job.Job)
so the API surface can evolve independently of internal storage format.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.job import JobStatus


# ── Requests ──────────────────────────────────────────────────────────────────

class VideoRequestIn(BaseModel):
    """Body accepted by POST /api/v1/videos."""

    prompt: str = Field(
        ...,
        min_length=5,
        max_length=500,
        examples=["Why do atoms form covalent bonds?"],
        description="The chemistry concept the learner wants explained.",
    )


# ── Responses ─────────────────────────────────────────────────────────────────

class JobSubmittedOut(BaseModel):
    """Response body for a newly submitted job (202 Accepted)."""

    job_id: str
    status: JobStatus
    message: str = "Video generation job submitted successfully."


class JobSummaryOut(BaseModel):
    """Compact job representation used in the list endpoint."""

    job_id: str
    prompt: str
    status: JobStatus
    created_at: datetime


class JobDetailOut(BaseModel):
    """Full job detail returned by the status endpoint."""

    job_id: str
    prompt: str
    status: JobStatus
    progress: Optional[str] = Field(
        None,
        description="Human-readable step description during PROCESSING.",
    )
    error_reason: Optional[str] = Field(
        None,
        description="Populated when status is FAILED.",
    )
    created_at: datetime
    updated_at: datetime


# ── Error envelope ────────────────────────────────────────────────────────────

class ErrorOut(BaseModel):
    """Uniform error response envelope."""

    detail: str
