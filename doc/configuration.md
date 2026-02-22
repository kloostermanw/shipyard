# Shipyard - Configuration File Design

## Overview

Shipyard uses a single YAML configuration file to define servers, applications, and their environments. The config is validated at startup using Pydantic models, providing clear error messages for any misconfiguration.

## Config File Location

The application looks for configuration in this order:
1. `--config <path>` CLI argument
2. `./shipyard.yaml` in the current directory
3. `~/.config/shipyard/config.yaml`

## Schema

### Top-Level Structure

```yaml
global:       # Global defaults (SSH, GitHub)
servers:      # Server definitions
applications: # Application definitions
```

### `global` - Global Settings

```yaml
global:
  ssh:
    default_user: "deploy"              # Default SSH username for all servers
    key_path: "~/.ssh/id_ed25519"       # Default SSH private key path
    connect_timeout: 10                 # SSH connection timeout in seconds
    keepalive_interval: 30              # Keepalive interval in seconds
  github:
    token_env: "GITHUB_TOKEN"           # Name of env var holding GitHub token
    api_base: "https://api.github.com"  # GitHub API base URL (for GHE)
    polling_interval: 2000              # Workflow status polling interval in ms
```

All fields have sensible defaults. The entire `global` section is optional.

### `servers` - Server Definitions

```yaml
servers:
  <server-id>:                          # Unique identifier, used as reference
    hostname: "10.0.1.10"               # Required: IP or hostname
    port: 22                            # SSH port (default: 22)
    user: "deploy"                      # Overrides global.ssh.default_user
    key_path: "~/.ssh/prod_key"         # Overrides global.ssh.key_path
    description: "Production web 1"     # Human-readable description
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `hostname` | Yes | - | IP address or hostname |
| `port` | No | `22` | SSH port |
| `user` | No | `global.ssh.default_user` | SSH username |
| `key_path` | No | `global.ssh.key_path` | Path to SSH private key |
| `description` | No | `""` | Human-readable description |

### `applications` - Application Definitions

```yaml
applications:
  <app-id>:                             # Unique identifier
    name: "Frontend App"                # Display name
    description: "Next.js frontend"     # Description
    github:
      repo: "myorg/frontend"           # GitHub owner/repo
      track: "releases"                 # "releases" or "tags"
    environments:
      <env-id>:                         # e.g. prd, uat, staging
        server: "prod-web-01"           # References a server from servers section
        path: "/opt/apps/frontend"      # Path to config folder with rerun.sh
        containers:                     # Docker container names for this env
          - "frontend-prd-web"
          - "frontend-prd-nginx"
        local-path: "~/repos/frontend"  # Optional: local dir to sync to remote path
```

#### `github` subsection

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `repo` | Yes | - | GitHub repository in `owner/repo` format |
| `track` | No | `"releases"` | What to track: `"releases"` or `"tags"` |

#### `environments` subsection

Each environment maps to a specific server, a path on that server, and the Docker container names for that environment. Container names are per-environment because they typically differ (e.g., `app-prd-web` vs `app-uat-web`).

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `server` | Yes | - | References a key from the `servers` section |
| `path` | Yes | - | Absolute path to the config folder containing `rerun.sh` |
| `containers` | No | `[]` | List of Docker container names (as shown in `docker ps`) |
| `local-path` | No | `null` | Local directory path to sync to the remote `path` via SFTP. Must be absolute or start with `~`. When set, enables one-way file sync (local → remote) on the Application screen. |

## Validation Rules

The following cross-reference validations are performed at load time:

1. Every `environments[].server` must reference an existing key in `servers`
2. Every `applications` key must be unique
3. Every `servers` key must be unique
4. `github.repo` must be in `owner/repo` format
5. `path` must be an absolute path (starts with `/`)
6. `local-path` (if set) must be absolute or start with `~`

## Complete Example

```yaml
# shipyard.yaml

global:
  ssh:
    default_user: "deploy"
    key_path: "~/.ssh/id_ed25519"
    connect_timeout: 10
    keepalive_interval: 30
  github:
    token_env: "GITHUB_TOKEN"
    polling_interval: 2000

servers:
  prod-web-01:
    hostname: "10.0.1.10"
    port: 22
    user: "deploy"
    key_path: "~/.ssh/prod_key"
    description: "Production web server 1"

  prod-web-02:
    hostname: "10.0.1.11"
    port: 22
    user: "deploy"
    key_path: "~/.ssh/prod_key"
    description: "Production web server 2"

  staging-01:
    hostname: "10.0.2.10"
    port: 22
    description: "Staging server"

  uat-01:
    hostname: "10.0.3.10"
    port: 2222
    description: "UAT server"

applications:
  frontend:
    name: "Frontend App"
    description: "Next.js frontend application"
    github:
      repo: "myorg/frontend"
      track: "releases"
    environments:
      prd:
        server: "prod-web-01"
        path: "/opt/apps/frontend"
        containers:
          - "frontend-prd-web"
          - "frontend-prd-nginx"
      staging:
        server: "staging-01"
        path: "/opt/apps/frontend"
        containers:
          - "frontend-staging-web"
          - "frontend-staging-nginx"

  api-service:
    name: "API Service"
    description: "FastAPI backend with Celery worker"
    github:
      repo: "myorg/api-service"
      track: "releases"
    environments:
      prd:
        server: "prod-web-01"
        path: "/opt/apps/api-service"
        containers:
          - "api-prd-web"
          - "api-prd-worker"
      uat:
        server: "uat-01"
        path: "/opt/apps/api-service"
        containers:
          - "api-uat-web"
          - "api-uat-worker"
      staging:
        server: "staging-01"
        path: "/opt/apps/api-service"
        containers:
          - "api-staging-web"
          - "api-staging-worker"

  admin-panel:
    name: "Admin Panel"
    description: "Internal admin dashboard"
    github:
      repo: "myorg/admin-panel"
      track: "tags"
    environments:
      prd:
        server: "prod-web-02"
        path: "/opt/apps/admin-panel"
        containers:
          - "admin-panel"
```

## Pydantic Models

The YAML configuration is validated against these Pydantic v2 models defined in `src/shipyard/config/schema.py`:

```python
class SSHSettings(BaseModel):
    default_user: str = "root"
    key_path: str = "~/.ssh/id_ed25519"
    connect_timeout: int = 10
    keepalive_interval: int = 30

class GitHubSettings(BaseModel):
    token_env: str = "GITHUB_TOKEN"
    api_base: str = "https://api.github.com"
    polling_interval: int = 2000  # milliseconds

class GlobalSettings(BaseModel):
    ssh: SSHSettings = SSHSettings()
    github: GitHubSettings = GitHubSettings()

class ServerConfig(BaseModel):
    hostname: str
    port: int = 22
    user: str | None = None
    key_path: str | None = None
    description: str = ""

class GitHubRepoConfig(BaseModel):
    repo: str  # "owner/repo"
    track: Literal["releases", "tags"] = "releases"

class EnvironmentConfig(BaseModel):
    server: str           # references servers.<key>
    path: str             # absolute path to config folder
    containers: list[str] = []  # docker container names
    local_path: str | None = Field(default=None, alias="local-path")  # local sync dir

class ApplicationConfig(BaseModel):
    name: str
    description: str = ""
    github: GitHubRepoConfig
    environments: dict[str, EnvironmentConfig]

class ShipyardConfig(BaseModel):
    global_: GlobalSettings = Field(default=GlobalSettings(), alias="global")
    servers: dict[str, ServerConfig]
    applications: dict[str, ApplicationConfig]
```
