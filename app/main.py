"""
app/main.py
-----------
FastAPI application factory.
"""

from fastapi import FastAPI

from app.api.v1.videos import router as videos_router

app = FastAPI(
    title="Chemistry Video Generation API",
    description=(
        "AI-native backend service that generates short educational chemistry "
        "videos on demand. Submit a prompt, track the job, download the video."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(videos_router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"], summary="Health check")
async def health() -> dict:
    return {"status": "ok"}
