"""Deployment executor - runs rerun.sh over SSH."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator

from shipyard.config.schema import ApplicationConfig, EnvironmentConfig
from shipyard.ssh.connection import SSHConnectionPool
from shipyard.ssh.executor import RemoteExecutor


class DeployStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class DeployEvent:
    """Event emitted during deployment for UI updates."""

    status: DeployStatus
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DeployResult:
    """Final result of a deployment."""

    app_id: str
    env_id: str
    version: str
    success: bool
    exit_code: int
    started_at: datetime
    completed_at: datetime


class Deployer:
    """Executes deployments by running rerun.sh on remote servers.

    Deployment is simple:
    1. SSH to the environment's server
    2. cd to the environment's config path
    3. Run ./rerun.sh <version>
    4. Stream output back
    5. Report success/failure based on exit code
    """

    def __init__(self, ssh_pool: SSHConnectionPool) -> None:
        self._ssh_pool = ssh_pool

    async def deploy(
        self,
        app_id: str,
        env_id: str,
        version: str,
        env_config: EnvironmentConfig,
    ) -> AsyncIterator[DeployEvent]:
        """Execute a deployment, yielding events for UI updates."""
        started_at = datetime.now()
        server_id = env_config.server
        deploy_path = env_config.path

        yield DeployEvent(
            status=DeployStatus.RUNNING,
            message=f"Connecting to {server_id}...",
        )

        try:
            conn = await self._ssh_pool.get_connection(server_id)
            executor = RemoteExecutor(conn)

            yield DeployEvent(
                status=DeployStatus.RUNNING,
                message=f"Running ./rerun.sh {version} in {deploy_path}",
            )

            # Stream the deploy script output
            command = f"cd {deploy_path} && ./rerun.sh {version}"
            process = await conn.create_process(command)

            # Stream stdout
            if process.stdout is not None:
                async for line in process.stdout:
                    yield DeployEvent(
                        status=DeployStatus.RUNNING,
                        message=line.rstrip("\n"),
                    )

            # Wait for process to complete
            await process.wait()
            exit_code = process.exit_status if process.exit_status is not None else -1

            if exit_code == 0:
                yield DeployEvent(
                    status=DeployStatus.SUCCESS,
                    message=f"Deploy completed successfully (exit code 0)",
                )
            else:
                # Include stderr in failure message
                stderr = ""
                if process.stderr is not None:
                    stderr = process.stderr.read() if hasattr(process.stderr, "read") else ""
                yield DeployEvent(
                    status=DeployStatus.FAILED,
                    message=f"Deploy failed (exit code {exit_code})"
                    + (f": {stderr}" if stderr else ""),
                )

        except Exception as exc:
            yield DeployEvent(
                status=DeployStatus.FAILED,
                message=f"Deploy error: {exc}",
            )
