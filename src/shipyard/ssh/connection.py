"""AsyncSSH connection pool for managing persistent SSH connections."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import asyncssh

from shipyard.config.schema import GlobalSettings, ServerConfig


@dataclass
class SSHConnectionInfo:
    """Resolved connection parameters for a server."""

    hostname: str
    port: int
    username: str
    key_path: Path
    known_hosts: str | None
    connect_timeout: int
    keepalive_interval: int


class SSHConnectionPool:
    """Manages a pool of persistent SSH connections to servers.

    Connections are created lazily and cached. Per-server locks
    prevent duplicate connections during concurrent access.
    """

    def __init__(
        self, global_settings: GlobalSettings, servers: dict[str, ServerConfig]
    ) -> None:
        self._global = global_settings
        self._servers = servers
        self._connections: dict[str, asyncssh.SSHClientConnection] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _resolve_connection_info(self, server_id: str) -> SSHConnectionInfo:
        """Merge server-specific overrides with global SSH defaults."""
        server = self._servers[server_id]
        return SSHConnectionInfo(
            hostname=server.hostname,
            port=server.port,
            username=server.user or self._global.ssh.default_user,
            key_path=Path(server.key_path or self._global.ssh.key_path).expanduser(),
            known_hosts=None,  # Use default known_hosts handling
            connect_timeout=self._global.ssh.connect_timeout,
            keepalive_interval=self._global.ssh.keepalive_interval,
        )

    async def _create_connection(self, server_id: str) -> asyncssh.SSHClientConnection:
        """Create a new SSH connection to the specified server."""
        info = self._resolve_connection_info(server_id)
        conn = await asyncssh.connect(
            host=info.hostname,
            port=info.port,
            username=info.username,
            client_keys=[str(info.key_path)],
            known_hosts=info.known_hosts,
            keepalive_interval=info.keepalive_interval,
            connect_timeout=info.connect_timeout,
        )
        return conn

    async def get_connection(self, server_id: str) -> asyncssh.SSHClientConnection:
        """Get or create a cached SSH connection.

        Thread-safe via per-server asyncio locks. Returns an existing
        connection if still alive, otherwise creates a new one.
        """
        if server_id not in self._servers:
            raise KeyError(f"Unknown server: {server_id}")

        if server_id not in self._locks:
            self._locks[server_id] = asyncio.Lock()

        async with self._locks[server_id]:
            conn = self._connections.get(server_id)
            if conn is not None and not conn.is_closed:
                return conn
            conn = await self._create_connection(server_id)
            self._connections[server_id] = conn
            return conn

    async def check_connection(self, server_id: str) -> bool:
        """Test if we can reach the server. Returns True if healthy."""
        try:
            conn = await self.get_connection(server_id)
            result = await conn.run("echo ok", timeout=5)
            return result.exit_status == 0
        except (OSError, asyncssh.Error):
            # Remove broken connection from cache
            self._connections.pop(server_id, None)
            return False

    async def close_all(self) -> None:
        """Close all cached connections."""
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
