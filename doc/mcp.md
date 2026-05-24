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
