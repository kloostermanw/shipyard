"""Append-only audit log with size-based rotation."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_DEFAULT_GENERATIONS = 5


class AuditLog:
    """JSON-lines audit log. Each write is a single line; flushes after each call."""

    def __init__(
        self,
        path: Path,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        max_generations: int = _DEFAULT_GENERATIONS,
    ) -> None:
        self._path = Path(path).expanduser()
        self._max_bytes = max_bytes
        self._max_generations = max_generations
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        method: str,
        params_summary: dict[str, Any],
        result_code: int,
        peer: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "method": method,
            "params_summary": params_summary,
            "result_code": result_code,
        }
        if peer is not None:
            record["peer"] = peer
        line = json.dumps(record) + "\n"
        self._rotate_if_needed(len(line.encode("utf-8")))
        existed = self._path.exists()
        with open(self._path, "ab") as f:
            f.write(line.encode("utf-8"))
        if not existed:
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current = self._path.stat().st_size if self._path.exists() else 0
        except OSError:
            current = 0
        if current + incoming_bytes <= self._max_bytes:
            return
        # Rotate: audit.log.(N-1) → audit.log.N, ..., audit.log → audit.log.1
        for i in range(self._max_generations, 0, -1):
            src = self._path.parent / f"{self._path.name}.{i - 1}" if i > 1 else self._path
            dst = self._path.parent / f"{self._path.name}.{i}"
            if i == self._max_generations and dst.exists():
                try:
                    dst.unlink()
                except OSError:
                    pass
            if src.exists():
                try:
                    src.rename(dst)
                except OSError:
                    pass
