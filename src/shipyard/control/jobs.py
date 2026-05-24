"""In-memory job registry for prepare/execute confirmation tokens."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any


_DEFAULT_TTL_SECONDS = 120


class JobNotFoundError(KeyError):
    """Raised when a token is unknown, expired, or already consumed."""


@dataclass
class Job:
    kind: str  # e.g. "deploy", "sync"
    params: dict[str, Any]
    created_at: float  # time.monotonic() snapshot


class JobRegistry:
    """Thread-unsafe, in-memory token → Job map. Single-use, time-bound."""

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._jobs: dict[str, Job] = {}

    def create(self, kind: str, params: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(16)
        self._jobs[token] = Job(kind=kind, params=params, created_at=time.monotonic())
        return token

    def consume(self, token: str) -> Job:
        job = self._jobs.pop(token, None)
        if job is None:
            raise JobNotFoundError(token)
        if time.monotonic() - job.created_at > self._ttl:
            raise JobNotFoundError(token)
        return job
