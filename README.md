# Shipyard

A terminal UI for deploying Docker applications to remote servers via SSH.

Each application has a `rerun.sh` script on the target server — Shipyard provides a visual interface to trigger deploys, monitor container status, and view logs across multiple servers and environments.

## Features

- **Dashboard** — overview of all applications and their environments
- **Multi-environment** — manage prd, staging, uat, etc. per application
- **Deploy with live output** — select a version from GitHub releases/tags, watch the deploy stream in real time
- **Container status** — `docker ps` status for every container, fetched over SSH
- **Log viewer** — stream `docker logs -f` output directly in the terminal
- **Server overview** — connectivity status, Docker version, and container counts for all servers

## Installation

Requires Python 3.11+.

```bash
# Using uv
uv venv
uv pip install -e ".[dev]"

# Or using pip
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
# Run with a config file
shipyard --config shipyard.yaml

# Or use the default lookup order:
#   ./shipyard.yaml → ~/.config/shipyard/config.yaml
shipyard

# Run as a Python module
python -m shipyard --config shipyard.yaml

# Run with Textual dev console (for debugging)
textual run --dev -c shipyard --config shipyard.yaml
```

## Configuration

Copy `config.example.yaml` to `shipyard.yaml` and edit it. The file has three sections:

```yaml
global:
  ssh:
    default_user: "deploy"
    key_path: "~/.ssh/id_ed25519"
    connect_timeout: 10
    keepalive_interval: 30
  github:
    token_env: "GITHUB_TOKEN"

servers:
  prod-web-01:
    hostname: "10.0.1.10"
    port: 22
    user: "deploy"
    key_path: "~/.ssh/prod_key"
    description: "Production web server 1"

applications:
  frontend:
    name: "Frontend App"
    description: "Next.js frontend application"
    github:
      repo: "myorg/frontend"
      track: "releases"        # or "tags"
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
```

See `doc/configuration.md` for the full schema reference.

## Keyboard shortcuts

| Key      | Action              |
| -------- | ------------------- |
| `d`      | Deploy              |
| `l`      | View logs           |
| `r`      | Refresh             |
| `s`      | Servers overview    |
| `escape` | Back                |
| `q`      | Quit                |

## Project layout

```
src/shipyard/
├── app.py              # Main Textual App entry point
├── config/             # YAML config loading and Pydantic models
├── ssh/                # AsyncSSH connection pool and command execution
├── github/             # GitHub API client (releases and tags)
├── deploy/             # Deployment logic (rerun.sh over SSH)
├── screens/            # Textual screens (dashboard, deploy, logs, etc.)
├── widgets/            # Reusable Textual widgets
└── styles/             # Textual CSS
```

## Testing

```bash
pytest
```

## Tech stack

- [Textual](https://textual.textualize.io/) — TUI framework
- [AsyncSSH](https://asyncssh.readthedocs.io/) — async SSH connections
- [Pydantic v2](https://docs.pydantic.dev/) — configuration validation
- [httpx](https://www.python-httpx.org/) — async GitHub API client
