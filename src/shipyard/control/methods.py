"""Control-plane RPC methods. Thin wrappers over existing services."""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path as _Path
from typing import Any, Awaitable, Callable

from shipyard.config.schema import ApplicationConfig, ShipyardConfig
from shipyard.control.jobs import JobNotFoundError, JobRegistry
from shipyard.secrets.store import SecretStore, SecretStoreError


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


_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_LOG_LINES = 2000
_MAX_GH_LIMIT = 100

_TEMPLATE_RE = _re.compile(r"\{\{(\w+)\}\}")


def _scan_template_files(local_path: str) -> list[_Path]:
    """Return all .j2 paths under local_path, skipping dotfiles/dot-dirs."""
    root = _Path(local_path).expanduser().resolve()
    if not root.is_dir():
        return []
    result: list[_Path] = []
    for path in root.rglob("*.j2"):
        parts = path.relative_to(root).parts
        if any(p.startswith(".") for p in parts):
            continue
        if path.is_file():
            result.append(path)
    return result


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

    # ---- logs ------------------------------------------------------------

    @staticmethod
    def _cap_trailing(text: str) -> tuple[str, int]:
        """Keep the last _MAX_OUTPUT_BYTES bytes of text."""
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= _MAX_OUTPUT_BYTES:
            return text, 0
        dropped = len(encoded) - _MAX_OUTPUT_BYTES
        truncated = encoded[-_MAX_OUTPUT_BYTES:].decode("utf-8", errors="replace")
        return truncated, dropped

    async def logs_tail(
        self, server_id: str, container: str, lines: int = 200
    ) -> dict[str, Any]:
        if server_id not in self._config.servers:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown server: {server_id}")
        lines = max(1, min(lines, _MAX_LOG_LINES))
        output = await self._executor.docker_logs_tail(server_id, container, lines)
        capped, dropped = self._cap_trailing(output)
        return {"output": capped, "truncated": dropped > 0, "bytes_dropped": dropped}

    # ---- github ----------------------------------------------------------

    async def github_versions(
        self, app_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        app = self._config.applications.get(app_id)
        if app is None:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown application: {app_id}")
        limit = max(1, min(limit, _MAX_GH_LIMIT))
        return await self._github.get_versions(app.github.repo, limit=limit)

    # ---- secrets ---------------------------------------------------------

    async def secrets_is_unlocked(self) -> dict[str, bool]:
        return {"unlocked": self._secret_store.is_unlocked}

    def _require_unlocked(self) -> None:
        if not self._secret_store.is_unlocked:
            raise ControlError(ErrorCode.SECRET_STORE_LOCKED, "Secret store is locked")

    async def secrets_list_keys(self) -> list[str]:
        self._require_unlocked()
        return self._secret_store.list_keys()

    async def secrets_get(self, key: str) -> dict[str, str]:
        self._require_unlocked()
        try:
            return {"value": self._secret_store.get(key)}
        except SecretStoreError as exc:
            raise ControlError(ErrorCode.NOT_FOUND, str(exc))

    async def secrets_set(self, key: str, value: str) -> dict[str, Any]:
        self._require_unlocked()
        created = key not in self._secret_store.list_keys()
        self._secret_store.set(key, value)
        return {"ok": True, "created": created}

    async def secrets_delete(self, key: str) -> dict[str, bool]:
        self._require_unlocked()
        try:
            self._secret_store.delete(key)
        except SecretStoreError as exc:
            raise ControlError(ErrorCode.NOT_FOUND, str(exc))
        return {"ok": True}

    # ---- templates -------------------------------------------------------

    def _env_local_path(self, app_id: str, env_id: str) -> str:
        app = self._config.applications.get(app_id)
        if app is None:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown application: {app_id}")
        env = app.environments.get(env_id)
        if env is None:
            raise ControlError(
                ErrorCode.NOT_FOUND, f"Unknown environment: {app_id}/{env_id}"
            )
        if env.local_path is None:
            raise ControlError(
                ErrorCode.NOT_FOUND,
                f"Environment {app_id}/{env_id} has no local-path configured",
            )
        return env.local_path

    def _classify_template_variables(
        self, variables: set[str]
    ) -> tuple[str, list[str]]:
        """Return (resolution, missing_variables)."""
        if not variables:
            return "PLAIN", []
        if not self._secret_store.is_unlocked:
            return "MISSING", sorted(variables)
        secrets = set(self._secret_store.list_keys())
        missing = sorted(variables - secrets)
        if missing:
            return "MISSING", missing
        return "LINKED", []

    async def templates_list(
        self, app_id: str, env_id: str
    ) -> list[dict[str, Any]]:
        local_path = self._env_local_path(app_id, env_id)
        root = _Path(local_path).expanduser().resolve()
        result: list[dict[str, Any]] = []
        for path in _scan_template_files(local_path):
            text = path.read_text(encoding="utf-8", errors="replace")
            variables = set(_TEMPLATE_RE.findall(text))
            resolution, missing = self._classify_template_variables(variables)
            result.append(
                {
                    "path": str(path.relative_to(root)),
                    "resolution": resolution,
                    "missing_variables": missing,
                    "variable_count": len(variables),
                }
            )
        return result

    # ---- deploy ----------------------------------------------------------

    def _current_versions_for_env(
        self, app_id: str, env_id: str
    ) -> list[str]:
        env_cache = self._container_cache.get(app_id, {}).get(env_id, [])
        return [c.get("image", "") for c in env_cache]

    @staticmethod
    def _cap_leading(text: str) -> tuple[str, int]:
        """Keep the LAST _MAX_OUTPUT_BYTES bytes (drop the beginning)."""
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= _MAX_OUTPUT_BYTES:
            return text, 0
        dropped = len(encoded) - _MAX_OUTPUT_BYTES
        kept = encoded[-_MAX_OUTPUT_BYTES:].decode("utf-8", errors="replace")
        return kept, dropped

    async def deploy_prepare(
        self, app_id: str, env_id: str, version: str
    ) -> dict[str, Any]:
        app = self._config.applications.get(app_id)
        if app is None:
            raise ControlError(ErrorCode.NOT_FOUND, f"Unknown application: {app_id}")
        env = app.environments.get(env_id)
        if env is None:
            raise ControlError(
                ErrorCode.NOT_FOUND, f"Unknown environment: {app_id}/{env_id}"
            )
        summary = {
            "app_id": app_id,
            "env_id": env_id,
            "server": env.server,
            "path": env.path,
            "version": version,
            "containers": list(env.containers),
            "current_versions": self._current_versions_for_env(app_id, env_id),
        }
        token = self._jobs.create(
            kind="deploy",
            params={
                "app_id": app_id,
                "env_id": env_id,
                "version": version,
            },
        )
        return {"token": token, "summary": summary}

    async def deploy_execute(self, token: str) -> dict[str, Any]:
        try:
            job = self._jobs.consume(token)
        except JobNotFoundError:
            raise ControlError(
                ErrorCode.INVALID_CONFIRMATION_TOKEN,
                "Confirmation token is unknown, expired, or already used",
            )
        if job.kind != "deploy":
            raise ControlError(
                ErrorCode.INVALID_CONFIRMATION_TOKEN,
                "Token is not for a deploy",
            )

        app_id = job.params["app_id"]
        env_id = job.params["env_id"]
        version = job.params["version"]
        env_config = self._config.applications[app_id].environments[env_id]

        result = await self._deployer.run_to_completion(
            app_id, env_id, version, env_config
        )
        combined = (result.stdout or "") + (result.stderr or "")
        capped, dropped = self._cap_leading(combined)
        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "output": capped,
            "truncated": dropped > 0,
            "bytes_dropped": dropped,
        }

    # ---- templates -------------------------------------------------------

    async def templates_inspect(
        self, app_id: str, env_id: str, path: str
    ) -> dict[str, Any]:
        local_path = self._env_local_path(app_id, env_id)
        root = _Path(local_path).expanduser().resolve()
        target = (root / path).resolve()
        if not target.is_file():
            raise ControlError(ErrorCode.NOT_FOUND, f"Template not found: {path}")
        try:
            target.relative_to(root)
        except ValueError:
            raise ControlError(ErrorCode.NOT_FOUND, f"Template outside local-path: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")

        known_keys = (
            set(self._secret_store.list_keys()) if self._secret_store.is_unlocked else set()
        )

        entries: list[dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, raw_value = stripped.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()
            match = _TEMPLATE_RE.fullmatch(raw_value)
            if match:
                secret_name = match.group(1)
                if secret_name in known_keys:
                    entries.append(
                        {"key": key, "resolution": "LINKED", "secret_name": secret_name}
                    )
                else:
                    entries.append(
                        {
                            "key": key,
                            "resolution": "MISSING",
                            "secret_name": secret_name,
                        }
                    )
            else:
                # Plain literal value; mask, never include the literal in output.
                entries.append({"key": key, "resolution": "PLAIN"})
        return {"path": path, "entries": entries}
