# Shipyard - Project Plan

## Context

Terminal TUI application in Python (Textual) that manages Docker deployments across multiple servers via SSH. Reads configuration from YAML, connects to servers using local `~/.ssh/` credentials, supports multi-environment and multi-container applications. Each application tracks a GitHub repository.

**Deployment model**: Each application has a config folder on the server containing a `rerun.sh` script. To deploy version `v1.0.0`, SSH into the server, `cd` to the config folder, and run `./rerun.sh v1.0.0`.

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| TUI framework | Textual | Async-native terminal UI framework |
| SSH | AsyncSSH | Native async, works with Textual's event loop, respects `~/.ssh/` |
| Config | PyYAML + Pydantic v2 | YAML parsing + strict validation with clear errors |
| GitHub API | httpx | Async HTTP, lightweight, only need releases/tags |
| Build system | Hatchling | Modern Python packaging |

## Project Structure

```
shipyard/
├── CLAUDE.md
├── pyproject.toml
├── config.example.yaml
├── doc/
│   ├── plan.md
│   ├── architecture.md
│   └── configuration.md
├── src/shipyard/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py                    # Main Textual App
│   ├── config/
│   │   ├── schema.py            # Pydantic models
│   │   └── manager.py           # Load, validate config
│   ├── ssh/
│   │   ├── connection.py        # AsyncSSH connection pool
│   │   └── executor.py          # Remote command execution
│   ├── github/
│   │   └── client.py            # GitHub releases/tags API
│   ├── deploy/
│   │   └── deployer.py          # Run rerun.sh over SSH
│   ├── screens/
│   │   ├── dashboard.py         # Home: app list
│   │   ├── application.py       # App detail: envs + containers
│   │   ├── deploy.py            # Deploy progress
│   │   ├── servers.py           # Server status
│   │   ├── server_detail.py    # Server detail: all containers
│   │   └── logs.py              # Container log viewer
│   ├── widgets/
│   │   ├── environment_panel.py
│   │   ├── deploy_progress.py
│   │   └── status_indicator.py
│   └── styles/
│       └── app.tcss
└── tests/
```

## Deployment Flow

1. User picks application + environment + version (from GitHub releases/tags)
2. Confirm dialog: "Deploy frontend v1.2.0 to prd on prod-web-01?"
3. SSH to the environment's server
4. `cd` to the environment's path
5. Run: `./rerun.sh v1.2.0`
6. Stream stdout/stderr back to the TUI in real-time
7. Show success/failure based on exit code

## Screens

- **Dashboard**: Application list with environment status overview
- **Application**: Per-app detail with environment panels showing containers
- **Deploy**: Version selection, confirmation, live output streaming
- **Servers**: Server connectivity and resource overview
- **Server Detail**: All Docker containers on a specific server
- **Logs**: Live container log streaming via SSH

## Implementation Order

1. Documentation (doc/, CLAUDE.md)
2. pyproject.toml + package skeleton
3. config/schema.py - Pydantic models
4. config/manager.py - YAML loading + validation
5. config.example.yaml
6. ssh/connection.py - AsyncSSH connection pool
7. ssh/executor.py - Command execution + streaming
8. github/client.py - Fetch releases and tags
9. deploy/deployer.py - Run rerun.sh, stream output
10. styles/app.tcss - TUI styling
11. widgets/ - Reusable UI components
12. screens/ - All 5 screens
13. app.py - Main app wiring
14. tests/
