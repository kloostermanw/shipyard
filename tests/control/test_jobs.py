"""Tests for the prepare/execute job registry."""

from __future__ import annotations

import time

import pytest

from shipyard.control.jobs import Job, JobRegistry, JobNotFoundError


def test_create_and_consume_job() -> None:
    """A registered job can be consumed once by its token."""
    reg = JobRegistry()
    token = reg.create(kind="deploy", params={"app_id": "frontend", "env_id": "prd", "version": "v1.0"})
    assert isinstance(token, str)
    assert len(token) >= 22  # 16 bytes urlsafe base64 → 22 chars

    job = reg.consume(token)
    assert isinstance(job, Job)
    assert job.kind == "deploy"
    assert job.params["version"] == "v1.0"


def test_consume_is_single_use() -> None:
    reg = JobRegistry()
    token = reg.create(kind="sync", params={})
    reg.consume(token)
    with pytest.raises(JobNotFoundError):
        reg.consume(token)


def test_consume_unknown_token_raises() -> None:
    reg = JobRegistry()
    with pytest.raises(JobNotFoundError):
        reg.consume("not-a-real-token")


def test_expired_token_raises(monkeypatch) -> None:
    """Tokens older than ttl_seconds raise JobNotFoundError."""
    reg = JobRegistry(ttl_seconds=120)
    fake_now = [1000.0]
    monkeypatch.setattr("shipyard.control.jobs.time.monotonic", lambda: fake_now[0])

    token = reg.create(kind="deploy", params={})
    fake_now[0] = 1000.0 + 121  # advance past TTL

    with pytest.raises(JobNotFoundError):
        reg.consume(token)


def test_tokens_are_unique() -> None:
    reg = JobRegistry()
    tokens = {reg.create(kind="deploy", params={}) for _ in range(50)}
    assert len(tokens) == 50
