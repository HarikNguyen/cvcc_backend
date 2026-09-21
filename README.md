# 🧪 CVCC Backend — AI Chemistry Video Generation Service

A backend prototype that generates short educational chemistry videos (up to 180s) on demand.  
Clients submit a chemistry concept, the backend processes it asynchronously through an AI pipeline (Groq JSON script → Google Cloud TTS → Manim rendering + FFmpeg audio mix), and returns a downloadable `.mp4`.

---

## Architecture Overview

```
Client
  │
  │  POST /api/v1/videos          ← submit prompt
  │  GET  /api/v1/videos          ← list all jobs
  │  GET  /api/v1/videos/{id}     ← poll status
  │  GET  /api/v1/videos/{id}/artifact  ← download video
  │
  ▼
FastAPI (app/main.py)
  │
  ├── Router (app/api/v1/videos.py)
  │     └── Validates HTTP contract, delegates to service
  │
  ├── JobService (app/services/__init__.py)
  │     └── Creates Job, enqueues BackgroundTask
  │
  ├── AI Pipeline (app/services/__init__.py / real_pipeline)
  │     ├── Step 1: gen_scripts  (Groq LLM → strict JSON script)
  │     ├── Step 2: gen_speech   (Google Cloud TTS → .mp3 per scene, mutagen measures duration)
  │     └── Step 3: gen_code     (Programmatic script translation → Manim subprocess → FFmpeg mix)
  │
  ├── JobStore (app/core/store.py)             ← thread-safe in-memory
  │
  └── artifacts/                               ← Generated .mp4 files
```

### Job Lifecycle

```
WAITING ──► PROCESSING ──► COMPLETED
               │
               └──────────► FAILED  (pipeline error / max retries exceeded)
```

Each state transition is an explicit method on the `Job` model (`mark_processing`, `mark_completed`, `mark_failed`), ensuring deterministic and trackable status updates.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Python 3.13 · FastAPI · Uvicorn · Pydantic |
| Script Generation | Groq API (`llama-3.1-70b-versatile`) in JSON mode |
| TTS / Voiceover | Google Cloud Text-to-Speech (`en-US-Journey-F`) |
| Video Engine | Manim Community Edition (Vertical 9:16 format) |
| Audio/Muxing | FFmpeg · Mutagen |
| Persistence (MVP) | In-memory `JobStore` (thread-safe) |
| Testing | pytest · pytest-mock · fastapi-testclient (100% green suite) |

---

## Supported Chemistry Topics (MVP Scope)

The pipeline is validated against these three required queries:

1. *How does the pH scale work?*
2. *Why do atoms form covalent bonds?*
3. *What is the difference between ionic and covalent bonding?*

---

## AI Pipeline Design Details

1. **gen_scripts (Groq)**: The LLM acts as a chemistry teacher. It is provided a strict catalog of 17 supported Manim visual effects (e.g., `FORMULA_DISPLAY`, `BOND_FORMATION`, `PH_SCALE`). It outputs a Pydantic-validated JSON containing scene sequence, exact effect keywords, and TTS narration. Self-correction kicks in if it uses invalid effects.
2. **gen_speech (Google TTS)**: Connects to GCP. Generates high-quality mp3s for each scene. `mutagen` is used to measure the exact millisecond duration of the spoken audio so the visual effects stay in sync.
3. **gen_code (Determinism via Code-Gen)**: Unlike typical AI coding agents, the LLM *does not write raw Manim Python*. Instead, a programmatic generator maps the JSON scenes to exact `play_effect()` calls inside a reusable `ChemistryScene` framework. This guarantees zero SyntaxErrors and 100% compile success.
4. **Fallback Mechanism**: If the Manim subprocess crashes (e.g., LaTeX rendering error), `gen_code` retries with a safe, text-only fallback scene, ensuring the user *always* receives a valid MP4 video.

---

## Quickstart

### 1. Install dependencies

```bash
# Optional: Use mise or uv for python 3.13 environments
pip install -e ".[dev]"
```

> **System requirements**: 
> - [Manim Community dependencies](https://docs.manim.community/en/stable/installation.html) (Cairo, LaTeX, Pango)
> - **FFmpeg** is required for audio muxing and Manim rendering.

### 2. Configure environment variables

```bash
cp .env.example .env
```
Edit `.env`:
- `GROQ_API_KEY`: Your Groq API key for Llama 3.1 70B.
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to your GCP service account JSON key for TTS.

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

API docs available at: **http://localhost:8000/docs**

### 4. Run tests

```bash
python -m pytest tests/ -v
```
*(All API, Job, Store, and Pipeline tests are fully mocked and run in seconds without hitting real external services).*

---

## API Reference

### `POST /api/v1/videos` — Submit a request

```bash
curl -X POST http://localhost:8000/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How does the pH scale work?"}'
```

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "WAITING",
  "message": "Video generation job submitted successfully."
}
```

---

### `GET /api/v1/videos` — List all jobs

```bash
curl http://localhost:8000/api/v1/videos
```

```json
[
  {
    "job_id": "123e4567-e89b-12d3-a456-426614174000",
    "prompt": "How does the pH scale work?",
    "status": "COMPLETED",
    "created_at": "2026-09-21T10:00:00Z"
  }
]
```

---

### `GET /api/v1/videos/{job_id}` — Poll job status

```bash
curl http://localhost:8000/api/v1/videos/123e4567-e89b-12d3-a456-426614174000
```

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "prompt": "How does the pH scale work?",
  "status": "PROCESSING",
  "progress": "Rendering video (Manim)...",
  "error_reason": null,
  "created_at": "2026-09-21T10:00:00Z",
  "updated_at": "2026-09-21T10:00:15Z"
}
```

---

### `GET /api/v1/videos/{job_id}/artifact` — Download video

```bash
curl -OJ http://localhost:8000/api/v1/videos/123e4567-e89b-12d3-a456-426614174000/artifact
```

Returns `video/mp4`. Errors:
- `400` — Job not yet completed (WAITING / PROCESSING) or FAILED
- `404` — Job not found or artifact file missing from disk
