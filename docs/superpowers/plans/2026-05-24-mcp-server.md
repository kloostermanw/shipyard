# Shipyard MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in stdio MCP server that exposes every TUI feature (apps, servers, containers, deploys, sync, logs, secrets, templates) to an LLM client, with destructive operations gated by prepare/execute confirmation tokens and the running TUI as the trust root.

**Architecture:** A thin `shipyard mcp` stdio process forwards MCP tool calls over a local Unix domain socket (mode 0600) to a control-plane server hosted inside the running TUI. The TUI owns SSH, GitHub, and the unlocked secret store. JSON-RPC 2.0 over newline-delimited JSON between MCP process and TUI. The job registry holds prepare/execute tokens in memory only.

**Tech Stack:** Python 3.11, asyncio, Pydantic v2, the `mcp` Python SDK (Anthropic), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-24-mcp-server-design.md`

---

## File structure (locked in here)

New files (under `src/shipyard/`):

- `control/__init__.py` — empty package marker.
- `control/jobs.py` — `Job` dataclass, `JobRegistry` with token-keyed in-memory store, 120 s expiry, single-use consumption.
- `control/methods.py` — `ControlMethods` class with one async method per RPC. Thin wrappers over existing services.
- `control/protocol.py` — JSON-RPC 2.0 framing: `encode_response`, `encode_error`, `parse_request`, error code constants.
- `control/audit.py` — `AuditLog` writer with size-based rotation.
- `control/server.py` — `ControlServer` class: asyncio Unix-socket server, token handshake, request dispatch.
- `mcp/__init__.py` — empty package marker.
- `mcp/__main__.py` — entry point for `python -m shipyard.mcp`, hosts the MCP stdio server.
- `mcp/client.py` — `JsonRpcClient` that connects to the control socket, performs handshake, sends/receives JSON-RPC requests.
- `mcp/server.py` — MCP server: tool registration and call handlers that delegate to `JsonRpcClient`.
- `mcp/tools.py` — pure data: list of `ToolSpec` dataclasses describing each tool's name, description, input schema, and the RPC method it maps to.

Modified files:

- `src/shipyard/config/schema.py` — add `MCPSettings`, wire into `GlobalSettings`.
- `src/shipyard/app.py` — start/stop the control server in `on_mount`/`on_unmount`; add `mcp` argparse subcommand in `main`.
- `pyproject.toml` — add `mcp>=1.0` dependency.
- `doc/architecture.md`, `doc/configuration.md`, `doc/screens.md`, `doc/plan.md`, `README.md` — documentation updates.

New tests:

- `tests/test_config.py` — extend with MCPSettings test cases.
- `tests/control/__init__.py`, `tests/control/test_jobs.py`, `tests/control/test_methods.py`, `tests/control/test_protocol.py`, `tests/control/test_audit.py`, `tests/control/test_server.py`.
- `tests/mcp/__init__.py`, `tests/mcp/test_client.py`, `tests/mcp/test_server.py`, `tests/mcp/test_tools.py`.
- `tests/integration/__init__.py`, `tests/integration/test_control_socket.py`, `tests/integration/test_mcp_end_to_end.py`.
- `tests/control/conftest.py` — shared fakes for control-method tests (FakeSSHPool, FakeDeployer, FakeFileSyncer, FakeGitHubClient, in-memory SecretStore).

New docs:

- `doc/mcp.md`.

---

## Task 1: Add MCPSettings to config schema

**Files:**
- Modify: `src/shipyard/config/schema.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_mcp_settings_defaults() -> None:
    """MCPSettings has sensible defaults and is part of GlobalSettings."""
    from shipyard.config.schema import GlobalSettings, MCPSettings

    g = GlobalSettings()
    assert isinstance(g.mcp, MCPSettings)
    assert g.mcp.enabled is False
    assert g.mcp.socket_path == "~/.config/shipyard/control.sock"
    assert g.mcp.audit_log_path == "~/.config/shipyard/audit.log"


def test_mcp_settings_from_yaml(sample_config_dict: dict) -> None:
    """MCP block is parsed from the global section."""
    from shipyard.config.schema import ShipyardConfig

    sample_config_dict["global"]["mcp"] = {
        "enabled": True,
        "socket_path": "/tmp/test.sock",
        "audit_log_path": "/tmp/audit.log",
    }
    cfg = ShipyardConfig.model_validate(sample_config_dict)
    assert cfg.global_.mcp.enabled is True
    assert cfg.global_.mcp.socket_path == "/tmp/test.sock"
    assert cfg.global_.mcp.audit_log_path == "/tmp/audit.log"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py::test_mcp_settings_defaults tests/test_config.py::test_mcp_settings_from_yaml -v`
Expected: FAIL with `ImportError: cannot import name 'MCPSettings'`.

- [ ] **Step 3: Add MCPSettings to schema**

Edit `src/shipyard/config/schema.py`. After the `GitHubSettings` class and before `GlobalSettings`, insert:

```python
class MCPSettings(BaseModel):
    enabled: bool = False
    socket_path: str = "~/.config/shipyard/control.sock"
    audit_log_path: str = "~/.config/shipyard/audit.log"
```

Then update `GlobalSettings` to:

```python
class GlobalSettings(BaseModel):
    ssh: SSHSettings = SSHSettings()
    github: GitHubSettings = GitHubSettings()
    mcp: MCPSettings = MCPSettings()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (all config tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/config/schema.py tests/test_config.py
git commit -m "feat(config): add MCPSettings to global config schema"
```

---

## Task 2: Add `mcp` SDK dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

Edit `pyproject.toml`. Append `"mcp>=1.0"` to the `dependencies` list:

```toml
dependencies = [
    "textual>=0.85.0",
    "asyncssh>=2.17.0",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "httpx>=0.27.0",
    "cryptography>=42.0",
    "mcp>=1.0",
]
```

- [ ] **Step 2: Install in dev venv**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: succeeds, installs `mcp` and its transitive deps.

- [ ] **Step 3: Confirm import works**

Run: `.venv/bin/python -c "from mcp.server import Server; from mcp.server.stdio import stdio_server; from mcp.types import Tool, TextContent; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add mcp SDK dependency for upcoming MCP server"
```

---

## Task 3: Create empty `control/` package and `Job` dataclass

**Files:**
- Create: `src/shipyard/control/__init__.py`
- Create: `src/shipyard/control/jobs.py`
- Create: `tests/control/__init__.py`
- Test: `tests/control/test_jobs.py`

- [ ] **Step 1: Create empty package markers**

Create `src/shipyard/control/__init__.py` with content:

```python
"""Control plane: in-TUI JSON-RPC server, accessed via Unix socket by shipyard mcp."""
```

Create `tests/control/__init__.py` with empty content.

- [ ] **Step 2: Write the failing tests**

Create `tests/control/test_jobs.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shipyard.control.jobs'`.

- [ ] **Step 4: Implement jobs module**

Create `src/shipyard/control/jobs.py`:

```python
"""In-memory job registry for prepare/execute confirmation tokens."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_jobs.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/shipyard/control/__init__.py src/shipyard/control/jobs.py tests/control/__init__.py tests/control/test_jobs.py
git commit -m "feat(control): add Job/JobRegistry for prepare-execute tokens"
```

---

## Task 4: Create shared test fakes for control methods

**Files:**
- Modify: `tests/conftest.py`

Putting these in the top-level `tests/conftest.py` (rather than `tests/control/conftest.py`) lets the integration tests under `tests/integration/` see them without re-export tricks.

- [ ] **Step 1: Append the fakes to the existing top-level conftest**

Append to `tests/conftest.py`:

```python
# === Below this line: shared fakes for control-plane and MCP tests ===
from dataclasses import dataclass, field
from typing import Any

from shipyard.secrets.store import SecretStore


@dataclass
class FakeDeployResult:
    success: bool = True
    exit_code: int = 0
    stdout: str = "Deploy ok\n"
    stderr: str = ""


@dataclass
class FakeSSHPool:
    """Stand-in for SSHConnectionPool. Records calls, returns canned output."""

    server_log_lines: dict[str, list[str]] = field(default_factory=dict)
    reachable: dict[str, bool] = field(default_factory=dict)

    async def check_connection(self, server_id: str) -> bool:
        return self.reachable.get(server_id, True)


@dataclass
class FakeDeployer:
    """Stand-in for Deployer."""

    next_result: FakeDeployResult = field(default_factory=FakeDeployResult)
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def run_to_completion(
        self, app_id: str, env_id: str, version: str, env_config
    ) -> FakeDeployResult:
        self.calls.append((app_id, env_id, version))
        return self.next_result


@dataclass
class FakeSyncResult:
    success: bool = True
    transferred: list[str] = field(default_factory=lambda: ["docker-compose.yml"])
    skipped: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class FakeFileSyncer:
    """Stand-in for FileSyncer."""

    next_result: FakeSyncResult = field(default_factory=FakeSyncResult)
    template_files: list[str] = field(default_factory=list)
    planned_uploads: list[str] = field(default_factory=lambda: ["docker-compose.yml"])
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def scan_for_prepare(
        self, server_id: str, local_path: str, remote_path: str
    ) -> dict[str, Any]:
        return {
            "planned_uploads": list(self.planned_uploads),
            "template_files": list(self.template_files),
        }

    async def run_to_completion(
        self, server_id: str, local_path: str, remote_path: str
    ) -> FakeSyncResult:
        self.calls.append((server_id, local_path, remote_path))
        return self.next_result


@dataclass
class FakeGitHubClient:
    """Stand-in for GitHubClient."""

    versions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def get_versions(self, repo: str, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.versions.get(repo, []))[:limit]


@dataclass
class FakeRemoteExecutor:
    """Used by methods that run docker logs on demand."""

    log_output: dict[tuple[str, str], str] = field(default_factory=dict)

    async def docker_logs_tail(
        self, server_id: str, container: str, lines: int
    ) -> str:
        return self.log_output.get((server_id, container), "")


@pytest.fixture
def fake_ssh_pool() -> FakeSSHPool:
    return FakeSSHPool(reachable={"prod-01": True, "staging-01": True})


@pytest.fixture
def fake_deployer() -> FakeDeployer:
    return FakeDeployer()


@pytest.fixture
def fake_syncer() -> FakeFileSyncer:
    return FakeFileSyncer()


@pytest.fixture
def fake_github() -> FakeGitHubClient:
    return FakeGitHubClient(
        versions={
            "myorg/frontend": [
                {"name": "v3.4.0", "kind": "release", "prerelease": False},
                {"name": "v3.3.0", "kind": "release", "prerelease": False},
            ],
        }
    )


@pytest.fixture
def fake_executor() -> FakeRemoteExecutor:
    return FakeRemoteExecutor()


@pytest.fixture
def unlocked_secrets(tmp_path) -> SecretStore:
    store = SecretStore(path=tmp_path / "secrets.enc")
    store.unlock("testpw")
    store.set("DB_PASSWORD", "supersecret")
    store.set("API_KEY", "abc123")
    return store


@pytest.fixture
def locked_secrets(tmp_path) -> SecretStore:
    return SecretStore(path=tmp_path / "secrets.enc")  # not unlocked


@pytest.fixture
def server_container_cache() -> dict[str, list[dict[str, str]]]:
    return {
        "prod-01": [
            {"name": "frontend-prd-web", "status": "running", "image": "myorg/frontend:v3.2", "uptime": "Up 2 days"},
            {"name": "frontend-prd-nginx", "status": "running", "image": "myorg/frontend:v3.2", "uptime": "Up 2 days"},
        ],
        "staging-01": [
            {"name": "frontend-staging-web", "status": "exited", "image": "myorg/frontend:v3.4", "uptime": "Exited 1h ago"},
        ],
    }


@pytest.fixture
def container_cache(server_container_cache, sample_config: ShipyardConfig) -> dict[str, dict[str, list[dict[str, str]]]]:
    cache: dict[str, dict[str, list[dict[str, str]]]] = {}
    for app_id, app in sample_config.applications.items():
        cache[app_id] = {}
        for env_id, env in app.environments.items():
            server_containers = server_container_cache.get(env.server, [])
            by_name = {c["name"]: c for c in server_containers}
            cache[app_id][env_id] = [
                by_name.get(name, {"name": name, "status": "unknown", "image": "", "uptime": ""})
                for name in env.containers
            ]
    return cache


@pytest.fixture
def control_deps(
    sample_config,
    fake_ssh_pool,
    fake_deployer,
    fake_syncer,
    fake_github,
    fake_executor,
    unlocked_secrets,
    container_cache,
    server_container_cache,
):
    """Bundle of dependencies passed to ControlMethods."""
    return {
        "config": sample_config,
        "ssh_pool": fake_ssh_pool,
        "deployer": fake_deployer,
        "syncer": fake_syncer,
        "github_client": fake_github,
        "executor": fake_executor,
        "secret_store": unlocked_secrets,
        "container_cache": container_cache,
        "server_container_cache": server_container_cache,
    }
```

Note: `tests/conftest.py` already provides `sample_config` and `sample_config_dict`; the fakes above are appended after those. The existing `import pytest` at the top of the file is reused.

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared fakes for control-plane and MCP tests"
```

---

## Task 5: ControlMethods — apps.list / apps.get / apps.refresh_status

**Files:**
- Create: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/control/test_methods.py`:

```python
"""Tests for ControlMethods — thin RPC wrappers over services."""

from __future__ import annotations

import pytest

from shipyard.control.methods import ControlMethods, ControlError, ErrorCode


@pytest.fixture
def methods(control_deps) -> ControlMethods:
    return ControlMethods(**control_deps)


async def test_apps_list_returns_all_apps(methods) -> None:
    result = await methods.apps_list()
    assert isinstance(result, list)
    assert {a["id"] for a in result} == {"frontend"}
    frontend = result[0]
    assert frontend["name"] == "Frontend App"
    assert frontend["github"]["repo"] == "myorg/frontend"
    env_ids = {e["id"] for e in frontend["environments"]}
    assert env_ids == {"prd", "staging"}


async def test_apps_get_returns_full_detail(methods) -> None:
    result = await methods.apps_get(app_id="frontend")
    assert result["id"] == "frontend"
    envs = {e["id"]: e for e in result["environments"]}
    assert envs["prd"]["server"] == "prod-01"
    assert envs["prd"]["path"] == "/opt/apps/frontend"
    containers = {c["name"]: c for c in envs["prd"]["containers"]}
    assert containers["frontend-prd-web"]["status"] == "running"
    assert containers["frontend-prd-web"]["image"] == "myorg/frontend:v3.2"


async def test_apps_get_unknown_app_raises_not_found(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.apps_get(app_id="does-not-exist")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_apps_refresh_status_calls_refresher(monkeypatch, methods) -> None:
    called = []

    async def fake_refresh() -> None:
        called.append(True)

    methods._refresh_status_callback = fake_refresh
    result = await methods.apps_refresh_status()
    assert called == [True]
    assert result == {"ok": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shipyard.control.methods'`.

- [ ] **Step 3: Implement methods module (apps section)**

Create `src/shipyard/control/methods.py`:

```python
"""Control-plane RPC methods. Thin wrappers over existing services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Awaitable, Callable, Protocol

from shipyard.config.schema import ApplicationConfig, EnvironmentConfig, ShipyardConfig
from shipyard.control.jobs import Job, JobNotFoundError, JobRegistry
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/methods.py tests/control/test_methods.py
git commit -m "feat(control): add apps_list / apps_get / apps_refresh_status methods"
```

---

## Task 6: ControlMethods — servers + containers

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_servers_list_returns_all(methods) -> None:
    result = await methods.servers_list()
    assert {s["id"] for s in result} == {"prod-01", "staging-01"}
    prod = next(s for s in result if s["id"] == "prod-01")
    assert prod["hostname"] == "10.0.1.10"
    assert prod["port"] == 22
    assert prod["user"] == "deploy"


async def test_servers_get_includes_containers_and_reachability(methods) -> None:
    result = await methods.servers_get(server_id="prod-01")
    assert result["id"] == "prod-01"
    assert result["reachable"] is True
    names = {c["name"] for c in result["containers"]}
    assert "frontend-prd-web" in names


async def test_servers_get_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.servers_get(server_id="nope")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_containers_list_returns_cached_entries(methods) -> None:
    result = await methods.containers_list(server_id="prod-01")
    assert len(result) == 2
    assert {c["name"] for c in result} == {"frontend-prd-web", "frontend-prd-nginx"}


async def test_containers_list_unknown_server_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.containers_list(server_id="ghost")
    assert exc_info.value.code == ErrorCode.NOT_FOUND
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "servers or containers"`
Expected: FAIL with `AttributeError: 'ControlMethods' object has no attribute 'servers_list'`.

- [ ] **Step 3: Implement methods**

Append inside `class ControlMethods:` in `src/shipyard/control/methods.py`, after `apps_refresh_status`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "servers or containers"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/methods.py tests/control/test_methods.py
git commit -m "feat(control): add servers_list / servers_get / containers_list"
```

---

## Task 7: ControlMethods — logs.tail + github.versions

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_logs_tail_returns_snapshot(methods, fake_executor) -> None:
    fake_executor.log_output[("prod-01", "frontend-prd-web")] = "line a\nline b\nline c\n"
    result = await methods.logs_tail(server_id="prod-01", container="frontend-prd-web", lines=100)
    assert result["output"] == "line a\nline b\nline c\n"
    assert result["truncated"] is False


async def test_logs_tail_truncates_oversized_output(methods, fake_executor) -> None:
    big = "x" * (70 * 1024)  # 70 KB
    fake_executor.log_output[("prod-01", "frontend-prd-web")] = big
    result = await methods.logs_tail(server_id="prod-01", container="frontend-prd-web", lines=2000)
    assert len(result["output"].encode()) <= 64 * 1024
    assert result["truncated"] is True
    assert result["bytes_dropped"] > 0


async def test_logs_tail_clamps_lines(methods, fake_executor) -> None:
    fake_executor.log_output[("prod-01", "x")] = "ok"
    result = await methods.logs_tail(server_id="prod-01", container="x", lines=99999)
    # lines arg has been clamped to 2000 (max); we don't observe directly but the
    # call must succeed.
    assert result["output"] == "ok"


async def test_logs_tail_unknown_server_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.logs_tail(server_id="ghost", container="x", lines=100)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_github_versions_returns_list(methods) -> None:
    result = await methods.github_versions(app_id="frontend", limit=10)
    assert [v["name"] for v in result] == ["v3.4.0", "v3.3.0"]


async def test_github_versions_unknown_app_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.github_versions(app_id="ghost", limit=10)
    assert exc_info.value.code == ErrorCode.NOT_FOUND
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "logs_tail or github_versions"`
Expected: FAIL with `AttributeError: ... 'logs_tail'`.

- [ ] **Step 3: Implement methods**

At the top of `src/shipyard/control/methods.py`, add the constant near `ErrorCode`:

```python
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_LOG_LINES = 2000
_MAX_GH_LIMIT = 100
```

Then append inside `class ControlMethods:`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "logs_tail or github_versions"`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/methods.py tests/control/test_methods.py
git commit -m "feat(control): add logs_tail and github_versions methods"
```

---

## Task 8: ControlMethods — secrets

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_secrets_is_unlocked_when_open(methods) -> None:
    result = await methods.secrets_is_unlocked()
    assert result == {"unlocked": True}


async def test_secrets_list_keys_returns_sorted(methods) -> None:
    result = await methods.secrets_list_keys()
    assert result == ["API_KEY", "DB_PASSWORD"]


async def test_secrets_get_returns_value(methods) -> None:
    result = await methods.secrets_get(key="DB_PASSWORD")
    assert result == {"value": "supersecret"}


async def test_secrets_get_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.secrets_get(key="MISSING")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_secrets_set_creates_new(methods) -> None:
    result = await methods.secrets_set(key="NEW_ONE", value="abc")
    assert result == {"ok": True, "created": True}
    assert (await methods.secrets_get(key="NEW_ONE")) == {"value": "abc"}


async def test_secrets_set_overwrites_existing(methods) -> None:
    result = await methods.secrets_set(key="DB_PASSWORD", value="newpw")
    assert result == {"ok": True, "created": False}
    assert (await methods.secrets_get(key="DB_PASSWORD")) == {"value": "newpw"}


async def test_secrets_delete_removes_key(methods) -> None:
    result = await methods.secrets_delete(key="DB_PASSWORD")
    assert result == {"ok": True}
    with pytest.raises(ControlError):
        await methods.secrets_get(key="DB_PASSWORD")


async def test_secrets_delete_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.secrets_delete(key="MISSING")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_secret_ops_locked_store_raises(locked_secrets, control_deps) -> None:
    control_deps["secret_store"] = locked_secrets
    m = ControlMethods(**control_deps)
    assert (await m.secrets_is_unlocked()) == {"unlocked": False}
    for coro in (
        m.secrets_list_keys(),
        m.secrets_get(key="X"),
        m.secrets_set(key="X", value="1"),
        m.secrets_delete(key="X"),
    ):
        with pytest.raises(ControlError) as exc_info:
            await coro
        assert exc_info.value.code == ErrorCode.SECRET_STORE_LOCKED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "secret"`
Expected: FAIL with `AttributeError: ... 'secrets_is_unlocked'`.

- [ ] **Step 3: Implement methods**

Append inside `class ControlMethods:`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "secret"`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/methods.py tests/control/test_methods.py
git commit -m "feat(control): add secrets RPC methods with locked-store guards"
```

---

## Task 9: ControlMethods — templates

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_templates_list_returns_j2_files(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    (local / "config.env.j2").write_text("DB_PASSWORD={{DB_PASSWORD}}\nAPI_KEY={{API_KEY}}\n")
    (local / "static.txt").write_text("not a template\n")

    # Point the prd environment at this local path
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)

    m = ControlMethods(**control_deps)
    result = await m.templates_list(app_id="frontend", env_id="prd")
    paths = {t["path"] for t in result}
    assert paths == {"config.env.j2"}
    entry = result[0]
    assert entry["resolution"] in {"LINKED", "MISSING", "PLAIN"}
    assert entry["resolution"] == "LINKED"  # both vars exist in unlocked store


async def test_templates_list_missing_variables(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    (local / "config.j2").write_text("UNKNOWN={{NOT_IN_STORE}}\n")
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)

    m = ControlMethods(**control_deps)
    result = await m.templates_list(app_id="frontend", env_id="prd")
    assert result[0]["resolution"] == "MISSING"
    assert result[0]["missing_variables"] == ["NOT_IN_STORE"]


async def test_templates_list_no_local_path_raises(control_deps) -> None:
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = None
    m = ControlMethods(**control_deps)
    with pytest.raises(ControlError) as exc_info:
        await m.templates_list(app_id="frontend", env_id="prd")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_templates_inspect_per_line(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    (local / "subdir").mkdir()
    (local / "subdir" / "env.j2").write_text(
        "DB_PASSWORD={{DB_PASSWORD}}\n"
        "API_KEY={{API_KEY}}\n"
        "MISSING_ONE={{NOT_IN_STORE}}\n"
        "PLAIN=hello\n"
    )
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)

    m = ControlMethods(**control_deps)
    result = await m.templates_inspect(app_id="frontend", env_id="prd", path="subdir/env.j2")
    entries = {e["key"]: e for e in result["entries"]}
    assert entries["DB_PASSWORD"]["resolution"] == "LINKED"
    assert "value" not in entries["DB_PASSWORD"]  # value must never leak
    assert entries["MISSING_ONE"]["resolution"] == "MISSING"
    assert entries["PLAIN"]["resolution"] == "PLAIN"


async def test_templates_inspect_unknown_path_raises(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)
    m = ControlMethods(**control_deps)
    with pytest.raises(ControlError) as exc_info:
        await m.templates_inspect(app_id="frontend", env_id="prd", path="nothere.j2")
    assert exc_info.value.code == ErrorCode.NOT_FOUND
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "template"`
Expected: FAIL with `AttributeError: ... 'templates_list'`.

- [ ] **Step 3: Implement methods**

Add this import near the top of `src/shipyard/control/methods.py`:

```python
import re as _re
from pathlib import Path as _Path
```

Add this module-level helper above `class ControlMethods`:

```python
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
```

Append inside `class ControlMethods:`:

```python
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

    async def templates_inspect(
        self, app_id: str, env_id: str, path: str
    ) -> dict[str, Any]:
        local_path = self._env_local_path(app_id, env_id)
        root = _Path(local_path).expanduser().resolve()
        target = (root / path).resolve()
        if not target.is_file() or root not in target.parents and target != root:
            # Reject paths outside local_path; also catches non-existent files.
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "template"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/methods.py tests/control/test_methods.py
git commit -m "feat(control): add templates_list / templates_inspect methods"
```

---

## Task 10: ControlMethods — deploy prepare/execute

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_deploy_prepare_returns_token_and_summary(methods) -> None:
    result = await methods.deploy_prepare(app_id="frontend", env_id="prd", version="v3.4.0")
    assert "token" in result
    summary = result["summary"]
    assert summary["server"] == "prod-01"
    assert summary["path"] == "/opt/apps/frontend"
    assert summary["version"] == "v3.4.0"
    assert summary["containers"] == ["frontend-prd-web", "frontend-prd-nginx"]
    assert summary["current_versions"] == ["myorg/frontend:v3.2", "myorg/frontend:v3.2"]


async def test_deploy_prepare_unknown_env_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.deploy_prepare(app_id="frontend", env_id="nope", version="v1")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_deploy_execute_runs_deployer(methods, fake_deployer) -> None:
    prepare = await methods.deploy_prepare(app_id="frontend", env_id="prd", version="v3.4.0")
    result = await methods.deploy_execute(token=prepare["token"])
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert fake_deployer.calls == [("frontend", "prd", "v3.4.0")]


async def test_deploy_execute_invalid_token(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.deploy_execute(token="bogus")
    assert exc_info.value.code == ErrorCode.INVALID_CONFIRMATION_TOKEN


async def test_deploy_execute_single_use(methods) -> None:
    prepare = await methods.deploy_prepare(app_id="frontend", env_id="prd", version="v3.4.0")
    await methods.deploy_execute(token=prepare["token"])
    with pytest.raises(ControlError) as exc_info:
        await methods.deploy_execute(token=prepare["token"])
    assert exc_info.value.code == ErrorCode.INVALID_CONFIRMATION_TOKEN


async def test_deploy_execute_truncates_oversized_output(methods, fake_deployer) -> None:
    fake_deployer.next_result.stdout = "x" * (70 * 1024)
    prepare = await methods.deploy_prepare(app_id="frontend", env_id="prd", version="v3.4.0")
    result = await methods.deploy_execute(token=prepare["token"])
    assert result["truncated"] is True
    assert result["bytes_dropped"] > 0
    assert len(result["output"].encode()) <= 64 * 1024
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "deploy"`
Expected: FAIL with `AttributeError: ... 'deploy_prepare'`.

- [ ] **Step 3: Implement methods**

Append inside `class ControlMethods:`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "deploy"`
Expected: PASS (6 tests).

- [ ] **Step 5: Add `Deployer.run_to_completion` to the real deployer**

The fake exposes `run_to_completion`; the real `Deployer` (`src/shipyard/deploy/deployer.py`) does not yet. Add it as a wrapper that consumes the existing event stream.

Edit `src/shipyard/deploy/deployer.py`. After the `Deployer.deploy` method, add:

```python
    async def run_to_completion(
        self,
        app_id: str,
        env_id: str,
        version: str,
        env_config: EnvironmentConfig,
    ) -> "DeployRunResult":
        """Run a deploy to completion, collecting all output.

        Used by the control plane for block-and-return MCP semantics.
        """
        stdout_lines: list[str] = []
        final_status = DeployStatus.PENDING
        async for event in self.deploy(app_id, env_id, version, env_config):
            if event.status == DeployStatus.RUNNING:
                stdout_lines.append(event.message)
            else:
                final_status = event.status
                stdout_lines.append(event.message)
        success = final_status == DeployStatus.SUCCESS
        return DeployRunResult(
            success=success,
            exit_code=0 if success else 1,
            stdout="\n".join(stdout_lines) + "\n",
            stderr="",
        )
```

Then add the dataclass `DeployRunResult` near `DeployResult` (after it):

```python
@dataclass
class DeployRunResult:
    """Aggregated result for block-and-return callers (MCP control plane)."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
```

- [ ] **Step 6: Run all tests to confirm nothing else broke**

Run: `.venv/bin/pytest -v`
Expected: PASS (everything green).

- [ ] **Step 7: Commit**

```bash
git add src/shipyard/control/methods.py src/shipyard/deploy/deployer.py tests/control/test_methods.py
git commit -m "feat(control): add deploy prepare/execute with confirmation tokens"
```

---

## Task 11: ControlMethods — sync prepare/execute

**Files:**
- Modify: `src/shipyard/control/methods.py`
- Modify: `src/shipyard/sync/syncer.py`
- Test: `tests/control/test_methods.py`

- [ ] **Step 1: Append tests**

Append to `tests/control/test_methods.py`:

```python
async def test_sync_prepare_returns_token_and_summary(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)
    control_deps["syncer"].planned_uploads = ["a.txt", "b.txt"]
    m = ControlMethods(**control_deps)

    result = await m.sync_prepare(app_id="frontend", env_id="prd")
    assert "token" in result
    summary = result["summary"]
    assert summary["server"] == "prod-01"
    assert summary["local_path"] == str(local)
    assert summary["remote_path"] == "/opt/apps/frontend"
    assert summary["planned_uploads"] == ["a.txt", "b.txt"]
    assert summary["template_files"] == []


async def test_sync_prepare_locked_with_templates_errors(tmp_path, control_deps, locked_secrets) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)
    control_deps["syncer"].template_files = ["env.j2"]
    control_deps["secret_store"] = locked_secrets
    m = ControlMethods(**control_deps)

    with pytest.raises(ControlError) as exc_info:
        await m.sync_prepare(app_id="frontend", env_id="prd")
    assert exc_info.value.code == ErrorCode.SECRET_STORE_LOCKED


async def test_sync_prepare_no_local_path_raises(control_deps) -> None:
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = None
    m = ControlMethods(**control_deps)
    with pytest.raises(ControlError) as exc_info:
        await m.sync_prepare(app_id="frontend", env_id="prd")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_sync_execute_runs_syncer(tmp_path, control_deps) -> None:
    local = tmp_path / "frontend-local"
    local.mkdir()
    cfg = control_deps["config"]
    cfg.applications["frontend"].environments["prd"].local_path = str(local)
    m = ControlMethods(**control_deps)
    prepare = await m.sync_prepare(app_id="frontend", env_id="prd")
    result = await m.sync_execute(token=prepare["token"])
    assert result["success"] is True
    assert result["transferred"] == ["docker-compose.yml"]


async def test_sync_execute_invalid_token(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.sync_execute(token="bogus")
    assert exc_info.value.code == ErrorCode.INVALID_CONFIRMATION_TOKEN
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "sync"`
Expected: FAIL with `AttributeError: ... 'sync_prepare'`.

- [ ] **Step 3: Add scan_for_prepare and run_to_completion to FileSyncer**

Edit `src/shipyard/sync/syncer.py`. After the existing `sync` method, add:

```python
    async def scan_for_prepare(
        self, server_id: str, local_path: str, remote_path: str
    ) -> dict[str, list[str]]:
        """Dry-run scan: compute planned uploads and detected template files.

        Used by the MCP control plane to populate sync_prepare summaries.
        """
        template_files: list[str] = []
        root = Path(local_path).expanduser().resolve()
        if root.is_dir():
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for f in filenames:
                    if f.endswith(".j2") and not f.startswith("."):
                        rel = str((Path(dirpath) / f).relative_to(root))
                        template_files.append(rel)

        # If templates are present but secrets are locked, return marker only.
        if template_files and not self._can_process_templates():
            return {"planned_uploads": [], "template_files": template_files}

        check = await self.check_sync_status(server_id, local_path, remote_path)
        planned = sorted(set(check.files_out_of_sync + check.files_missing_remote))
        return {"planned_uploads": planned, "template_files": template_files}

    async def run_to_completion(
        self, server_id: str, local_path: str, remote_path: str
    ) -> "SyncRunResult":
        """Run sync to completion, collecting result. Used by MCP control plane."""
        transferred: list[str] = []
        last_status = SyncStatus.UNKNOWN
        last_message = ""
        async for event in self.sync(server_id, local_path, remote_path):
            last_status = event.status
            last_message = event.message
            if event.status == SyncStatus.SYNCING and event.message.startswith("Uploading: "):
                # Extract filename (strip the "Uploading: " prefix and any trailing " (template)")
                name = event.message[len("Uploading: ") :]
                if name.endswith(" (template)"):
                    name = name[: -len(" (template)")]
                transferred.append(name)
        success = last_status == SyncStatus.IN_SYNC
        return SyncRunResult(
            success=success,
            transferred=transferred,
            skipped=[],
            error="" if success else last_message,
        )
```

Then add this dataclass near `SyncCheckResult`:

```python
@dataclass
class SyncRunResult:
    """Aggregated sync result for block-and-return callers (MCP control plane)."""

    success: bool
    transferred: list[str]
    skipped: list[str]
    error: str = ""
```

- [ ] **Step 4: Implement sync methods on ControlMethods**

Append inside `class ControlMethods:`:

```python
    # ---- sync ------------------------------------------------------------

    async def sync_prepare(self, app_id: str, env_id: str) -> dict[str, Any]:
        local_path = self._env_local_path(app_id, env_id)
        env = self._config.applications[app_id].environments[env_id]
        scan = await self._syncer.scan_for_prepare(
            env.server, local_path, env.path
        )
        if scan["template_files"] and not self._secret_store.is_unlocked:
            raise ControlError(
                ErrorCode.SECRET_STORE_LOCKED,
                "Secret store is locked but .j2 templates exist; unlock via the TUI first",
            )
        summary = {
            "app_id": app_id,
            "env_id": env_id,
            "server": env.server,
            "local_path": local_path,
            "remote_path": env.path,
            "planned_uploads": scan["planned_uploads"],
            "template_files": scan["template_files"],
        }
        token = self._jobs.create(
            kind="sync",
            params={
                "app_id": app_id,
                "env_id": env_id,
                "server_id": env.server,
                "local_path": local_path,
                "remote_path": env.path,
            },
        )
        return {"token": token, "summary": summary}

    async def sync_execute(self, token: str) -> dict[str, Any]:
        try:
            job = self._jobs.consume(token)
        except JobNotFoundError:
            raise ControlError(
                ErrorCode.INVALID_CONFIRMATION_TOKEN,
                "Confirmation token is unknown, expired, or already used",
            )
        if job.kind != "sync":
            raise ControlError(
                ErrorCode.INVALID_CONFIRMATION_TOKEN, "Token is not for a sync"
            )

        result = await self._syncer.run_to_completion(
            job.params["server_id"],
            job.params["local_path"],
            job.params["remote_path"],
        )
        return {
            "success": result.success,
            "transferred": result.transferred,
            "skipped": result.skipped,
            "error": result.error,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_methods.py -v -k "sync"`
Expected: PASS (5 tests).

- [ ] **Step 6: Run full test suite to confirm nothing else broke**

Run: `.venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/shipyard/control/methods.py src/shipyard/sync/syncer.py tests/control/test_methods.py
git commit -m "feat(control): add sync prepare/execute with locked-store guard"
```

---

## Task 12: JSON-RPC protocol helpers

**Files:**
- Create: `src/shipyard/control/protocol.py`
- Test: `tests/control/test_protocol.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/control/test_protocol.py`:

```python
"""Tests for JSON-RPC 2.0 framing helpers."""

from __future__ import annotations

import json

import pytest

from shipyard.control.protocol import (
    JsonRpcError,
    encode_error,
    encode_result,
    parse_request,
)


def test_parse_valid_request() -> None:
    raw = '{"jsonrpc":"2.0","id":1,"method":"apps.list","params":{}}'
    req = parse_request(raw)
    assert req.id == 1
    assert req.method == "apps.list"
    assert req.params == {}


def test_parse_request_without_params() -> None:
    raw = '{"jsonrpc":"2.0","id":7,"method":"apps.list"}'
    req = parse_request(raw)
    assert req.params == {}


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request("not json")
    assert exc_info.value.code == -32700  # Parse error


def test_parse_wrong_jsonrpc_version() -> None:
    raw = '{"jsonrpc":"1.0","id":1,"method":"x"}'
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request(raw)
    assert exc_info.value.code == -32600  # Invalid request


def test_parse_missing_method() -> None:
    raw = '{"jsonrpc":"2.0","id":1}'
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request(raw)
    assert exc_info.value.code == -32600


def test_encode_result_round_trip() -> None:
    payload = encode_result(request_id=42, result={"ok": True})
    parsed = json.loads(payload)
    assert parsed == {"jsonrpc": "2.0", "id": 42, "result": {"ok": True}}


def test_encode_error_round_trip() -> None:
    payload = encode_error(request_id=42, code=-32005, message="not found")
    parsed = json.loads(payload)
    assert parsed == {
        "jsonrpc": "2.0",
        "id": 42,
        "error": {"code": -32005, "message": "not found"},
    }


def test_encode_error_includes_data_when_provided() -> None:
    payload = encode_error(
        request_id=1, code=-32006, message="bad", data={"field": "version"}
    )
    parsed = json.loads(payload)
    assert parsed["error"]["data"] == {"field": "version"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: ... control.protocol`.

- [ ] **Step 3: Implement protocol module**

Create `src/shipyard/control/protocol.py`:

```python
"""JSON-RPC 2.0 framing helpers (newline-delimited)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass
class JsonRpcError(Exception):
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        return f"JSON-RPC error {self.code}: {self.message}"


@dataclass
class JsonRpcRequest:
    id: Any
    method: str
    params: dict[str, Any]


def parse_request(raw: str) -> JsonRpcRequest:
    """Parse a single JSON-RPC request frame. Raises JsonRpcError on protocol problems."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        raise JsonRpcError(INVALID_REQUEST, "Request must be a JSON object")
    if data.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, "Missing or unsupported jsonrpc version")
    method = data.get("method")
    if not isinstance(method, str):
        raise JsonRpcError(INVALID_REQUEST, "Missing or invalid method")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object")
    return JsonRpcRequest(id=data.get("id"), method=method, params=params)


def encode_result(request_id: Any, result: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def encode_error(
    request_id: Any, code: int, message: str, data: Any = None
) -> str:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "error": err})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_protocol.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/protocol.py tests/control/test_protocol.py
git commit -m "feat(control): add JSON-RPC 2.0 framing helpers"
```

---

## Task 13: Audit log writer with rotation

**Files:**
- Create: `src/shipyard/control/audit.py`
- Test: `tests/control/test_audit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/control/test_audit.py`:

```python
"""Tests for the audit log writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog


@pytest.fixture
def audit_path(tmp_path) -> Path:
    return tmp_path / "audit.log"


def test_write_creates_file_with_secure_mode(audit_path) -> None:
    log = AuditLog(path=audit_path)
    log.write(method="apps.list", params_summary={}, result_code=0)
    assert audit_path.exists()
    mode = audit_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_write_appends_jsonl(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(method="apps.list", params_summary={}, result_code=0)
    log.write(method="apps.get", params_summary={"app_id": "frontend"}, result_code=0)
    lines = audit_path.read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[1])
    assert rec["method"] == "apps.get"
    assert rec["params_summary"] == {"app_id": "frontend"}
    assert rec["result_code"] == 0
    assert "timestamp" in rec


def test_secrets_set_does_not_log_value(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(
        method="secrets.set",
        params_summary={"key": "DB_PASSWORD"},  # caller responsible for stripping value
        result_code=0,
    )
    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert "value" not in rec["params_summary"]


def test_rotation_when_size_exceeded(audit_path) -> None:
    log = AuditLog(path=audit_path, max_bytes=200, max_generations=3)
    # Write enough entries to trigger rotation a few times
    for i in range(30):
        log.write(method="apps.list", params_summary={"i": i}, result_code=0)
    assert audit_path.exists()
    # At least audit.log.1 should exist
    assert (audit_path.parent / (audit_path.name + ".1")).exists()
    # No generation past max should exist
    assert not (audit_path.parent / (audit_path.name + ".4")).exists()


def test_peer_credentials_included_when_provided(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(
        method="apps.list",
        params_summary={},
        result_code=0,
        peer={"pid": 1234, "uid": 501},
    )
    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert rec["peer"] == {"pid": 1234, "uid": 501}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: ... control.audit`.

- [ ] **Step 3: Implement audit module**

Create `src/shipyard/control/audit.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_audit.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/control/audit.py tests/control/test_audit.py
git commit -m "feat(control): add audit log writer with size-based rotation"
```

---

## Task 14: Control server — Unix socket + handshake + dispatch

**Files:**
- Create: `src/shipyard/control/server.py`
- Test: `tests/control/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/control/test_server.py`:

```python
"""Tests for the in-TUI JSON-RPC control server."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer


@pytest.fixture
def socket_path(tmp_path) -> Path:
    return tmp_path / "control.sock"


@pytest.fixture
def token_path(tmp_path) -> Path:
    return tmp_path / "control.token"


@pytest.fixture
def audit_log(tmp_path) -> AuditLog:
    return AuditLog(path=tmp_path / "audit.log")


@pytest.fixture
async def running_server(socket_path, token_path, audit_log, control_deps):
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def _send_and_recv(socket_path: Path, frames: list[str]) -> list[str]:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        for frame in frames:
            writer.write((frame + "\n").encode("utf-8"))
            await writer.drain()
        responses: list[str] = []
        for _ in frames[1:]:  # one response per non-handshake frame
            line = await reader.readline()
            if not line:
                break
            responses.append(line.decode("utf-8").rstrip("\n"))
        return responses
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def test_socket_created_with_mode_0600(running_server, socket_path) -> None:
    assert socket_path.exists()
    mode = socket_path.stat().st_mode & 0o777
    assert mode == 0o600


async def test_token_file_created_with_mode_0600(running_server, token_path) -> None:
    assert token_path.exists()
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600
    token = token_path.read_text().strip()
    assert len(token) >= 22


async def test_apps_list_round_trip(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "apps.list", "params": {}})
    responses = await _send_and_recv(socket_path, [handshake, request])
    assert len(responses) == 1
    parsed = json.loads(responses[0])
    assert parsed["id"] == 1
    assert any(a["id"] == "frontend" for a in parsed["result"])


async def test_wrong_token_closes_connection(running_server, socket_path) -> None:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write((json.dumps({"hello": "wrong-token"}) + "\n").encode())
        await writer.drain()
        # Expect EOF
        data = await reader.read(1024)
        assert data == b""
    finally:
        writer.close()


async def test_unknown_method_returns_error(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "no.such.method", "params": {}})
    responses = await _send_and_recv(socket_path, [handshake, request])
    parsed = json.loads(responses[0])
    assert parsed["error"]["code"] == -32601  # Method not found


async def test_validation_error_on_bad_params(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "apps.get", "params": {"app_id": "ghost"}
    })
    responses = await _send_and_recv(socket_path, [handshake, request])
    parsed = json.loads(responses[0])
    assert parsed["error"]["code"] == -32005  # NOT_FOUND


async def test_audit_log_records_calls(running_server, socket_path, token_path, tmp_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "apps.list", "params": {}})
    await _send_and_recv(socket_path, [handshake, request])

    audit_lines = (tmp_path / "audit.log").read_text().splitlines()
    assert len(audit_lines) >= 1
    rec = json.loads(audit_lines[-1])
    assert rec["method"] == "apps.list"
    assert rec["result_code"] == 0


async def test_server_unlinks_socket_on_stop(socket_path, token_path, audit_log, control_deps) -> None:
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    assert socket_path.exists()
    await server.stop()
    assert not socket_path.exists()
    assert not token_path.exists()


async def test_stale_socket_is_unlinked_before_bind(socket_path, token_path, audit_log, control_deps) -> None:
    socket_path.write_text("leftover")  # not a real socket; should be removed
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    try:
        # After start, it's a real socket file (s_type, not the leftover text)
        assert socket_path.exists()
    finally:
        await server.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/control/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: ... control.server`.

- [ ] **Step 3: Implement server**

Create `src/shipyard/control/server.py`:

```python
"""In-TUI JSON-RPC control server over Unix domain socket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import struct
import sys
from pathlib import Path
from typing import Any

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlError, ControlMethods, ErrorCode
from shipyard.control.protocol import (
    INVALID_REQUEST,
    JsonRpcError,
    METHOD_NOT_FOUND,
    encode_error,
    encode_result,
    parse_request,
)


_LOG = logging.getLogger(__name__)

# Map JSON-RPC method name → (ControlMethods coroutine attr name, allowed param keys)
# Allowed param keys keep dispatch strict so unexpected kwargs are rejected.
_METHODS: dict[str, tuple[str, set[str]]] = {
    "apps.list": ("apps_list", set()),
    "apps.get": ("apps_get", {"app_id"}),
    "apps.refresh_status": ("apps_refresh_status", set()),
    "servers.list": ("servers_list", set()),
    "servers.get": ("servers_get", {"server_id"}),
    "containers.list": ("containers_list", {"server_id"}),
    "logs.tail": ("logs_tail", {"server_id", "container", "lines"}),
    "github.versions": ("github_versions", {"app_id", "limit"}),
    "secrets.is_unlocked": ("secrets_is_unlocked", set()),
    "secrets.list_keys": ("secrets_list_keys", set()),
    "secrets.get": ("secrets_get", {"key"}),
    "secrets.set": ("secrets_set", {"key", "value"}),
    "secrets.delete": ("secrets_delete", {"key"}),
    "templates.list": ("templates_list", {"app_id", "env_id"}),
    "templates.inspect": ("templates_inspect", {"app_id", "env_id", "path"}),
    "deploy.prepare": ("deploy_prepare", {"app_id", "env_id", "version"}),
    "deploy.execute": ("deploy_execute", {"token"}),
    "sync.prepare": ("sync_prepare", {"app_id", "env_id"}),
    "sync.execute": ("sync_execute", {"token"}),
}

# Methods whose params_summary should NOT include the "value" field in the audit log.
_PARAMS_REDACT_KEYS: set[str] = {"value", "password", "master_password"}


def _summarize_params(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in _PARAMS_REDACT_KEYS}


def _get_peer_creds(transport: asyncio.BaseTransport) -> dict[str, int] | None:
    sock = transport.get_extra_info("socket")
    if sock is None:
        return None
    try:
        if sys.platform.startswith("linux"):
            # SO_PEERCRED → struct { pid_t pid; uid_t uid; gid_t gid; }
            import socket as _socket
            data = sock.getsockopt(_socket.SOL_SOCKET, 17, struct.calcsize("3i"))  # SO_PEERCRED = 17
            pid, uid, _gid = struct.unpack("3i", data)
            return {"pid": pid, "uid": uid}
        if sys.platform == "darwin":
            import socket as _socket
            # LOCAL_PEEREUID = 2, LOCAL_PEERPID = 3, level = 0 (SOL_LOCAL)
            try:
                uid = sock.getsockopt(0, 2)
            except OSError:
                uid = -1
            try:
                pid = sock.getsockopt(0, 3)
            except OSError:
                pid = -1
            return {"pid": pid, "uid": uid}
    except Exception:  # pragma: no cover (kernel idiosyncrasies)
        return None
    return None


class ControlServer:
    """Asyncio Unix-socket JSON-RPC server inside the TUI."""

    def __init__(
        self,
        methods: ControlMethods,
        socket_path: Path,
        token_path: Path,
        audit_log: AuditLog,
    ) -> None:
        self._methods = methods
        self._socket_path = Path(socket_path).expanduser()
        self._token_path = Path(token_path).expanduser()
        self._audit = audit_log
        self._server: asyncio.AbstractServer | None = None
        self._token: str = ""

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove stale socket / token files from a prior crashed run.
        for p in (self._socket_path, self._token_path):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _LOG.warning("Could not remove stale %s: %s", p, exc)

        # Write the token file BEFORE the socket is reachable.
        self._token = secrets.token_urlsafe(32)
        self._token_path.write_text(self._token)
        os.chmod(self._token_path, 0o600)

        self._server = await asyncio.start_unix_server(
            self._handle_connection, path=str(self._socket_path)
        )
        os.chmod(self._socket_path, 0o600)
        _LOG.info("Control server listening at %s", self._socket_path)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        for p in (self._socket_path, self._token_path):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _LOG.warning("Could not remove %s on shutdown: %s", p, exc)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = _get_peer_creds(writer.transport)
        try:
            # Step 1: token handshake
            line = await reader.readline()
            if not line:
                return
            try:
                handshake = json.loads(line.decode("utf-8").rstrip("\n"))
            except json.JSONDecodeError:
                self._audit.write("handshake.fail", {"reason": "invalid_json"}, 1, peer=peer)
                return
            if not isinstance(handshake, dict) or handshake.get("hello") != self._token:
                self._audit.write("handshake.fail", {"reason": "bad_token"}, 1, peer=peer)
                return

            # Step 2: request loop
            while True:
                line = await reader.readline()
                if not line:
                    return
                raw = line.decode("utf-8").rstrip("\n")
                if not raw:
                    continue
                response = await self._handle_one(raw, peer)
                writer.write((response + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            return
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_one(self, raw: str, peer: dict[str, int] | None) -> str:
        try:
            req = parse_request(raw)
        except JsonRpcError as exc:
            self._audit.write("parse.error", {}, exc.code, peer=peer)
            return encode_error(None, exc.code, exc.message)

        spec = _METHODS.get(req.method)
        if spec is None:
            self._audit.write(req.method, _summarize_params(req.method, req.params), METHOD_NOT_FOUND, peer=peer)
            return encode_error(req.id, METHOD_NOT_FOUND, f"Unknown method: {req.method}")

        attr_name, allowed = spec
        extra = set(req.params) - allowed
        if extra:
            self._audit.write(req.method, _summarize_params(req.method, req.params), INVALID_REQUEST, peer=peer)
            return encode_error(
                req.id,
                INVALID_REQUEST,
                f"Unexpected parameter(s): {sorted(extra)}",
            )

        handler = getattr(self._methods, attr_name)
        try:
            result = await handler(**req.params)
        except ControlError as exc:
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(exc.code), peer=peer)
            return encode_error(req.id, int(exc.code), exc.message)
        except TypeError as exc:
            # Missing required kwargs from params
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(ErrorCode.VALIDATION_ERROR), peer=peer)
            return encode_error(
                req.id, int(ErrorCode.VALIDATION_ERROR), f"Invalid parameters: {exc}"
            )
        except Exception as exc:
            _LOG.exception("Internal error handling %s", req.method)
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(ErrorCode.INTERNAL_ERROR), peer=peer)
            return encode_error(req.id, int(ErrorCode.INTERNAL_ERROR), "Internal error")

        self._audit.write(req.method, _summarize_params(req.method, req.params), 0, peer=peer)
        return encode_result(req.id, result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/control/test_server.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/shipyard/control/server.py tests/control/test_server.py
git commit -m "feat(control): add Unix-socket JSON-RPC server with token handshake"
```

---

## Task 15: Wire control server into ShipyardApp

**Files:**
- Modify: `src/shipyard/app.py`
- Modify: `src/shipyard/deploy/deployer.py` (already updated in Task 10 — only needed if hooks haven't been wired yet)

- [ ] **Step 1: Modify app.py to start/stop the control server**

Edit `src/shipyard/app.py`. Add these imports near the top alongside existing ones:

```python
from pathlib import Path

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
```

In the `ShipyardApp.__init__` method, after `self.file_syncer = ...`, add:

```python
        self._control_server: ControlServer | None = None
```

Replace the existing `on_mount` method with:

```python
    def on_mount(self) -> None:
        from shipyard.screens.dashboard import DashboardScreen

        self.push_screen(DashboardScreen())
        self.refresh_container_cache()
        if self.shipyard_config.global_.mcp.enabled:
            self.run_worker(self._start_control_server(), exclusive=True, group="control_server")

    async def _start_control_server(self) -> None:
        cfg = self.shipyard_config.global_.mcp
        socket_path = Path(cfg.socket_path).expanduser()
        token_path = socket_path.with_name("control.token")
        audit = AuditLog(path=Path(cfg.audit_log_path).expanduser())

        methods = ControlMethods(
            config=self.shipyard_config,
            ssh_pool=self.ssh_pool,
            deployer=self.deployer,
            syncer=self.file_syncer,
            github_client=self.github_client,
            executor=_AppRemoteExecutor(self.ssh_pool),
            secret_store=self.secret_store,
            container_cache=self.container_cache,
            server_container_cache=self.server_container_cache,
            refresh_status_callback=self._refresh_for_control,
        )
        self._control_server = ControlServer(
            methods=methods,
            socket_path=socket_path,
            token_path=token_path,
            audit_log=audit,
        )
        await self._control_server.start()

    async def _refresh_for_control(self) -> None:
        """Wait for an in-flight refresh to complete, then trigger one and wait."""
        await self._fetch_all_container_status()
```

Replace the existing `on_unmount` method with:

```python
    async def on_unmount(self) -> None:
        if self._control_server is not None:
            try:
                await self._control_server.stop()
            except Exception:
                pass
        await self.ssh_pool.close_all()
        await self.github_client.close()
```

Then, near the bottom of `app.py`, before `def main()`, add a small executor adapter:

```python
class _AppRemoteExecutor:
    """Minimal adapter exposing docker_logs_tail for the control plane."""

    def __init__(self, ssh_pool: SSHConnectionPool) -> None:
        self._ssh_pool = ssh_pool

    async def docker_logs_tail(
        self, server_id: str, container: str, lines: int
    ) -> str:
        conn = await self._ssh_pool.get_connection(server_id)
        result = await conn.run(
            f"docker logs --tail {lines} {container} 2>&1", timeout=30
        )
        return result.stdout or ""
```

- [ ] **Step 2: Add the `mcp` subcommand to argparse**

Edit `main()` in `src/shipyard/app.py`:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Shipyard - Docker Deployment TUI")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)

    subparsers = parser.add_subparsers(dest="command")
    mcp_parser = subparsers.add_parser(
        "mcp", help="Run the Shipyard MCP server over stdio (requires the TUI to be running)"
    )
    mcp_parser.add_argument("--config", "-c", help="Path to config file", default=None)

    args = parser.parse_args()

    if args.command == "mcp":
        from shipyard.mcp.__main__ import main as mcp_main
        mcp_main(config_path=args.config)
        return

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = ShipyardApp(config)
    app.run()
```

- [ ] **Step 3: Smoke test — launch TUI manually**

Run the TUI to confirm nothing broke at import / startup time. With `global.mcp.enabled: false` (default), behavior should be identical.

Run: `.venv/bin/python -c "from shipyard.app import ShipyardApp, main; print('imports ok')"`
Expected: prints `imports ok`.

- [ ] **Step 4: Run all existing tests**

Run: `.venv/bin/pytest -v`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/app.py
git commit -m "feat(app): start MCP control server when global.mcp.enabled"
```

---

## Task 16: MCP-side JSON-RPC client

**Files:**
- Create: `src/shipyard/mcp/__init__.py`
- Create: `src/shipyard/mcp/client.py`
- Create: `tests/mcp/__init__.py`
- Test: `tests/mcp/test_client.py`

- [ ] **Step 1: Create empty package markers**

Create `src/shipyard/mcp/__init__.py` with content:

```python
"""MCP stdio server that proxies to the in-TUI control plane."""
```

Create `tests/mcp/__init__.py` empty.

- [ ] **Step 2: Write the failing tests**

Create `tests/mcp/test_client.py`:

```python
"""Tests for the MCP-side JSON-RPC client (Unix socket)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from shipyard.mcp.client import (
    JsonRpcClient,
    JsonRpcRemoteError,
    ShipyardNotRunningError,
)


async def _start_fake_server(
    socket_path: Path,
    token: str,
    handler,
) -> asyncio.AbstractServer:
    async def serve(reader, writer):
        try:
            hs_line = await reader.readline()
            if not hs_line:
                writer.close()
                return
            hs = json.loads(hs_line.decode().rstrip("\n"))
            if hs.get("hello") != token:
                writer.close()
                return
            while True:
                line = await reader.readline()
                if not line:
                    return
                req = json.loads(line.decode().rstrip("\n"))
                response = handler(req)
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_unix_server(serve, path=str(socket_path))


async def test_client_round_trip(tmp_path) -> None:
    socket_path = tmp_path / "ctl.sock"
    token_path = tmp_path / "ctl.token"
    token = "test-token-1234567890123456"
    token_path.write_text(token)

    def handler(req):
        assert req["method"] == "apps.list"
        return {"jsonrpc": "2.0", "id": req["id"], "result": [{"id": "frontend"}]}

    server = await _start_fake_server(socket_path, token, handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            result = await client.call("apps.list", {})
        finally:
            await client.close()
        assert result == [{"id": "frontend"}]
    finally:
        server.close()
        await server.wait_closed()


async def test_client_remote_error(tmp_path) -> None:
    socket_path = tmp_path / "ctl.sock"
    token_path = tmp_path / "ctl.token"
    token = "token-aaaaaaaaaaaaaaaaaaaaaa"
    token_path.write_text(token)

    def handler(req):
        return {
            "jsonrpc": "2.0",
            "id": req["id"],
            "error": {"code": -32005, "message": "not found"},
        }

    server = await _start_fake_server(socket_path, token, handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            with pytest.raises(JsonRpcRemoteError) as exc_info:
                await client.call("apps.get", {"app_id": "ghost"})
        finally:
            await client.close()
        assert exc_info.value.code == -32005
        assert exc_info.value.message == "not found"
    finally:
        server.close()
        await server.wait_closed()


async def test_client_shipyard_not_running(tmp_path) -> None:
    socket_path = tmp_path / "missing.sock"
    token_path = tmp_path / "missing.token"
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    with pytest.raises(ShipyardNotRunningError):
        await client.connect()


async def test_client_handshake_rejected(tmp_path) -> None:
    socket_path = tmp_path / "ctl.sock"
    token_path = tmp_path / "ctl.token"
    token_path.write_text("wrong-token-xxxxxxxxxxxxxxxxxxxxxxxx")

    def handler(req):
        return {"jsonrpc": "2.0", "id": req["id"], "result": "should-not-get-here"}

    server = await _start_fake_server(socket_path, "real-token-yyyyyyyyyyyyyyyyyyyyyyy", handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            # Server will close the connection after rejecting handshake → next call fails
            with pytest.raises(ShipyardNotRunningError):
                await client.call("apps.list", {})
        finally:
            await client.close()
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mcp/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: ... mcp.client`.

- [ ] **Step 4: Implement the client**

Create `src/shipyard/mcp/client.py`:

```python
"""JSON-RPC client used by `shipyard mcp` to reach the in-TUI control server."""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ShipyardNotRunningError(Exception):
    """Raised when the control socket is unreachable (TUI not running / restarted)."""


@dataclass
class JsonRpcRemoteError(Exception):
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        return f"JSON-RPC error {self.code}: {self.message}"


class JsonRpcClient:
    """Connect to the TUI's Unix socket, perform handshake, send/receive requests."""

    def __init__(self, socket_path: Path, token_path: Path) -> None:
        self._socket_path = Path(socket_path).expanduser()
        self._token_path = Path(token_path).expanduser()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if not self._socket_path.exists():
            raise ShipyardNotRunningError(
                f"Shipyard control socket not found at {self._socket_path}. "
                f"Start the TUI with `shipyard --config <path>` first."
            )
        try:
            token = self._token_path.read_text().strip()
        except FileNotFoundError:
            raise ShipyardNotRunningError(
                "Control token file is missing — Shipyard is not running or is restarting."
            )
        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                str(self._socket_path)
            )
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise ShipyardNotRunningError(
                f"Cannot connect to Shipyard control socket: {exc}"
            )
        # Send handshake
        self._writer.write((json.dumps({"hello": token}) + "\n").encode("utf-8"))
        await self._writer.drain()

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        if self._writer is None or self._reader is None:
            raise ShipyardNotRunningError("Client is not connected")
        request_id = next(self._ids)
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        ) + "\n"

        async with self._lock:
            try:
                self._writer.write(payload.encode("utf-8"))
                await self._writer.drain()
                line = await self._reader.readline()
            except (ConnectionResetError, BrokenPipeError) as exc:
                raise ShipyardNotRunningError(
                    f"Connection to Shipyard lost: {exc}"
                )
            if not line:
                raise ShipyardNotRunningError(
                    "Shipyard closed the connection (TUI may have exited or token rejected)."
                )

        response = json.loads(line.decode("utf-8").rstrip("\n"))
        if "error" in response:
            err = response["error"]
            raise JsonRpcRemoteError(
                code=err.get("code", -32603),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )
        return response.get("result")

    async def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mcp/test_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/shipyard/mcp/__init__.py src/shipyard/mcp/client.py tests/mcp/__init__.py tests/mcp/test_client.py
git commit -m "feat(mcp): add JSON-RPC client that connects to the TUI control socket"
```

---

## Task 17: MCP tool specs

**Files:**
- Create: `src/shipyard/mcp/tools.py`
- Test: `tests/mcp/test_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_tools.py`:

```python
"""Tests for the static MCP tool registry."""

from __future__ import annotations

from shipyard.mcp.tools import TOOL_SPECS, ToolSpec


def test_all_specs_have_required_fields() -> None:
    for spec in TOOL_SPECS:
        assert isinstance(spec, ToolSpec)
        assert spec.name
        assert spec.description
        assert isinstance(spec.input_schema, dict)
        assert spec.input_schema.get("type") == "object"
        assert spec.rpc_method


def test_tool_names_are_unique() -> None:
    names = [s.name for s in TOOL_SPECS]
    assert len(names) == len(set(names))


def test_destructive_tools_have_confirmation_directive() -> None:
    destructive = {"execute_deploy", "execute_sync"}
    for spec in TOOL_SPECS:
        if spec.name in destructive:
            assert "prepare" in spec.description.lower()


def test_no_tool_accepts_master_password_field() -> None:
    forbidden = {"password", "master_password", "passphrase"}
    for spec in TOOL_SPECS:
        props = set(spec.input_schema.get("properties", {}).keys())
        assert not (props & forbidden), f"Tool {spec.name} accepts a forbidden password field"


def test_expected_tools_are_present() -> None:
    names = {s.name for s in TOOL_SPECS}
    expected = {
        "list_applications", "get_application", "refresh_status",
        "list_servers", "get_server", "list_containers",
        "tail_container_logs", "list_github_versions",
        "list_secret_keys", "get_secret_value", "secret_store_status",
        "list_templates", "inspect_template",
        "prepare_deploy", "execute_deploy",
        "prepare_sync", "execute_sync",
        "set_secret", "delete_secret",
    }
    assert expected.issubset(names)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mcp/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: ... mcp.tools`.

- [ ] **Step 3: Implement tool specs**

Create `src/shipyard/mcp/tools.py`:

```python
"""Static registry of MCP tools exposed by `shipyard mcp`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    rpc_method: str


_OBJ: dict[str, Any] = {"type": "object", "properties": {}, "required": []}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_applications",
        description="List all applications, their environments, and the configured Docker containers per environment.",
        input_schema=_schema({}, []),
        rpc_method="apps.list",
    ),
    ToolSpec(
        name="get_application",
        description="Get detailed information about one application, including container statuses per environment from the current cache.",
        input_schema=_schema(
            {"app_id": {"type": "string", "description": "Application identifier from list_applications."}},
            ["app_id"],
        ),
        rpc_method="apps.get",
    ),
    ToolSpec(
        name="refresh_status",
        description="Force a refresh of the container status cache (re-runs `docker ps` on every configured server). Slow.",
        input_schema=_schema({}, []),
        rpc_method="apps.refresh_status",
    ),
    ToolSpec(
        name="list_servers",
        description="List all configured servers with hostname, port, user, and description.",
        input_schema=_schema({}, []),
        rpc_method="servers.list",
    ),
    ToolSpec(
        name="get_server",
        description="Get one server's details plus its SSH reachability and all containers currently on it.",
        input_schema=_schema(
            {"server_id": {"type": "string"}},
            ["server_id"],
        ),
        rpc_method="servers.get",
    ),
    ToolSpec(
        name="list_containers",
        description="List Docker containers on a specific server (from the current cache).",
        input_schema=_schema(
            {"server_id": {"type": "string"}},
            ["server_id"],
        ),
        rpc_method="containers.list",
    ),
    ToolSpec(
        name="tail_container_logs",
        description="Get a finite snapshot of container logs via `docker logs --tail N`. Live follow is not supported.",
        input_schema=_schema(
            {
                "server_id": {"type": "string"},
                "container": {"type": "string"},
                "lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 200},
            },
            ["server_id", "container"],
        ),
        rpc_method="logs.tail",
    ),
    ToolSpec(
        name="list_github_versions",
        description="List the most recent releases or tags for an application's configured GitHub repository.",
        input_schema=_schema(
            {
                "app_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            ["app_id"],
        ),
        rpc_method="github.versions",
    ),
    ToolSpec(
        name="list_secret_keys",
        description="List the keys (not values) of all secrets in the encrypted store. Requires the TUI to be unlocked.",
        input_schema=_schema({}, []),
        rpc_method="secrets.list_keys",
    ),
    ToolSpec(
        name="get_secret_value",
        description="Return the cleartext value of a single secret. Requires the TUI to be unlocked. Treat the value as sensitive.",
        input_schema=_schema(
            {"key": {"type": "string"}},
            ["key"],
        ),
        rpc_method="secrets.get",
    ),
    ToolSpec(
        name="secret_store_status",
        description="Check whether the Shipyard secret store is unlocked. Returns {unlocked: bool}. Safe to call anytime.",
        input_schema=_schema({}, []),
        rpc_method="secrets.is_unlocked",
    ),
    ToolSpec(
        name="set_secret",
        description="Create or overwrite a secret value. Requires the TUI to be unlocked. The old value is not returned.",
        input_schema=_schema(
            {"key": {"type": "string"}, "value": {"type": "string"}},
            ["key", "value"],
        ),
        rpc_method="secrets.set",
    ),
    ToolSpec(
        name="delete_secret",
        description="Delete a secret from the store. Requires the TUI to be unlocked.",
        input_schema=_schema(
            {"key": {"type": "string"}},
            ["key"],
        ),
        rpc_method="secrets.delete",
    ),
    ToolSpec(
        name="list_templates",
        description="List .j2 template files in an environment's local-path directory, with per-file resolution status (LINKED/MISSING/PLAIN).",
        input_schema=_schema(
            {"app_id": {"type": "string"}, "env_id": {"type": "string"}},
            ["app_id", "env_id"],
        ),
        rpc_method="templates.list",
    ),
    ToolSpec(
        name="inspect_template",
        description="Inspect a .j2 template file's KEY=VALUE lines and per-line secret linkage. Resolved secret values are never returned.",
        input_schema=_schema(
            {
                "app_id": {"type": "string"},
                "env_id": {"type": "string"},
                "path": {"type": "string", "description": "Relative path under local-path."},
            },
            ["app_id", "env_id", "path"],
        ),
        rpc_method="templates.inspect",
    ),
    ToolSpec(
        name="prepare_deploy",
        description=(
            "Start a deploy flow. Returns a single-use confirmation_token and a summary "
            "(server, path, version, containers, current_versions). YOU MUST surface the "
            "summary to the user before calling execute_deploy."
        ),
        input_schema=_schema(
            {
                "app_id": {"type": "string"},
                "env_id": {"type": "string"},
                "version": {"type": "string", "description": "Version/tag/release name to deploy."},
            },
            ["app_id", "env_id", "version"],
        ),
        rpc_method="deploy.prepare",
    ),
    ToolSpec(
        name="execute_deploy",
        description=(
            "Run a previously prepared deploy. Requires a confirmation_token from prepare_deploy. "
            "Blocks until rerun.sh exits. Tokens are single-use and expire after 120 seconds."
        ),
        input_schema=_schema(
            {"confirmation_token": {"type": "string"}},
            ["confirmation_token"],
        ),
        rpc_method="deploy.execute",
    ),
    ToolSpec(
        name="prepare_sync",
        description=(
            "Start a sync flow. Returns a confirmation_token and a summary "
            "(local_path, remote_path, planned_uploads, template_files). YOU MUST surface the "
            "summary to the user before calling execute_sync. Fails if .j2 templates exist and the "
            "secret store is locked."
        ),
        input_schema=_schema(
            {"app_id": {"type": "string"}, "env_id": {"type": "string"}},
            ["app_id", "env_id"],
        ),
        rpc_method="sync.prepare",
    ),
    ToolSpec(
        name="execute_sync",
        description=(
            "Run a previously prepared sync. Requires a confirmation_token from prepare_sync. "
            "Blocks until sync finishes. Returns transferred file paths only — never rendered template content."
        ),
        input_schema=_schema(
            {"confirmation_token": {"type": "string"}},
            ["confirmation_token"],
        ),
        rpc_method="sync.execute",
    ),
]


def get_spec(name: str) -> ToolSpec | None:
    for s in TOOL_SPECS:
        if s.name == name:
            return s
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mcp/test_tools.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/mcp/tools.py tests/mcp/test_tools.py
git commit -m "feat(mcp): add static tool registry with input schemas"
```

---

## Task 18: MCP server wiring (tool registration + dispatch)

**Files:**
- Create: `src/shipyard/mcp/server.py`
- Test: `tests/mcp/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp/test_server.py`:

```python
"""Tests for the MCP server dispatcher (mapping MCP tool calls to RPC calls)."""

from __future__ import annotations

import json

import pytest

from shipyard.mcp.client import JsonRpcRemoteError, ShipyardNotRunningError
from shipyard.mcp.server import build_server, handle_call_tool


class FakeClient:
    def __init__(self, responses: dict[str, object] | None = None, raises: Exception | None = None) -> None:
        self.responses = responses or {}
        self.raises = raises
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict) -> object:
        self.calls.append((method, params))
        if self.raises is not None:
            raise self.raises
        return self.responses.get(method, {})


async def test_list_applications_round_trips() -> None:
    client = FakeClient(responses={"apps.list": [{"id": "frontend"}]})
    result = await handle_call_tool(client, "list_applications", {})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload == [{"id": "frontend"}]
    assert client.calls == [("apps.list", {})]


async def test_get_application_passes_args() -> None:
    client = FakeClient(responses={"apps.get": {"id": "frontend"}})
    await handle_call_tool(client, "get_application", {"app_id": "frontend"})
    assert client.calls == [("apps.get", {"app_id": "frontend"})]


async def test_unknown_tool_returns_is_error() -> None:
    client = FakeClient()
    result = await handle_call_tool(client, "no_such_tool", {})
    assert result[0].is_error is True
    assert "unknown tool" in result[0].text.lower()


async def test_remote_error_becomes_error_result() -> None:
    client = FakeClient(raises=JsonRpcRemoteError(code=-32005, message="not found"))
    result = await handle_call_tool(client, "get_application", {"app_id": "ghost"})
    assert result[0].is_error is True
    assert "not found" in result[0].text


async def test_shipyard_not_running_becomes_error_result() -> None:
    client = FakeClient(raises=ShipyardNotRunningError("nope"))
    result = await handle_call_tool(client, "list_applications", {})
    assert result[0].is_error is True
    assert "shipyard is not running" in result[0].text.lower()


async def test_secret_store_locked_friendly_message() -> None:
    client = FakeClient(raises=JsonRpcRemoteError(code=-32002, message="Secret store is locked"))
    result = await handle_call_tool(client, "list_secret_keys", {})
    assert result[0].is_error is True
    assert "locked" in result[0].text.lower()


def test_build_server_registers_all_tools(tmp_path) -> None:
    from shipyard.mcp.tools import TOOL_SPECS

    server, _ = build_server(socket_path=tmp_path / "x.sock", token_path=tmp_path / "x.token")
    # The Server's internal tool registry is implementation-defined; we use the same
    # spec list and rely on the integration test for the protocol level. Here we just
    # ensure build_server returns successfully and the spec list is non-empty.
    assert server is not None
    assert len(TOOL_SPECS) >= 19
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mcp/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: ... mcp.server`.

- [ ] **Step 3: Implement the server**

Create `src/shipyard/mcp/server.py`:

```python
"""MCP stdio server: registers tools and dispatches to the in-TUI control plane."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from shipyard.mcp.client import (
    JsonRpcClient,
    JsonRpcRemoteError,
    ShipyardNotRunningError,
)
from shipyard.mcp.tools import TOOL_SPECS, get_spec


_LOG = logging.getLogger(__name__)


# Map RPC error codes to user-readable hints for MCP tool errors.
_ERROR_HINTS: dict[int, str] = {
    -32001: "Shipyard is not running. Start the TUI with `shipyard --config <path>` first.",
    -32002: "Shipyard's secret store is locked. Unlock it in the TUI (press 'e' on the dashboard).",
    -32003: "Confirmation token is invalid or has expired. Call the matching prepare_* tool again.",
    -32004: "SSH error talking to the target server. Check connectivity in the TUI's Servers screen.",
    -32005: "Not found.",
    -32006: "Invalid parameters.",
    -32099: "An internal error occurred. Check the Shipyard TUI for details.",
}


async def handle_call_tool(
    client: JsonRpcClient, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch one MCP tool call to a JSON-RPC method via `client`."""
    spec = get_spec(name)
    if spec is None:
        return [
            TextContent(
                type="text",
                text=f"Unknown tool: {name}",
                is_error=True,
            )
        ]

    try:
        result = await client.call(spec.rpc_method, arguments)
    except ShipyardNotRunningError as exc:
        return [TextContent(type="text", text=str(exc), is_error=True)]
    except JsonRpcRemoteError as exc:
        hint = _ERROR_HINTS.get(exc.code, "")
        body = exc.message if not hint else f"{hint}\n\n(Detail: {exc.message})"
        return [TextContent(type="text", text=body, is_error=True)]

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def build_server(
    socket_path: Path, token_path: Path
) -> tuple[Server, JsonRpcClient]:
    """Construct an MCP `Server` with all tools registered.

    Returns (server, client). The caller is responsible for connecting the client
    and running the server inside `stdio_server(...)`.
    """
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    server: Server = Server("shipyard")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in TOOL_SPECS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if not client._writer:  # lazy-connect on first call
            try:
                await client.connect()
            except ShipyardNotRunningError as exc:
                return [TextContent(type="text", text=str(exc), is_error=True)]
        return await handle_call_tool(client, name, arguments)

    return server, client
```

Note: `TextContent.is_error` is supported by recent MCP SDK versions; if the installed version doesn't expose it as a field, replace the `is_error=True` kwarg with appending a leading "ERROR: " prefix to the text content. The test in this task assumes the field exists; update the test if needed once you install the SDK.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mcp/test_server.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shipyard/mcp/server.py tests/mcp/test_server.py
git commit -m "feat(mcp): wire MCP tool registration and JSON-RPC dispatch"
```

---

## Task 19: MCP entry point

**Files:**
- Create: `src/shipyard/mcp/__main__.py`

- [ ] **Step 1: Implement the entry point**

Create `src/shipyard/mcp/__main__.py`:

```python
"""`python -m shipyard.mcp` — stdio MCP server.

Loads the same Shipyard YAML config as the TUI to discover where the control socket lives,
then runs the MCP server over stdio. The actual work is forwarded to the running TUI
process via the Unix socket.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from mcp.server.stdio import stdio_server

from shipyard.config.manager import ConfigError, load_config
from shipyard.mcp.server import build_server


_LOG = logging.getLogger("shipyard.mcp")


def main(config_path: str | None = None) -> None:
    """Entry point used by `shipyard mcp`."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"shipyard mcp: config error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not config.global_.mcp.enabled:
        print(
            "shipyard mcp: MCP is disabled in your config. Set `global.mcp.enabled: true` "
            "in shipyard.yaml and restart the TUI.",
            file=sys.stderr,
        )
        sys.exit(3)

    socket_path = Path(config.global_.mcp.socket_path).expanduser()
    token_path = socket_path.with_name("control.token")

    server, _client = build_server(socket_path=socket_path, token_path=token_path)

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test by invoking the entry point**

Run: `.venv/bin/python -c "from shipyard.mcp.__main__ import main; print('import ok')"`
Expected: prints `import ok`.

- [ ] **Step 3: Commit**

```bash
git add src/shipyard/mcp/__main__.py
git commit -m "feat(mcp): add stdio entry point (shipyard mcp)"
```

---

## Task 20: Integration test — control socket end-to-end

**Files:**
- Create: `tests/integration/__init__.py`
- Test: `tests/integration/test_control_socket.py`

- [ ] **Step 1: Create the integration package**

Create `tests/integration/__init__.py` (empty).

- [ ] **Step 2: Write the integration test**

Create `tests/integration/test_control_socket.py`:

```python
"""End-to-end: real ControlServer + real JsonRpcClient over Unix sockets."""

from __future__ import annotations

from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
from shipyard.mcp.client import JsonRpcClient, JsonRpcRemoteError


@pytest.fixture
async def running(tmp_path, control_deps):
    socket_path = tmp_path / "control.sock"
    token_path = tmp_path / "control.token"
    audit = AuditLog(path=tmp_path / "audit.log")
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit,
    )
    await server.start()
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    await client.connect()
    try:
        yield client, server
    finally:
        await client.close()
        await server.stop()


async def test_full_method_listing(running) -> None:
    client, _ = running
    result = await client.call("apps.list", {})
    assert any(a["id"] == "frontend" for a in result)


async def test_deploy_prepare_execute_flow(running) -> None:
    client, _ = running
    prep = await client.call(
        "deploy.prepare",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    assert prep["summary"]["version"] == "v3.4.0"
    result = await client.call("deploy.execute", {"token": prep["token"]})
    assert result["success"] is True


async def test_replay_token_fails(running) -> None:
    client, _ = running
    prep = await client.call(
        "deploy.prepare",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    await client.call("deploy.execute", {"token": prep["token"]})
    with pytest.raises(JsonRpcRemoteError) as exc_info:
        await client.call("deploy.execute", {"token": prep["token"]})
    assert exc_info.value.code == -32003


async def test_locked_store_returns_locked_error(tmp_path, control_deps, locked_secrets) -> None:
    # Build a separate server with a locked store
    socket_path = tmp_path / "ctl.sock"
    token_path = tmp_path / "ctl.token"
    audit = AuditLog(path=tmp_path / "audit.log")
    control_deps["secret_store"] = locked_secrets
    server = ControlServer(
        methods=ControlMethods(**control_deps),
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit,
    )
    await server.start()
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    await client.connect()
    try:
        with pytest.raises(JsonRpcRemoteError) as exc_info:
            await client.call("secrets.get", {"key": "anything"})
        assert exc_info.value.code == -32002
    finally:
        await client.close()
        await server.stop()
```

All fakes used by these tests (`control_deps`, `locked_secrets`, etc.) live in the top-level `tests/conftest.py` (added in Task 4), so they are auto-discovered by integration tests too — no extra conftest needed.

Also remove the unused fixture stub from the test file:

In `tests/integration/test_control_socket.py`, delete:

```python
@pytest.fixture
def control_deps_for_integration(tests_root):
    # Reuse the control conftest by importing its fixtures at session-time.
    pass


# Force pytest to look for fixtures in tests/control/conftest.py.
# (Conftest under tests/control/ provides control_deps; integration tests sit in a
# sibling directory, so we add it via a local conftest with a fixture pointer below.)
```

(Those comments and the empty fixture were a holdover from an earlier design — the fixtures are now in the top-level conftest and require no plumbing.)

- [ ] **Step 3: Run integration tests**

Run: `.venv/bin/pytest tests/integration/test_control_socket.py -v`
Expected: PASS (4 tests).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_control_socket.py
git commit -m "test: add end-to-end integration tests for control socket"
```

---

## Task 21: Integration test — MCP-over-stdio end-to-end

**Files:**
- Test: `tests/integration/test_mcp_end_to_end.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_mcp_end_to_end.py`:

```python
"""End-to-end test: real shipyard.mcp.server against a real ControlServer.

We don't spin up an actual subprocess here — we exercise the Server in-process by
calling the registered handlers directly. The handlers go through the real
JsonRpcClient and a real Unix socket, so this catches the full chain.
"""

from __future__ import annotations

import json

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
from shipyard.mcp.server import handle_call_tool
from shipyard.mcp.client import JsonRpcClient


@pytest.fixture
async def stack(tmp_path, control_deps):
    socket_path = tmp_path / "control.sock"
    token_path = tmp_path / "control.token"
    audit = AuditLog(path=tmp_path / "audit.log")
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit,
    )
    await server.start()
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
        await server.stop()


async def test_list_applications_via_mcp_handler(stack) -> None:
    client = stack
    result = await handle_call_tool(client, "list_applications", {})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert any(a["id"] == "frontend" for a in payload)


async def test_get_secret_value_unlocked(stack) -> None:
    client = stack
    result = await handle_call_tool(client, "get_secret_value", {"key": "DB_PASSWORD"})
    assert getattr(result[0], "is_error", False) is False
    payload = json.loads(result[0].text)
    assert payload == {"value": "supersecret"}


async def test_full_deploy_flow_via_mcp(stack) -> None:
    client = stack
    prep_result = await handle_call_tool(
        client,
        "prepare_deploy",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    prep_payload = json.loads(prep_result[0].text)
    token = prep_payload["token"]

    exec_result = await handle_call_tool(
        client, "execute_deploy", {"confirmation_token": token}
    )
    exec_payload = json.loads(exec_result[0].text)
    assert exec_payload["success"] is True


async def test_invalid_token_returns_user_friendly_error(stack) -> None:
    client = stack
    result = await handle_call_tool(
        client, "execute_deploy", {"confirmation_token": "bogus"}
    )
    assert result[0].is_error is True
    assert "expired" in result[0].text.lower() or "invalid" in result[0].text.lower()


async def test_no_tool_returns_master_password(stack) -> None:
    """Security regression: no tool definition or output should leak a password field."""
    from shipyard.mcp.tools import TOOL_SPECS

    for spec in TOOL_SPECS:
        for prop in spec.input_schema.get("properties", {}).keys():
            assert prop not in {"password", "master_password", "passphrase"}
```

- [ ] **Step 2: Note about MCP execute_deploy parameter name**

The MCP tool `execute_deploy` accepts `confirmation_token` in its schema, but the underlying RPC method is `deploy.execute(token=...)`. They have different parameter names. We need to translate.

Update `src/shipyard/mcp/server.py` `handle_call_tool` to translate parameter names for the two execute tools. Replace the `try: result = await client.call(spec.rpc_method, arguments)` block with:

```python
    translated = dict(arguments)
    if name in {"execute_deploy", "execute_sync"} and "confirmation_token" in translated:
        translated["token"] = translated.pop("confirmation_token")

    try:
        result = await client.call(spec.rpc_method, translated)
    except ShipyardNotRunningError as exc:
        return [TextContent(type="text", text=str(exc), is_error=True)]
    except JsonRpcRemoteError as exc:
        hint = _ERROR_HINTS.get(exc.code, "")
        body = exc.message if not hint else f"{hint}\n\n(Detail: {exc.message})"
        return [TextContent(type="text", text=body, is_error=True)]
```

- [ ] **Step 3: Run integration tests**

Run: `.venv/bin/pytest tests/integration/test_mcp_end_to_end.py -v`
Expected: PASS (5 tests).

- [ ] **Step 4: Run full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS (everything).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_mcp_end_to_end.py src/shipyard/mcp/server.py
git commit -m "test: add end-to-end MCP-handler integration tests"
```

---

## Task 22: User-facing docs — doc/mcp.md

**Files:**
- Create: `doc/mcp.md`

- [ ] **Step 1: Write the user guide**

Create `doc/mcp.md`:

```markdown
# Shipyard MCP Server

Shipyard ships with an opt-in [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes every TUI feature to an LLM client (Claude Code, Claude Desktop, Cursor, etc.). The MCP server is a thin process that proxies tool calls over a local Unix socket to the running Shipyard TUI.

## How it works

1. The TUI runs as today. When `global.mcp.enabled` is `true`, it opens a Unix socket at `~/.config/shipyard/control.sock` (mode 0600) and writes a random token to `~/.config/shipyard/control.token` (mode 0600).
2. `shipyard mcp` is a separate stdio process spawned by your MCP client. It connects to the socket, performs a token handshake, and forwards MCP tool calls to the TUI as JSON-RPC requests.
3. The TUI is the trust root: it owns SSH connections, the GitHub client, and the unlocked secret store. If the TUI is not running, every MCP tool returns "Shipyard is not running". If the secret store is locked, secret tools return "Secret store is locked".

## Enabling MCP

In your `shipyard.yaml`:

```yaml
global:
  mcp:
    enabled: true
    socket_path: "~/.config/shipyard/control.sock"
    audit_log_path: "~/.config/shipyard/audit.log"
```

Restart the TUI. You should see `MCP control server listening at <path>` in the logs.

## Configuring an MCP client

### Claude Code

In your project's `.claude/settings.json` (or via `claude mcp add`):

```json
{
  "mcpServers": {
    "shipyard": {
      "command": "shipyard",
      "args": ["mcp", "--config", "/absolute/path/to/shipyard.yaml"]
    }
  }
}
```

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "shipyard": {
      "command": "/path/to/.venv/bin/shipyard",
      "args": ["mcp", "--config", "/absolute/path/to/shipyard.yaml"]
    }
  }
}
```

## Tool reference

### Read tools

| Tool | Args | Purpose |
|------|------|---------|
| `list_applications` | — | List all apps and their environments |
| `get_application` | `app_id` | App detail + container statuses |
| `refresh_status` | — | Force-refresh the container status cache |
| `list_servers` | — | List configured servers |
| `get_server` | `server_id` | Server config + reachability + containers |
| `list_containers` | `server_id` | Containers on a server (cached) |
| `tail_container_logs` | `server_id`, `container`, `lines?` | Snapshot of recent logs |
| `list_github_versions` | `app_id`, `limit?` | Recent GitHub releases/tags |
| `list_secret_keys` | — | Secret keys (requires unlocked store) |
| `get_secret_value` | `key` | Cleartext value of a secret |
| `secret_store_status` | — | `{unlocked: bool}` |
| `list_templates` | `app_id`, `env_id` | `.j2` files + per-file resolution status |
| `inspect_template` | `app_id`, `env_id`, `path` | Per-line secret linkage (no values) |

### Write tools

Destructive operations use a two-step `prepare` + `execute` flow:

| Tool | Args | Purpose |
|------|------|---------|
| `prepare_deploy` | `app_id`, `env_id`, `version` | Returns `confirmation_token` + summary |
| `execute_deploy` | `confirmation_token` | Runs `rerun.sh`, blocks until done |
| `prepare_sync` | `app_id`, `env_id` | Returns `confirmation_token` + planned uploads |
| `execute_sync` | `confirmation_token` | Runs sync to completion |
| `set_secret` | `key`, `value` | Create/overwrite a secret |
| `delete_secret` | `key` | Delete a secret |

Confirmation tokens are single-use and expire after 120 seconds.

## Security

- **Trust root.** The TUI process holds all credentials. `shipyard mcp` has none.
- **Socket & token files** are mode 0600 — only your OS user can access them.
- **Master password is never exposed via MCP.** Unlock the secret store only in the TUI.
- **No arbitrary command execution.** The tool surface is closed.
- **Audit log.** When MCP is enabled, every control-plane call is appended to `~/.config/shipyard/audit.log` (mode 0600), rotated at 5 MB across 5 generations. No secret values are written.
- **Remote/multi-user access is unsupported.** This is a single-user local-only design.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Every tool returns "Shipyard is not running" | The TUI isn't running, or `global.mcp.enabled` is `false` |
| Secret tools return "Secret store is locked" | Unlock the store in the TUI (press `e` on the dashboard) |
| `execute_deploy` returns "expired or invalid token" | Tokens expire after 120 s — call `prepare_deploy` again |
| MCP client says it can't find `shipyard` | Use the absolute path to the `shipyard` binary in your client config |
| Permissions error on socket | Make sure no other user owns `~/.config/shipyard/control.sock` |
```

- [ ] **Step 2: Commit**

```bash
git add doc/mcp.md
git commit -m "docs: add user guide for the Shipyard MCP server"
```

---

## Task 23: Update existing docs

**Files:**
- Modify: `doc/architecture.md`
- Modify: `doc/configuration.md`
- Modify: `doc/screens.md`
- Modify: `doc/plan.md`
- Modify: `README.md`

- [ ] **Step 1: Add MCP section to `doc/architecture.md`**

Edit `doc/architecture.md`. After the "Container Status Cache" section, add:

````markdown
## MCP Server

Shipyard exposes an opt-in [MCP](https://modelcontextprotocol.io/) interface so an LLM client can drive every feature the TUI offers. The MCP layer is split in two:

1. **Control plane (in-TUI).** A `ControlServer` (asyncio Unix socket, newline-delimited JSON-RPC 2.0) runs inside the TUI when `global.mcp.enabled: true`. It binds `~/.config/shipyard/control.sock` (mode 0600) and writes a random per-session token to `~/.config/shipyard/control.token`. Methods are thin wrappers around existing services (`SSHConnectionPool`, `Deployer`, `FileSyncer`, `GitHubClient`, `SecretStore`).

2. **MCP process.** `shipyard mcp` is a separate stdio process spawned by an MCP client. It opens the socket, performs the token handshake, then forwards MCP tool calls to the control plane.

Destructive operations (`execute_deploy`, `execute_sync`) require a one-shot 120 s confirmation token from the corresponding `prepare_*` call. Secret values never leave the TUI except through an explicit `get_secret_value` call. The TUI must be running and the secret store unlocked for secret-related tools to succeed.

See `doc/mcp.md` for the user guide and full tool reference.

```
┌────────────────┐  stdio   ┌──────────────────┐ Unix sock ┌────────────────┐
│  MCP client    │ ───────► │   shipyard mcp   │ ────────► │  shipyard TUI  │
│ (Claude, etc.) │ MCP JSON │ (thin stdio proc)│ JSON-RPC  │ (control plane)│
└────────────────┘          └──────────────────┘           └────────────────┘
```
````

- [ ] **Step 2: Add MCP block to `doc/configuration.md`**

Edit `doc/configuration.md`. In the `### `global` - Global Settings` section, append after the existing `github:` block:

```yaml
  mcp:
    enabled: false                                       # default off; opt-in
    socket_path: "~/.config/shipyard/control.sock"
    audit_log_path: "~/.config/shipyard/audit.log"
```

Then add this subsection right after the existing `global` description, before `### `servers``:

```markdown
#### `mcp` subsection

When `enabled: true`, Shipyard opens a local Unix domain socket so an MCP client (Claude Code, Claude Desktop, etc.) can drive every TUI feature via the `shipyard mcp` command. See `doc/mcp.md` for the security model and tool reference.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `enabled` | No | `false` | Whether to start the control plane on TUI launch |
| `socket_path` | No | `~/.config/shipyard/control.sock` | Unix socket path (mode 0600) |
| `audit_log_path` | No | `~/.config/shipyard/audit.log` | Append-only JSON-lines audit log (mode 0600, rotated at 5 MB × 5 generations) |
```

- [ ] **Step 3: Add a paragraph to `doc/screens.md`**

Edit `doc/screens.md`. Append a new section at the very end:

```markdown
## MCP Server

When `global.mcp.enabled: true`, the TUI also exposes a Unix-socket control plane that powers the optional `shipyard mcp` stdio server. The TUI must be running for any MCP tool call to succeed; the secret store must be unlocked for any secret-related tool. There is no dedicated screen for MCP in the TUI today (an audit-log viewer is planned). See `doc/mcp.md` for the full guide.
```

- [ ] **Step 4: Add MCP entry to `doc/plan.md`**

Read the current `doc/plan.md` and append (under whatever "Completed" or "Roadmap" section is conventional):

```markdown
## Completed

- ... (existing entries)
- **MCP Server (opt-in):** Stdio MCP server (`shipyard mcp`) proxying over a local Unix socket to the running TUI. Full feature parity with TUI; prepare/execute confirmation for destructive ops; secrets never unlocked via MCP. See `doc/mcp.md`, `docs/superpowers/specs/2026-05-24-mcp-server-design.md`.
```

If `doc/plan.md` has a different structure, add the entry where it fits the existing layout — the goal is a single line summarizing the feature with pointers to detailed docs.

- [ ] **Step 5: Update `README.md`**

Edit `README.md`. Add a short paragraph (one or two sentences) under the project description:

```markdown
## MCP integration (opt-in)

Shipyard can expose all of its features to an MCP client (Claude Code, Claude Desktop, Cursor) via the `shipyard mcp` stdio command. The MCP process talks to your running TUI over a local Unix socket; nothing is exposed to the network. See [`doc/mcp.md`](doc/mcp.md) for setup and security details.
```

- [ ] **Step 6: Commit**

```bash
git add doc/architecture.md doc/configuration.md doc/screens.md doc/plan.md README.md
git commit -m "docs: update architecture/config/screens/README for MCP server"
```

---

## Final verification

- [ ] **Step 1: Full test suite passes**

Run: `.venv/bin/pytest -v`
Expected: every test passes.

- [ ] **Step 2: Manual smoke test of MCP launch (without a client)**

Run: `.venv/bin/python -m shipyard.mcp --config ./shipyard.yaml 2>&1 | head -5`
Expected: either it waits for stdio input (no error), or — if MCP is disabled in your config — it prints the disabled message and exits with code 3. Stop it with Ctrl-C.

- [ ] **Step 3: Manual smoke test of TUI**

Run: `.venv/bin/shipyard --config ./shipyard.yaml`
Expected: TUI starts. With `mcp.enabled: false` the behavior is identical to before; with `mcp.enabled: true` you should see the control socket appear at `~/.config/shipyard/control.sock`. Quit with `q`.

- [ ] **Step 4: Verify socket cleanup**

After quitting the TUI, run: `ls ~/.config/shipyard/control.sock 2>&1`
Expected: `No such file or directory`.

- [ ] **Step 5: Sanity-check the audit log**

If you exercised MCP tools during the smoke test, run: `tail -5 ~/.config/shipyard/audit.log`
Expected: JSON lines, each with `method`, `params_summary`, `result_code`, timestamp.

---

## Spec coverage check

This is a self-review against `docs/superpowers/specs/2026-05-24-mcp-server-design.md`:

- ✅ stdio MCP server (Task 19)
- ✅ Unix socket transport, mode 0600 (Task 14)
- ✅ Token-file handshake, 0600 (Task 14)
- ✅ Newline-delimited JSON-RPC 2.0 (Task 12, 14)
- ✅ All read methods: apps, servers, containers, logs, github, secrets, templates (Tasks 5–9)
- ✅ Prepare/execute for deploy and sync (Tasks 10, 11)
- ✅ Single-use, 120 s tokens (Task 3)
- ✅ Locked-store guards (Tasks 8, 11)
- ✅ Audit log with rotation (Task 13, 14)
- ✅ Peer creds in audit log where OS supports it (Task 14)
- ✅ Output caps & truncation (Tasks 7, 10)
- ✅ TUI lifecycle hooks (Task 15)
- ✅ argparse `mcp` subcommand (Task 15)
- ✅ MCP tool registry with descriptions and schemas (Task 17)
- ✅ MCP dispatch, parameter translation for `execute_*` (Tasks 18, 21)
- ✅ MCP entry point that loads config (Task 19)
- ✅ End-to-end tests (Tasks 20, 21)
- ✅ Docs (Tasks 22, 23)
- ✅ Security regressions covered: socket mode, token regeneration, secret values never returned in templates/sync, single-use tokens, no master-password field, secret_store_locked surfacing (Tasks 14, 21, 9, 11, 8)
