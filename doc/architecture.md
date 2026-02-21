# Shipyard - Architecture Document

## Overview

Shipyard is a terminal TUI application for managing Docker deployments across multiple servers. It provides a visual interface for deploying applications, monitoring container status, and viewing logs -- all through SSH connections using the user's existing SSH keys.

## Core Concepts

### Application
An application is a deployable unit tracked in GitHub. It consists of one or more Docker containers and can be deployed to multiple environments. Each application has a `rerun.sh` deploy script already present on its target servers.

### Environment
An environment (prd, uat, staging, etc.) is a deployment target for an application. Each environment maps to a specific server and a path on that server where the application's config folder (containing `rerun.sh`) lives. Not every application has every environment.

### Server
A server is a remote machine accessible via SSH. Multiple applications and environments can share the same server.

### Container
A Docker container is a running instance that belongs to an application. Containers are tracked by name for status monitoring via `docker ps`.

## Architecture Layers

```
┌─────────────────────────────────────────────────┐
│                   TUI Layer                      │
│  Screens: Dashboard, Application, Deploy,        │
│           Servers, ServerDetail, Logs             │
│  Widgets: EnvironmentPanel, DeployProgress,      │
│           StatusIndicator, FetchStatusBar        │
├─────────────────────────────────────────────────┤
│                Service Layer                     │
│  Deploy:   deployer.py (run rerun.sh)           │
│  GitHub:   client.py (releases, tags)           │
│  Config:   manager.py (load, validate, resolve) │
├─────────────────────────────────────────────────┤
│              Infrastructure Layer                │
│  SSH:      connection.py (connection pool)       │
│            executor.py (command execution)       │
│  Config:   schema.py (Pydantic models)          │
├─────────────────────────────────────────────────┤
│                External Systems                  │
│  Remote servers (via SSH)                        │
│  Docker daemon (via docker CLI over SSH)         │
│  GitHub API (via HTTPS)                          │
└─────────────────────────────────────────────────┘
```

## Module Details

### config/schema.py - Data Models

Pydantic v2 models that define and validate the YAML configuration:

- `ShipyardConfig` - Root model with `global`, `servers`, `applications`
- `GlobalSettings` - SSH defaults, GitHub settings
- `ServerConfig` - hostname, port, user, key_path, description
- `ApplicationConfig` - name, description, github, containers, environments
- `EnvironmentConfig` - server reference, path to config folder
- `ContainerRef` - container name for status tracking
- `GitHubRepoConfig` - repo (owner/repo), track (releases/tags)

### config/manager.py - Configuration Management

Loads the YAML config file, validates it against the Pydantic schema, and provides methods to access resolved configuration. Validates cross-references (e.g., environment server references must exist in the servers section).

Config file lookup order:
1. `--config` CLI argument
2. `./shipyard.yaml` (current directory)
3. `~/.config/shipyard/config.yaml`

### ssh/connection.py - SSH Connection Pool

Manages persistent AsyncSSH connections to servers. Connections are created lazily on first use and cached. Per-server locking prevents duplicate connections. Merges server-specific SSH settings with global defaults.

Key methods:
- `get_connection(server_id)` - Get or create a cached connection
- `check_connection(server_id)` - Test if a server is reachable
- `close_all()` - Clean up all connections on app exit

### ssh/executor.py - Remote Command Execution

Wraps an AsyncSSH connection to provide command execution:

- `run(command)` - Execute and return stdout/stderr/exit_status
- `stream(command)` - Yield stdout lines as they arrive (for live output)

### github/client.py - GitHub API Client

Async HTTP client (httpx) for the GitHub REST API:

- `get_releases(repo)` - List recent releases
- `get_latest_release(repo)` - Get the latest release
- `get_tags(repo)` - List recent tags

Uses the `GITHUB_TOKEN` environment variable for authentication (optional, increases rate limits).

### deploy/deployer.py - Deployment Executor

The deployment is simple by design:

1. SSH to the environment's server
2. `cd` to the environment's config path
3. Run `./rerun.sh <version>`
4. Stream output back to the caller
5. Report success/failure based on exit code

The deployer yields events (output lines, status changes) that the DeployScreen consumes to update the UI in real-time.

## Screen Architecture

Textual's screen stack is used for navigation. The app starts on the DashboardScreen. Screens are pushed/popped as the user navigates.

```
ShipyardApp
├── DashboardScreen (default)
│   ├── → ApplicationScreen (push on enter)
│   │   ├── → DeployScreen (push on 'd')
│   │   │   └── DeployConfirmModal (modal)
│   │   └── → LogViewerScreen (push on 'l')
│   └── → ServersScreen (push on 's')
│       └── → ServerDetailScreen (push on enter)
```

### DashboardScreen
DataTable listing all applications with columns: name, environments, latest GitHub release, aggregated container status. Refreshes status by checking `docker ps` on each server.

### ApplicationScreen
Shows a single application's details. Displays one EnvironmentPanel widget per environment, each showing the server, deploy path, and container statuses (name, image, status, uptime from `docker ps`).

### DeployScreen
Two-phase screen:
1. **Version selection**: Shows recent GitHub releases/tags to pick from
2. **Deploy execution**: After confirmation, streams `rerun.sh` output in a RichLog widget

### ServersScreen
DataTable listing all configured servers with connectivity status (SSH reachable), Docker version, and container counts. Press enter on a row to open the ServerDetailScreen.

### ServerDetailScreen
Shows all Docker containers on a specific server via `docker ps -a --format json`. Displays container name, status (color-coded), image, and uptime in a DataTable.

### LogViewerScreen
Streams `docker logs -f <container>` output from a remote server via SSH. Supports follow mode toggle and clearing the display.

## Container Status Cache

Shipyard uses a two-tier caching model for container status data, populated at startup and refreshable via the `r` key on any screen.

### Tier 1: Server-level cache (`server_container_cache`)

- Keyed by `server_id → list[dict]`
- One unfiltered `docker ps -a --format json` SSH call per configured server
- Contains **all** containers on each server (not just Shipyard-managed ones)
- Used by `ServerDetailScreen` to show every container on a server

### Tier 2: App/env-level cache (`container_cache`)

- Keyed by `app_id → env_id → list[dict]`
- Derived from the server-level cache by matching configured container names
- Containers not found on the server get `status: "unknown"`
- Used by `ApplicationScreen` / `EnvironmentPanel` for per-app container status

Both caches are populated together in `_fetch_all_container_status()`. As each server completes, a `FetchProgress(completed, total)` message is posted so the `FetchStatusBar` widget can show incremental progress (e.g. "Fetching servers: 2/4"). Once all servers are done and the caches are built, a `ContainerCacheUpdated` message is posted so all active screens can react. The status bar turns green at completion and auto-hides after 2 seconds.

## Key Design Decisions

1. **AsyncSSH over paramiko**: AsyncSSH integrates natively with Python's asyncio (which Textual uses). Paramiko requires threading workarounds. AsyncSSH also respects `~/.ssh/config` natively.

2. **Docker CLI over SSH, not docker-py SDK**: Running `docker` commands over SSH avoids docker-py's dependency on paramiko and its known issues with encrypted keys, jump hosts, and SSH agent forwarding. It also requires no extra setup on the server side.

3. **rerun.sh deployment model**: The app doesn't manage Docker containers directly. Each application already has its own deployment script. This keeps the tool simple and compatible with existing deployment workflows.

4. **Pydantic for config validation**: Provides type safety, clear error messages, and serves as living documentation for the config schema.

5. **httpx for GitHub API**: Lightweight async HTTP client. We only need releases and tags endpoints, so a full GitHub SDK would be overkill.

6. **Screen-based navigation**: Textual's screen stack provides a natural push/pop navigation model similar to mobile apps. Each screen is self-contained with its own key bindings.
