"""
app/api/v1/videos.py
---------------------
Router: /api/v1/videos

Endpoints:
  POST   /api/v1/videos             → Submit a generation request
  GET    /api/v1/videos             → List all jobs
  GET    /api/v1/videos/{job_id}    → Get job status/detail
  GET    /api/v1/videos/{job_id}/artifact → Download completed video
"""

from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from app.models.job import JobStatus
from app.schemas import (
    ErrorOut,
    JobDetailOut,
    JobSubmittedOut,
    JobSummaryOut,
    VideoRequestIn,
)
from app.services import JobService, job_service as _default_service

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])


# ── Dependency ─────────────────────────────────────────────────────────────────
# Allows tests to inject a custom service without touching module-level state.

def get_service() -> JobService:  # pragma: no cover
    return _default_service


# ── Helpers ────────────────────────────────────────────────────────────────────

def _job_or_404(job_id: str, service: JobService) -> object:
    """Retrieve a job or raise 404."""
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "",
    status_code=202,
    response_model=JobSubmittedOut,
    responses={
        400: {"model": ErrorOut, "description": "Invalid request body."},
        422: {"model": ErrorOut, "description": "Prompt failed validation."},
    },
    summary="Submit a chemistry video request",
    description=(
        "Accepts a chemistry concept prompt, enqueues an async generation job, "
        "and immediately returns the job ID. "
        "Poll `GET /api/v1/videos/{job_id}` to track progress."
    ),
)
async def submit_video_request(
    body: VideoRequestIn,
    background_tasks: BackgroundTasks,
    service: JobService = Depends(get_service),
) -> JobSubmittedOut:
    job = service.submit(prompt=body.prompt, background_tasks=background_tasks)
    return JobSubmittedOut(job_id=job.id, status=job.status)


@router.get(
    "",
    response_model=list[JobSummaryOut],
    summary="List all video generation jobs",
    description="Returns all jobs ordered by submission date, newest first.",
)
async def list_jobs(
    service: JobService = Depends(get_service),
) -> list[JobSummaryOut]:
    jobs = service.list_jobs()
    return [
        JobSummaryOut(
            job_id=j.id,
            prompt=j.prompt,
            status=j.status,
            created_at=j.created_at,
        )
        for j in jobs
    ]


@router.get(
    "/{job_id}",
    response_model=JobDetailOut,
    responses={
        404: {"model": ErrorOut, "description": "Job not found."},
    },
    summary="Get video job status and details",
    description=(
        "Returns the full detail of a job including its current status, "
        "in-progress step description, and error reason (if failed)."
    ),
)
async def get_job_status(
    job_id: str,
    service: JobService = Depends(get_service),
) -> JobDetailOut:
    job = _job_or_404(job_id, service)
    return JobDetailOut(
        job_id=job.id,
        prompt=job.prompt,
        status=job.status,
        progress=job.progress,
        error_reason=job.error_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/{job_id}/artifact",
    response_class=FileResponse,
    responses={
        200: {"content": {"video/mp4": {}}, "description": "The generated video file."},
        400: {"model": ErrorOut, "description": "Video not ready yet."},
        404: {"model": ErrorOut, "description": "Job not found or artifact missing."},
    },
    summary="Download the completed video artifact",
    description=(
        "Streams the MP4 video file once the job is COMPLETED. "
        "Returns 400 if the job is still WAITING or PROCESSING, "
        "and 404 if the job does not exist or the file is missing."
    ),
)
async def get_video_artifact(
    job_id: str,
    service: JobService = Depends(get_service),
) -> FileResponse:
    job = _job_or_404(job_id, service)

    # Guard: job must be COMPLETED to have an artifact.
    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Job failed: {job.error_reason}",
        )
    if job.status in (JobStatus.WAITING, JobStatus.PROCESSING):
        raise HTTPException(
            status_code=400,
            detail=f"Video is not ready yet. Current status: {job.status.value}",
        )

    # Guard: artifact file must exist on disk.
    video_path = job.video_path
    if not video_path or not os.path.isfile(video_path):
        raise HTTPException(
            status_code=404,
            detail="Artifact file not found on disk.",
        )

    filename = f"chemistry_video_{job_id[:8]}.mp4"
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename,
    )
