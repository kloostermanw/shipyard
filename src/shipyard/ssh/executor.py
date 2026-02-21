"""Remote command execution over SSH."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

import asyncssh


@dataclass
class CommandResult:
    """Result of a remote command execution."""

    stdout: str
    stderr: str
    exit_status: int

    @property
    def success(self) -> bool:
        return self.exit_status == 0


class RemoteExecutor:
    """Execute commands on a remote server via an SSH connection."""

    def __init__(self, conn: asyncssh.SSHClientConnection) -> None:
        self._conn = conn

    async def run(self, command: str, timeout: int = 30) -> CommandResult:
        """Run a command and return the complete result."""
        result = await self._conn.run(command, timeout=timeout)
        return CommandResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_status=result.exit_status if result.exit_status is not None else -1,
        )

    async def stream(self, command: str) -> AsyncIterator[str]:
        """Stream stdout line-by-line from a long-running command."""
        process = await self._conn.create_process(command)
        if process.stdout is None:
            return
        async for line in process.stdout:
            yield line.rstrip("\n")
