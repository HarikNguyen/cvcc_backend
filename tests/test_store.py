"""
tests/test_store.py
--------------------
Unit tests for the in-memory JobStore.
"""

from __future__ import annotations

import pytest

from app.core.store import JobStore
from app.models.job import Job


@pytest.fixture
def store() -> JobStore:
    return JobStore()


class TestJobStoreSave:
    def test_save_returns_the_job(self, store):
        job = Job(prompt="test")
        result = store.save(job)
        assert result is job

    def test_len_increases_after_save(self, store):
        assert len(store) == 0
        store.save(Job(prompt="test"))
        assert len(store) == 1

    def test_save_overwrites_on_same_id(self, store):
        job = Job(prompt="original")
        store.save(job)
        job.prompt = "updated"
        store.save(job)
        assert len(store) == 1
        assert store.get(job.id).prompt == "updated"


class TestJobStoreGet:
    def test_get_returns_job_by_id(self, store):
        job = Job(prompt="test")
        store.save(job)
        assert store.get(job.id) is job

    def test_get_returns_none_for_unknown_id(self, store):
        assert store.get("nonexistent-id") is None


class TestJobStoreListAll:
    def test_list_all_empty(self, store):
        assert store.list_all() == []

    def test_list_all_returns_all_jobs(self, store):
        j1 = Job(prompt="a")
        j2 = Job(prompt="b")
        store.save(j1)
        store.save(j2)
        ids = {j.id for j in store.list_all()}
        assert j1.id in ids and j2.id in ids

    def test_list_all_sorted_newest_first(self, store):
        import time
        j1 = Job(prompt="first")
        store.save(j1)
        time.sleep(0.01)
        j2 = Job(prompt="second")
        store.save(j2)
        result = store.list_all()
        assert result[0].id == j2.id  # newest first


class TestJobStoreClear:
    def test_clear_empties_store(self, store):
        store.save(Job(prompt="test"))
        store.clear()
        assert len(store) == 0
