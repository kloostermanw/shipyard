"""Control-plane RPC methods. Thin wrappers over existing services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Awaitable, Callable

from shipyard.config.schema import ApplicationConfig, ShipyardConfig
from shipyard.control.jobs import JobRegistry
from shipyard.secrets.store import SecretStore


class ErrorCode(IntEnum):
    SHIPYARD_NOT_RUNNING = -32001
    SECRET_STORE_LOCKED = -32002
    INVALID_CONFIRMATION_TOKEN = -32003
    SSH_ERROR = -32004
    NOT_FOUND = -32005
    VALIDATION_ERROR = -32006
    INTERNAL_ERROR = -32099


@dataclass
class ControlError(Exception):
    code: ErrorCode
    message: str

    def __str__(self) -> str:
        return f"[{self.code.name}] {self.message}"


class ControlMethods:
    """Bundle of RPC method handlers. Constructed once per running TUI."""

    def __init__(
        self,
        config: ShipyardConfig,
        ssh_pool: Any,
        deployer: Any,
        syncer: Any,
        github_client: Any,
        executor: Any,
        secret_store: SecretStore,
        container_cache: dict[str, dict[str, list[dict[str, str]]]],
        server_container_cache: dict[str, list[dict[str, str]]],
        jobs: JobRegistry | None = None,
        refresh_status_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._ssh_pool = ssh_pool
        self._deployer = deployer
        self._syncer = syncer
        self._github = github_client
        self._executor = executor
        self._secret_store = secret_store
        self._container_cache = container_cache
        self._server_container_cache = server_container_cache
        self._jobs = jobs or JobRegistry()
        self._refresh_status_callback = refresh_status_callback

    # ---- apps ------------------------------------------------------------

    def _serialize_app(self, app_id: str, app: ApplicationConfig) -> dict[str, Any]:
        return {
            "id": app_id,
            "name": app.name,
            "description": app.description,
            "github": {"repo": app.github.repo, "track": app.github.track},
            "environments": [
                {
                    "id": env_id,
                    "server": env.server,
                    "path": env.path,
                    "has_local_path": env.local_path is not None,
                }
                for env_id, env in app.environments.items()
            ],
        }

    async def apps_list(self) -> list[dict[str, Any]]:
        return [
            self._serialize_app(app_id, app)
            for app_id, app in self._config.applications.items()
        ]

    async def apps_get(self, app_id: str) -> dict[str, Any]:
        app = self._config.applications.get(app_id)
        if app is None:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown application: {app_id}")
        detail = self._serialize_app(app_id, app)
        env_cache = self._container_cache.get(app_id, {})
        for env_dict in detail["environments"]:
            env_id = env_dict["id"]
            env_dict["containers"] = list(env_cache.get(env_id, []))
        return detail

    async def apps_refresh_status(self) -> dict[str, Any]:
        if self._refresh_status_callback is None:
            raise ControlError(
                ErrorCode.INTERNAL_ERROR,
                "Refresh callback not wired (control server misconfigured)",
            )
        await self._refresh_status_callback()
        return {"ok": True}

    # ---- servers ---------------------------------------------------------

    async def servers_list(self) -> list[dict[str, Any]]:
        result = []
        for sid, server in self._config.servers.items():
            result.append(
                {
                    "id": sid,
                    "hostname": server.hostname,
                    "port": server.port,
                    "user": server.user or self._config.global_.ssh.default_user,
                    "description": server.description,
                }
            )
        return result

    async def servers_get(self, server_id: str) -> dict[str, Any]:
        server = self._config.servers.get(server_id)
        if server is None:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown server: {server_id}")
        reachable = await self._ssh_pool.check_connection(server_id)
        containers = list(self._server_container_cache.get(server_id, []))
        return {
            "id": server_id,
            "hostname": server.hostname,
            "port": server.port,
            "user": server.user or self._config.global_.ssh.default_user,
            "description": server.description,
            "reachable": reachable,
            "containers": containers,
        }

    # ---- containers ------------------------------------------------------

    async def containers_list(self, server_id: str) -> list[dict[str, str]]:
        if server_id not in self._config.servers:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown server: {server_id}")
        return list(self._server_container_cache.get(server_id, []))
