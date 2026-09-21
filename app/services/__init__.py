"""
app/services/__init__.py
-------------------------
Business logic layer coordinating the background video generation pipeline.
Injects the real AI pipeline components (Groq, TTS, Manim).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from app.core.store import JobStore, job_store
from app.models.job import Job, JobStatus
from app.pipeline.gen_scripts import generate_script
from app.pipeline.gen_speech import generate_speech
from app.pipeline.gen_code import generate_video

logger = logging.getLogger(__name__)

# Type alias for the pipeline runner function injected into JobService
PipelineCallable = Callable[[str, str, JobStore], Coroutine[None, None, None]]


async def real_pipeline(job_id: str, prompt: str, store: JobStore) -> None:
    """
    The actual AI pipeline executor.
    Runs asynchronously in the background. Coordinates:
      1. Script generation (Groq)
      2. Speech synthesis (Google Cloud TTS)
      3. Video rendering + Audio muxing (Manim + FFmpeg)
    """
    job = store.get(job_id)
    if not job:
        logger.error(f"Pipeline started for unknown job {job_id}")
        return

    # Helper to update progress and save
    def _update_progress(msg: str):
        job.advance_progress(msg)
        store.save(job)
        logger.info(f"Job {job_id}: {msg}")

    try:
        # Mark as processing
        job.mark_processing()
        store.save(job)
        logger.info(f"Job {job_id} started processing.")

        # ── Step 1: Generate Script ───────────────────────────────────────
        _update_progress("Generating video script (Groq)...")
        # Run synchronous generate_script in a threadpool to not block the event loop
        script = await asyncio.to_thread(generate_script, prompt, _update_progress)

        # ── Step 2: Generate Speech ───────────────────────────────────────
        _update_progress("Generating voiceover (Google Cloud TTS)...")
        speech = await asyncio.to_thread(generate_speech, script, job_id, None, _update_progress)

        # ── Step 3: Render Video ──────────────────────────────────────────
        _update_progress("Rendering video (Manim)...")
        final_video_path = await asyncio.to_thread(generate_video, script, speech, job_id, None, None, _update_progress)

        # ── Success ───────────────────────────────────────────────────────
        job.mark_completed(final_video_path)
        store.save(job)
        logger.info(f"Job {job_id} COMPLETED successfully.")

    except Exception as e:
        logger.exception(f"Job {job_id} FAILED during pipeline execution.")
        job.mark_failed(f"{type(e).__name__}: {str(e)}")
        store.save(job)


class JobService:
    """
    Manages job lifecycle and handles API requests.
    """
    def __init__(self, store: JobStore, pipeline_runner: PipelineCallable):
        self.store = store
        self._pipeline_runner = pipeline_runner

    def submit(self, prompt: str, background_tasks) -> Job:
        job = Job(prompt=prompt)
        self.store.save(job)

        # Offload the heavy pipeline to FastAPI's background task queue
        background_tasks.add_task(self._pipeline_runner, job.id, prompt, self.store)
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.store.get(job_id)

    def list_jobs(self) -> list[Job]:
        return self.store.list_all()

    def get_video_path(self, job_id: str) -> str | None:
        job = self.store.get(job_id)
        if not job or job.status != JobStatus.COMPLETED:
            return None
        return job.video_path


# Singleton instance used by the FastAPI router.
# Using real_pipeline instead of _noop_pipeline now.
job_service = JobService(job_store, real_pipeline)
