# 🧪 CVCC Backend — AI Chemistry Video Generation Service

A backend prototype that generates short educational chemistry videos on demand.  
Clients submit a chemistry concept, the backend processes it asynchronously through an AI pipeline (script → voiceover → Manim animation), and returns a downloadable `.mp4`.

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
  ├── AI Pipeline (app/services/pipeline.py)   ← pluggable
  │     ├── Step 0: validate_prompt            (LLM / keyword guard)
  │     ├── Step 1: gen_scripts                (LLM → structured JSON)
  │     ├── Step 2: gen_speech                 (TTS → .mp3 per scene)
  │     ├── Step 3: gen_code                   (LLM → Manim Python)
  │     └── Step 4: render + retry loop        (subprocess + auto-fix)
  │
  ├── JobStore (app/core/store.py)             ← thread-safe in-memory
  │
  └── Artifacts (artifacts/)                  ← .mp4 files on disk
```

### Job Lifecycle

```
WAITING ──► PROCESSING ──► COMPLETED
               │
               └──────────► FAILED  (validation error / max retries exceeded)
```

Each state transition is an explicit method on the `Job` model (`mark_processing`, `mark_completed`, `mark_failed`), making it impossible to skip steps silently.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Python 3.11+ · FastAPI · Uvicorn |
| Video engine | Manim Community Edition |
| LLM | Google Gemini (free tier) |
| TTS / Voiceover | Edge TTS |
| Persistence (MVP) | In-memory `JobStore` (thread-safe) |
| Testing | pytest · pytest-asyncio · httpx |

---

## Supported Chemistry Topics (MVP Scope)

The pipeline is validated against these three required queries:

1. *How does the pH scale work?*
2. *Why do atoms form covalent bonds?*
3. *What is the difference between ionic and covalent bonding?*

Prompts outside chemistry are rejected early (Step 0) with a clear `FAILED` status and reason.  
The validator and prompt strategy are modular — adding Physics or Biology topics requires only a new `TopicStrategy` class.

---

## Project Structure

```
cvcc_backend/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── api/
│   │   └── v1/
│   │       └── videos.py        # All 4 API endpoints
│   ├── models/
│   │   └── job.py               # Job domain model + state transitions
│   ├── schemas/
│   │   └── job.py               # Pydantic request/response schemas
│   ├── core/
│   │   └── store.py             # Thread-safe in-memory job store
│   └── services/
│       └── __init__.py          # JobService (pipeline injection point)
├── tests/
│   ├── conftest.py              # Isolated fixtures (no global state)
│   ├── test_job_model.py        # Domain model unit tests
│   ├── test_store.py            # Store unit tests
│   └── test_api_videos.py       # API endpoint integration tests
├── artifacts/                   # Generated .mp4 files (git-ignored)
├── pyproject.toml
├── spec.md                      # Full product specification
└── README.md
```

---

## Quickstart

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

> **Manim system dependencies** (Cairo, FFmpeg, LaTeX) must also be installed.  
> See the [Manim installation guide](https://docs.manim.community/en/stable/installation.html).

### 2. Configure environment

```bash
cp .env.example .env
# Add your GEMINI_API_KEY
```

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

API docs available at: **http://localhost:8000/docs**

### 4. Run tests

```bash
pytest tests/ -v
```

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
  "progress": "Generating Manim animation code...",
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

---

## Reliability Design

LLM and media-generation tools are non-deterministic by nature.  
The pipeline is engineered to produce consistent results across repeated runs:

| Problem | Solution |
|---|---|
| LLM returns wrong JSON structure | Structured output with schema validation; retry on parse failure |
| Manim code has syntax errors | Subprocess stderr is fed back to LLM for auto-fix (max 3 retries) |
| TTS produces silence or empty file | File-size and duration guards before next step |
| Prompt is off-topic | Step 0 validation rejects early — clean FAILED state, no wasted AI calls |
| Subprocess hangs indefinitely | Configurable timeout on `subprocess.run`; FAILED with "timeout" reason |
| Partial pipeline failure | Each step updates `job.progress` — exact failure point is always visible |

---

## Design Decisions & Tradeoffs

**In-memory store over SQLite/Postgres**  
Keeps the MVP small. The `JobStore` exposes a clean interface (`save`, `get`, `list_all`) — swapping it for a DB adapter requires zero changes to the service or router layers.

**BackgroundTasks over Celery**  
Single-process deployment is sufficient for a prototype. The pipeline callable is injected into `JobService`, so replacing it with a Celery task is a one-line change.

**Manim over a hosted video API**  
Manim produces deterministic, high-quality mathematical animations with chemistry-specific LaTeX support — far more educationally valuable than generic stock video. The tradeoff is a heavier local dependency footprint.

**Schema ≠ Domain model**  
`app/schemas/job.py` (API contract) and `app/models/job.py` (internal state) are deliberately separate. This prevents a DB refactor from accidentally breaking the public API.
