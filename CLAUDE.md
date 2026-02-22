# Shipyard - Docker Deployment TUI

## What is this?

A terminal TUI application (Python/Textual) for deploying Docker applications to remote servers via SSH. Each application has a `rerun.sh` script on the server -- this tool provides a visual interface to trigger deploys, monitor container status, and view logs.

## Tech Stack

- **Python 3.11+**
- **Textual** - TUI framework
- **AsyncSSH** - SSH connections (async-native)
- **Pydantic v2** - Configuration validation
- **PyYAML** - YAML parsing
- **httpx** - GitHub API client (async)
- **Hatchling** - Build system

## Project Layout

```
src/shipyard/
├── app.py              # Main Textual App entry point
├── config/             # YAML config loading and Pydantic models
│   ├── schema.py       # Pydantic models (ShipyardConfig, ServerConfig, etc.)
│   └── manager.py      # Load, validate, resolve configuration
├── ssh/                # SSH connection management
│   ├── connection.py   # AsyncSSH connection pool
│   └── executor.py     # Remote command execution + streaming
├── github/             # GitHub API integration
│   └── client.py       # Fetch releases/tags
├── deploy/             # Deployment logic
│   └── deployer.py     # Run rerun.sh over SSH, stream output
├── sync/               # File sync (local → remote)
│   └── syncer.py       # SFTP file sync via SSH connections
├── screens/            # Textual screens (views)
│   ├── dashboard.py    # Home screen: app list
│   ├── application.py  # App detail: environments + containers
│   ├── deploy.py       # Deploy version selection + progress
│   ├── sync.py         # File sync progress screen
│   ├── servers.py      # Server status overview
│   ├── server_detail.py # Server detail: all containers on a server
│   └── logs.py         # Live container log viewer
├── widgets/            # Reusable Textual widgets
└── styles/             # Textual CSS files
    └── app.tcss
```

## How to Run

```bash
# Create venv and install (using uv)
uv venv
uv pip install -e ".[dev]"

# Run the app
.venv/bin/shipyard --config shipyard.yaml
# or
.venv/bin/python -m shipyard --config shipyard.yaml

# Run with Textual dev console (for debugging)
.venv/bin/textual run --dev -c shipyard --config shipyard.yaml
```

## Configuration

Config file: `shipyard.yaml` (see `config.example.yaml` and `doc/configuration.md`)

Lookup order: `--config` flag > `./shipyard.yaml` > `~/.config/shipyard/config.yaml`

## Key Patterns

- **Async everywhere**: All SSH and HTTP operations use async/await
- **Textual workers**: Background tasks use `@work` decorator or `run_worker()`
- **Screen stack**: Navigation uses `push_screen()` / `pop_screen()`
- **Pydantic validation**: Config is validated on load, cross-references checked
- **SSH connection pooling**: Connections are lazily created and reused

## Testing

```bash
.venv/bin/pytest
```

## Documentation
Every time there is a change to this application, this documentation files needs to be updated.

- `doc/plan.md` - Project plan
- `doc/architecture.md` - Architecture and design decisions
- `doc/configuration.md` - Configuration file schema reference
- `doc/screens.md` - Every screen of the application