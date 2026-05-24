"""Shared test fixtures."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shipyard.config.schema import (
    ApplicationConfig,
    EnvironmentConfig,
    GitHubRepoConfig,
    GitHubSettings,
    GlobalSettings,
    ShipyardConfig,
    ServerConfig,
    SSHSettings,
)


@pytest.fixture
def sample_config_dict() -> dict:
    """A valid config dict for testing."""
    return {
        "global": {
            "ssh": {
                "default_user": "deploy",
                "key_path": "~/.ssh/id_ed25519",
                "connect_timeout": 10,
                "keepalive_interval": 30,
            },
            "github": {
                "token_env": "GITHUB_TOKEN",
            },
        },
        "servers": {
            "prod-01": {
                "hostname": "10.0.1.10",
                "port": 22,
                "user": "deploy",
                "description": "Production server",
            },
            "staging-01": {
                "hostname": "10.0.2.10",
                "port": 22,
                "description": "Staging server",
            },
        },
        "applications": {
            "frontend": {
                "name": "Frontend App",
                "description": "Next.js frontend",
                "github": {
                    "repo": "myorg/frontend",
                    "track": "releases",
                },
                "environments": {
                    "prd": {
                        "server": "prod-01",
                        "path": "/opt/apps/frontend",
                        "containers": ["frontend-prd-web", "frontend-prd-nginx"],
                    },
                    "staging": {
                        "server": "staging-01",
                        "path": "/opt/apps/frontend",
                        "containers": ["frontend-staging-web"],
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_config(sample_config_dict: dict) -> ShipyardConfig:
    """A valid ShipyardConfig for testing."""
    return ShipyardConfig.model_validate(sample_config_dict)


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


@pytest.fixture
def short_tmp(tmp_path) -> Path:
    """Return a tmp dir with a path short enough for AF_UNIX (104-char limit on macOS)."""
    p = str(tmp_path)
    if len(p) + len("/control.sock") > 100:
        # Fall back to a short path under /tmp
        d = Path(tempfile.mkdtemp(prefix="sy_", dir="/tmp"))
        return d
    return tmp_path
