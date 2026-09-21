"""
tests/test_api_videos.py
-------------------------
Integration-style tests for the /api/v1/videos router.
Uses FastAPI TestClient with the service dependency overridden to an isolated
in-memory store. No AI calls are made.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.models.job import Job, JobStatus


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/v1/videos
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubmitVideoRequest:
    ENDPOINT = "/api/v1/videos"
    VALID_PROMPT = "Why do atoms form covalent bonds?"

    def test_returns_202(self, client: TestClient):
        resp = client.post(self.ENDPOINT, json={"prompt": self.VALID_PROMPT})
        assert resp.status_code == 202

    def test_response_contains_job_id_and_waiting_status(self, client: TestClient):
        resp = client.post(self.ENDPOINT, json={"prompt": self.VALID_PROMPT})
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "WAITING"
        assert "message" in data

    def test_job_appears_in_store_after_submit(self, client: TestClient, service):
        resp = client.post(self.ENDPOINT, json={"prompt": self.VALID_PROMPT})
        job_id = resp.json()["job_id"]
        assert service.get_job(job_id) is not None

    def test_prompt_too_short_returns_422(self, client: TestClient):
        resp = client.post(self.ENDPOINT, json={"prompt": "pH"})
        assert resp.status_code == 422

    def test_prompt_too_long_returns_422(self, client: TestClient):
        resp = client.post(self.ENDPOINT, json={"prompt": "x" * 501})
        assert resp.status_code == 422

    def test_missing_prompt_returns_422(self, client: TestClient):
        resp = client.post(self.ENDPOINT, json={})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client: TestClient):
        resp = client.post(self.ENDPOINT, content=b"", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    @pytest.mark.parametrize("prompt", [
        "How does the pH scale work?",
        "Why do atoms form covalent bonds?",
        "What is the difference between ionic and covalent bonding?",
    ])
    def test_required_chemistry_prompts_are_accepted(self, client: TestClient, prompt: str):
        resp = client.post(self.ENDPOINT, json={"prompt": prompt})
        assert resp.status_code == 202


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/videos
# ═══════════════════════════════════════════════════════════════════════════════

class TestListJobs:
    ENDPOINT = "/api/v1/videos"

    def test_returns_200_and_empty_list_on_fresh_store(self, client: TestClient):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_submitted_jobs(self, client: TestClient):
        client.post(self.ENDPOINT, json={"prompt": "How does the pH scale work?"})
        client.post(self.ENDPOINT, json={"prompt": "Why do atoms form covalent bonds?"})
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_items_have_required_fields(self, client: TestClient):
        client.post(self.ENDPOINT, json={"prompt": "How does the pH scale work?"})
        item = client.get(self.ENDPOINT).json()[0]
        for field in ("job_id", "prompt", "status", "created_at"):
            assert field in item, f"Missing field: {field}"

    def test_list_sorted_newest_first(self, client: TestClient):
        import time
        client.post(self.ENDPOINT, json={"prompt": "How does the pH scale work?"})
        time.sleep(0.01)
        client.post(self.ENDPOINT, json={"prompt": "Why do atoms form covalent bonds?"})
        items = client.get(self.ENDPOINT).json()
        assert items[0]["prompt"] == "Why do atoms form covalent bonds?"


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/videos/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetJobStatus:
    LIST_ENDPOINT = "/api/v1/videos"

    def _submit(self, client, prompt="Why do atoms form covalent bonds?") -> str:
        return client.post(self.LIST_ENDPOINT, json={"prompt": prompt}).json()["job_id"]

    def test_returns_200_for_existing_job(self, client: TestClient):
        job_id = self._submit(client)
        resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_job(self, client: TestClient):
        resp = client.get(f"{self.LIST_ENDPOINT}/nonexistent-id")
        assert resp.status_code == 404

    def test_new_job_has_waiting_status(self, client: TestClient):
        job_id = self._submit(client)
        data = client.get(f"{self.LIST_ENDPOINT}/{job_id}").json()
        assert data["status"] == "WAITING"

    def test_detail_has_all_required_fields(self, client: TestClient):
        job_id = self._submit(client)
        data = client.get(f"{self.LIST_ENDPOINT}/{job_id}").json()
        for field in ("job_id", "prompt", "status", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    def test_processing_job_shows_progress(self, client: TestClient, service):
        job_id = self._submit(client)
        job = service.get_job(job_id)
        job.mark_processing("Generating voiceover...")
        service.store.save(job)

        data = client.get(f"{self.LIST_ENDPOINT}/{job_id}").json()
        assert data["status"] == "PROCESSING"
        assert data["progress"] == "Generating voiceover..."

    def test_failed_job_shows_error_reason(self, client: TestClient, service):
        job_id = self._submit(client)
        job = service.get_job(job_id)
        job.mark_failed("Prompt is not chemistry-related.")
        service.store.save(job)

        data = client.get(f"{self.LIST_ENDPOINT}/{job_id}").json()
        assert data["status"] == "FAILED"
        assert data["error_reason"] == "Prompt is not chemistry-related."


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/videos/{job_id}/artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetArtifact:
    LIST_ENDPOINT = "/api/v1/videos"

    def _submit(self, client) -> str:
        return client.post(
            self.LIST_ENDPOINT,
            json={"prompt": "How does the pH scale work?"},
        ).json()["job_id"]

    def test_waiting_job_returns_400(self, client: TestClient):
        job_id = self._submit(client)
        resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}/artifact")
        assert resp.status_code == 400

    def test_processing_job_returns_400(self, client: TestClient, service):
        job_id = self._submit(client)
        job = service.get_job(job_id)
        job.mark_processing()
        service.store.save(job)
        resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}/artifact")
        assert resp.status_code == 400

    def test_failed_job_returns_400(self, client: TestClient, service):
        job_id = self._submit(client)
        job = service.get_job(job_id)
        job.mark_failed("Render failed.")
        service.store.save(job)
        resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}/artifact")
        assert resp.status_code == 400

    def test_unknown_job_returns_404(self, client: TestClient):
        resp = client.get(f"{self.LIST_ENDPOINT}/no-such-id/artifact")
        assert resp.status_code == 404

    def test_completed_job_without_file_returns_404(self, client: TestClient, service):
        job_id = self._submit(client)
        job = service.get_job(job_id)
        job.mark_processing()
        job.mark_completed("/nonexistent/path/video.mp4")
        service.store.save(job)
        resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}/artifact")
        assert resp.status_code == 404

    def test_completed_job_with_real_file_returns_200_video(self, client: TestClient, service):
        """Create a real temp file to simulate a completed artifact on disk."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake-video-content")
            tmp_path = f.name

        try:
            job_id = self._submit(client)
            job = service.get_job(job_id)
            job.mark_processing()
            job.mark_completed(tmp_path)
            service.store.save(job)

            resp = client.get(f"{self.LIST_ENDPOINT}/{job_id}/artifact")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "video/mp4"
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /health
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
