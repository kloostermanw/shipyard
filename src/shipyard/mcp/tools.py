"""Static registry of MCP tools exposed by `shipyard mcp`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    rpc_method: str


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
