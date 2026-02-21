"""Tests for SSH connection pool and executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shipyard.config.schema import GlobalSettings, ServerConfig, SSHSettings
from shipyard.ssh.connection import SSHConnectionInfo, SSHConnectionPool
from shipyard.ssh.executor import CommandResult, RemoteExecutor


class TestSSHConnectionInfo:
    """Tests for connection info resolution."""

    def test_resolve_connection_info(self) -> None:
        global_settings = GlobalSettings(
            ssh=SSHSettings(
                default_user="deploy",
                key_path="~/.ssh/id_ed25519",
                connect_timeout=10,
                keepalive_interval=30,
            )
        )
        servers = {
            "prod-01": ServerConfig(
                hostname="10.0.1.10",
                port=22,
                user="admin",
                key_path="~/.ssh/prod_key",
            ),
        }
        pool = SSHConnectionPool(global_settings, servers)
        info = pool._resolve_connection_info("prod-01")

        assert info.hostname == "10.0.1.10"
        assert info.port == 22
        assert info.username == "admin"
        assert info.key_path == Path("~/.ssh/prod_key").expanduser()

    def test_resolve_uses_global_defaults(self) -> None:
        global_settings = GlobalSettings(
            ssh=SSHSettings(default_user="deploy", key_path="~/.ssh/id_ed25519")
        )
        servers = {
            "staging": ServerConfig(hostname="10.0.2.10"),
        }
        pool = SSHConnectionPool(global_settings, servers)
        info = pool._resolve_connection_info("staging")

        assert info.username == "deploy"
        assert info.key_path == Path("~/.ssh/id_ed25519").expanduser()

    async def test_unknown_server_raises(self) -> None:
        pool = SSHConnectionPool(GlobalSettings(), {})
        with pytest.raises(KeyError, match="unknown-server"):
            await pool.get_connection("unknown-server")


class TestCommandResult:
    """Tests for CommandResult."""

    def test_success(self) -> None:
        result = CommandResult(stdout="ok", stderr="", exit_status=0)
        assert result.success is True

    def test_failure(self) -> None:
        result = CommandResult(stdout="", stderr="error", exit_status=1)
        assert result.success is False
