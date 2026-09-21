"""
tests/conftest.py
-----------------
Shared pytest fixtures.

Strategy:
  - Each test gets a FRESH, isolated JobService backed by its own in-memory
    store. This prevents state leakage between tests without needing to reset
    any global singleton.
  - The FastAPI TestClient is patched via dependency_overrides so the router
    uses the same isolated service that tests inspect directly.
  - The pipeline is stubbed to a no-op so no AI calls are made.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.store import JobStore
from app.main import app
from app.services import JobService
from app.api.v1.videos import get_service


@pytest.fixture
def store() -> JobStore:
    """A fresh in-memory store for each test."""
    return JobStore()


@pytest.fixture
def service(store: JobStore) -> JobService:
    """A JobService wired to the isolated store, with a no-op pipeline stub."""

    def _stub_pipeline(job, store_):
        # Intentionally does nothing — tests control state transitions manually.
        pass

    return JobService(store=store, pipeline=_stub_pipeline)


@pytest.fixture
def client(service: JobService) -> TestClient:
    """
    TestClient with the get_service dependency overridden to use the
    per-test isolated service.
    """
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()
