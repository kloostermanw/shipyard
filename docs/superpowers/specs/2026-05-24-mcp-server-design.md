# Shipyard MCP Server — Design

**Status:** Draft
**Date:** 2026-05-24
**Author:** Wiebe (with Claude)

## Summary

Add a Model Context Protocol (MCP) server to Shipyard so an LLM client (Claude Code, Claude Desktop, Cursor, etc.) can drive every user-facing feature the TUI exposes: list applications, view container/server status, fetch GitHub versions, deploy, sync files (including `.j2` template rendering), tail logs, and manage encrypted secrets.

The MCP server is a thin stdio process that forwards calls over a local Unix domain socket to the running Shipyard TUI. The TUI is the trust root: it owns the unlocked secret store, the SSH connection pool, and the GitHub client. If the TUI is not running, MCP returns a clear error. If the secret store is locked, secret tools return a locked-store error. Destructive operations (deploy, sync) use a two-step `prepare`/`execute` token flow so the LLM is forced to surface a structured summary before committing.

## Goals

- Full feature parity with the TUI, accessible from any MCP client.
- A single, consistent trust root (the running TUI process).
- No new attack surface for secrets: no MCP-side key material, no master-password tool, no value leakage in tool output beyond explicit `get_secret_value` calls.
- Opt-in: control plane only starts when explicitly enabled in `shipyard.yaml`.

## Non-goals

- Remote / multi-user access (HTTP transport with auth is out of scope).
- Protecting against a fully compromised user account.
- Live streaming of deploy output or container logs via the MCP protocol (block-and-return for deploys, finite snapshot for logs).
- Unlocking the secret store from MCP.
- Arbitrary remote command execution via MCP.
- A `shipyard ctl` CLI on top of the control socket (control plane is designed to support one later; no CLI is built in v1).

## Architecture

```
   ┌────────────────────────┐                    ┌────────────────────────┐
   │   MCP client           │                    │  shipyard TUI (running)│
   │ (Claude Code/Desktop)  │                    │                        │
   └──────────┬─────────────┘                    │   ┌──────────────────┐ │
              │ stdio (MCP/JSON-RPC)             │   │ Control server   │ │
              ▼                                  │   │ (asyncio,        │ │
   ┌────────────────────────┐  Unix sock (0600)  │   │  JSON-RPC over   │ │
   │   shipyard mcp         │ ─────────────────► │   │  newline frames) │ │
   │  (thin stdio process)  │                    │   └────────┬─────────┘ │
   └────────────────────────┘                    │            │           │
                                                 │   Services (existing): │
                                                 │   SSHConnectionPool    │
                                                 │   Deployer, FileSyncer │
                                                 │   GitHubClient         │
                                                 │   SecretStore          │
                                                 └────────────────────────┘
```

### New modules

Under `src/shipyard/`:

- `mcp/` — the stdio MCP server process.
  - `__main__.py` — `python -m shipyard.mcp`, entry point for `shipyard mcp`.
  - `server.py` — MCP protocol handling: tool registration, request dispatch, response shaping, input validation.
  - `client.py` — JSON-RPC client that connects to the TUI's control socket, performs the token handshake, and forwards requests.
- `control/` — the in-TUI control plane.
  - `server.py` — asyncio Unix-socket server, line-delimited JSON-RPC 2.0.
  - `methods.py` — RPC method handlers; thin wrappers over existing services. No new business logic.
  - `jobs.py` — in-memory job registry for confirmation tokens (`prepare` → `execute`).

### Existing module changes

- `app.py` `ShipyardApp.on_mount` — start the control server if `global.mcp.enabled` is true. Before binding, unlink any stale socket file at `socket_path` (Shipyard never runs twice as the same user, so a leftover socket is a crash artifact). Bind, then `chmod 0600`, then write the freshly generated token file with mode 0600.
- `app.py` `ShipyardApp.on_unmount` — close the control server and `try/finally` unlink the socket and token files. Idempotent (it is fine if they were already removed).
- `app.py` `main()` — extend the argparse parser with subcommands. The default subcommand (or no subcommand) keeps today's behavior (launch the TUI). A new `mcp` subcommand dispatches to `shipyard.mcp.__main__:main`, so `shipyard mcp` and `shipyard` share one binary.
- `config/schema.py` — add `MCPSettings` (see Configuration below).
- `pyproject.toml` — add `mcp>=1.0` dependency (Anthropic Python MCP SDK).

## Control protocol (TUI ↔ shipyard mcp)

### Transport

- Unix domain socket at `~/.config/shipyard/control.sock`, mode 0600. OS-enforced owner-only access.
- Token file at `~/.config/shipyard/control.token`, mode 0600, containing a 32-byte random token (regenerated on each TUI start).
- First frame from any client connection must be `{"hello": "<token>"}`. Otherwise the server closes the connection without further response.

### Framing

Newline-delimited JSON, one JSON-RPC 2.0 message per line. Requests have `id`, `method`, `params`. Responses have `id`, `result` or `error`. No batching, no server→client notifications.

### Error codes

| Code | Meaning |
|------|---------|
| `-32001` | `shipyard_not_running` (synthesized by `shipyard mcp` when the socket is unavailable — never seen on the wire) |
| `-32002` | `secret_store_locked` |
| `-32003` | `invalid_confirmation_token` (unknown, expired, or already consumed) |
| `-32004` | `ssh_error` (remote command failed at the transport level) |
| `-32005` | `not_found` (unknown app / env / server / container / secret / template) |
| `-32006` | `validation_error` (bad input shape) |
| `-32099` | `internal_error` (catch-all; logged with stack trace server-side, no internals returned over the wire) |

### Read methods

- `apps.list` → list of `{id, name, description, github: {repo, track}, environments: [{id, server, path, has_local_path}]}`
- `apps.get(app_id)` → app config plus per-env container statuses from cache
- `apps.refresh_status()` → triggers `_fetch_all_container_status()`; resolves when complete
- `servers.list` → list of `{id, hostname, port, user, description}`
- `servers.get(server_id)` → server config + reachability + all containers from `server_container_cache`
- `containers.list(server_id)` → containers on a server from the cache
- `logs.tail(server_id, container, lines=200)` → finite snapshot of `docker logs --tail N`
- `github.versions(app_id, limit=20)` → recent releases/tags via `GitHubClient`
- `secrets.list_keys()` → `[string]`; returns `secret_store_locked` if locked
- `secrets.get(key)` → `{value}`; returns `secret_store_locked` if locked, `not_found` if missing
- `secrets.is_unlocked()` → `{unlocked: bool}` (safe to call any time)
- `templates.list(app_id, env_id)` → list of `.j2` files in `local-path` with per-file variable resolution status
- `templates.inspect(app_id, env_id, path)` → per-line entries with secret linkage status (LINKED/MISSING/PLAIN); never includes resolved values for LINKED rows

### Prepare/execute methods (destructive)

- `deploy.prepare(app_id, env_id, version)` → `{token, summary: {server, path, version, containers, current_versions}}`
- `deploy.execute(token)` → blocks until `rerun.sh` exits; returns `{success, exit_code, stdout, stderr, started_at, completed_at}`
- `sync.prepare(app_id, env_id)` → `{token, summary: {local_path, remote_path, planned_uploads: [...], template_files: [...]}}`. Computed by reusing `FileSyncer`'s existing scan/check logic (no transfers). If `template_files` is non-empty and the secret store is locked, returns `secret_store_locked` immediately — no token is issued, since `execute_sync` could not succeed.
- `sync.execute(token)` → blocks; returns `{success, transferred: [path], skipped: [path]}`. Output never includes rendered template content.
- `secrets.set(key, value)` → `{ok: true, created: bool}` — no prepare step. Requires unlocked store; returns `secret_store_locked` if locked. If the key already exists, the old value is overwritten and `created` is `false`. The old value is not returned in the response.
- `secrets.delete(key)` → `{ok: true}` — no prepare step. Requires unlocked store; returns `secret_store_locked` if locked, `not_found` if the key does not exist.

### Confirmation tokens

`prepare` calls register a `Job` in an in-memory registry keyed by a 16-byte random token, storing the resolved parameters and a creation timestamp. `execute` looks up the token, removes it on first use (one-shot), and runs. Tokens expire 120 seconds after creation. Expired or unknown tokens return `invalid_confirmation_token`.

`execute_*` takes only the token — it never re-takes parameters, so there is nothing to tamper with between `prepare` and `execute`.

The job registry is in-memory only. If the TUI restarts between `prepare` and `execute`, the token is gone and the LLM must call `prepare_*` again — by design.

### Concurrency

The control server uses asyncio. Multiple MCP clients may connect simultaneously; each handler is an independent coroutine. Existing services (`SecretStore`, `SSHConnectionPool`, etc.) are already serialized through the event loop. Long-running calls (`deploy.execute`, `sync.execute`) hold their socket connection open for the full duration.

## MCP tool surface

`shipyard mcp` registers the following tools with the MCP host. Each is a thin map onto one control-plane RPC; the MCP layer handles input validation, response shaping, and human-readable error messages.

**Naming convention:** control-plane RPC methods are dotted (`apps.list`, `deploy.prepare`); MCP tools are snake_case verb-noun (`list_applications`, `prepare_deploy`). The two surfaces map 1:1.

**Output size cap:** No tool returns more than 64 KB of text. Outputs that would exceed this (deploy logs from long `rerun.sh` runs, log tails) are truncated to the last 64 KB; the response includes `truncated: true`, `bytes_dropped: N`, and a hint about lowering `lines` / using a smaller window. Truncation is on the trailing end for log tails (most recent kept) and on the leading end for deploy output (last lines kept, since failures usually surface at the end).

### Read tools

| Tool | Args | Returns |
|------|------|---------|
| `list_applications` | — | Apps with envs, deployed versions, latest GitHub version |
| `get_application` | `app_id` | App detail incl. container statuses per env |
| `refresh_status` | — | Re-runs container cache fetch, returns updated cache summary |
| `list_servers` | — | Servers with hostname/user/port/description |
| `get_server` | `server_id` | Server config + reachability + all containers |
| `list_containers` | `server_id` | Containers from server cache |
| `tail_container_logs` | `server_id`, `container`, `lines?` (default 200, max 2000) | Finite log snapshot |
| `list_github_versions` | `app_id`, `limit?` (default 20, max 100) | Releases/tags |
| `list_secret_keys` | — | `[string]` or `secret_store_locked` error |
| `get_secret_value` | `key` | `{value}` or `secret_store_locked` / `not_found` |
| `secret_store_status` | — | `{unlocked: bool}` |
| `list_templates` | `app_id`, `env_id` | `.j2` files in `local-path` + per-file variable resolution status |
| `inspect_template` | `app_id`, `env_id`, `path` | Per-line key/value/secret-linkage table |

### Write tools

| Tool | Args | Returns |
|------|------|---------|
| `prepare_deploy` | `app_id`, `env_id`, `version` | `{confirmation_token, summary}` |
| `execute_deploy` | `confirmation_token` | `{success, exit_code, output}` (blocks until rerun.sh exits) |
| `prepare_sync` | `app_id`, `env_id` | `{confirmation_token, summary, planned_uploads, template_files}` |
| `execute_sync` | `confirmation_token` | `{success, transferred, skipped}` |
| `set_secret` | `key`, `value` | `{ok: true}` |
| `delete_secret` | `key` | `{ok: true}` |

### Tool descriptions

Each tool's description (registered with the MCP host) states:
- What the tool does.
- Its user-visible side effect (e.g. deploys "execute `./rerun.sh <version>` on a remote server, affecting running containers").
- Prerequisites (unlocked store for secret-reveal, valid token for `execute_*`).
- For destructive tools: a directive that the LLM must call the matching `prepare_*` first and surface the returned `summary` to the user before calling `execute_*`.

The hard guarantee against skipping prepare is the token mechanism: `execute_deploy` requires a token that only `prepare_deploy` issues.

### Intentionally NOT exposed

- `unlock_secrets(password)` — would push the master password into the chat transcript. Unlock only via the TUI.
- Live follow for deploys / logs (block-and-return for deploys, finite tail for logs).
- Arbitrary SSH command execution.
- Raw `shipyard.yaml` access or mutation.

## Security model

### Trust boundary

The TUI process is the trust root. It holds the unlocked secret store, the SSH connection pool, and the GitHub client. `shipyard mcp` runs with the same OS user but holds no key material; whatever the LLM can do is bounded by the control-plane surface.

### Threats and mitigations

| Threat | Mitigation |
|--------|------------|
| Other local user reads/connects to the control socket | Socket file `chmod 0600`, owner-only. Token file `chmod 0600`, regenerated each TUI start. Path under `~/.config/shipyard/`. |
| Stolen socket path used after TUI dies | TUI unlinks socket on shutdown (`finally` in `app.on_unmount`). MCP receives ECONNREFUSED → `shipyard_not_running`. Token file is removed too. |
| MCP-side process compromise leaks secret store | MCP holds no key material. Reading a secret requires calling the control plane; the TUI owns the Fernet key. If locked, all secret tools return `secret_store_locked`. |
| LLM tricked into deploying prod | `execute_deploy` requires a token from `prepare_deploy`. Tokens are single-use, expire in 120 s. `prepare_deploy` response includes a structured `summary` (server, version, container list, current versions) that the tool description instructs the LLM to surface. MCP host tool-use approval is a second line of defense. |
| LLM exfiltrates secrets via tool output | Secret values only flow through `get_secret_value` (explicitly requested). Sync output reports only file paths (`transferred`/`skipped`), never rendered template content. `inspect_template` never returns resolved values for LINKED entries. |
| LLM exfiltrates secrets via deploy/sync streams | `execute_deploy` output is `rerun.sh` stdout/stderr — the same content the user already trusts to display in the TUI. `execute_sync` output is filenames only. |
| Master password in logs / chat transcript | No MCP tool accepts the master password. TUI is the sole unlock entry point. |
| Arbitrary remote command execution | Closed tool surface; no `ssh.exec` tool. |
| Replay of a confirmation token after action ran | Token removed from registry on first `execute_*`; second use returns `invalid_confirmation_token`. |
| Tampering with parameters between `prepare` and `execute` | Token maps to resolved parameters server-side. `execute_*` takes only the token. |
| Audit / "who did what" | When MCP is enabled, every control-plane RPC is appended to `~/.config/shipyard/audit.log` with timestamp, method, parameter summary (no secret values), result code, and — where the OS exposes it (Linux `SO_PEERCRED`, macOS `LOCAL_PEEREUID`/`LOCAL_PEERPID`) — peer PID/UID. File `chmod 0600`. Rotated when it exceeds 5 MB, keeping up to 5 generations (`audit.log.1` … `audit.log.5`). TUI viewer for this log is post-MVP. |
| Concurrent MCP + TUI mutations of secrets | `SecretStore` operations serialized through the asyncio event loop. Last-write-wins on the file; both surfaces share the in-memory dict. |

### Explicit non-goals

See top-level Non-goals. Remote access and an attacker-with-shell threat model are out of scope; both would require separate, dedicated work.

## Configuration

New section in `shipyard.yaml`:

```yaml
global:
  mcp:
    enabled: false                                       # default off; opt-in
    socket_path: "~/.config/shipyard/control.sock"
    audit_log_path: "~/.config/shipyard/audit.log"
```

Pydantic model in `src/shipyard/config/schema.py`:

```python
class MCPSettings(BaseModel):
    enabled: bool = False
    socket_path: str = "~/.config/shipyard/control.sock"
    audit_log_path: str = "~/.config/shipyard/audit.log"

class GlobalSettings(BaseModel):
    ssh: SSHSettings = SSHSettings()
    github: GitHubSettings = GitHubSettings()
    mcp: MCPSettings = MCPSettings()
```

When `enabled` is true, the TUI logs `MCP control server listening at <path>` once on startup. When false, no socket is opened and no audit log is written.

## Error handling

### `shipyard mcp` ↔ TUI failures

- No socket → every tool returns: `"Shipyard is not running. Start the TUI with shipyard --config <path> first."` Process exit code remains 0; the failure is communicated via MCP `isError: true` tool results.
- Mid-call socket disconnect (TUI quit during a long `execute_deploy`) → tool returns `"Connection to Shipyard lost during execution. The deploy may have partially completed — check the target server."` plus any partial output captured so far.
- Token handshake mismatch → MCP retries reading `control.token` once (in case TUI just restarted); on second mismatch, returns `"Shipyard restarted — reconnect by restarting the MCP client."`

### Per-tool errors

Each tool catches the JSON-RPC error codes above and maps them to MCP tool-result errors with short, user-readable messages. Tools never raise; all failures become structured results.

### Deploy / sync failures

- Non-zero `rerun.sh` exit → `execute_deploy` returns `{success: false, exit_code, output}`. Not an MCP-level error.
- Sync failure (missing template variable, etc.) → `{success: false, error, partial_results}`. Not an MCP-level error.

### Input validation

Pydantic models validate every tool's args. Bad inputs return `validation_error` with the offending field path, so the LLM can self-correct on the next call.

## Testing

Test files mirror the module layout (`tests/control/`, `tests/mcp/`). All async tests use `pytest-asyncio` (already configured).

### Unit

- `control/methods.py` — each RPC method tested against fake services (mocked `SSHConnectionPool`, `Deployer`, `FileSyncer`, `SecretStore`). Asserts wiring and response shape, not service internals.
- `control/jobs.py` — token registry: creation, single-use consumption, 120 s expiry, unknown-token error, concurrent prepare/execute.
- `mcp/server.py` — each MCP tool tested by stubbing the JSON-RPC client and asserting input validation + response shape.

### Integration

- `tests/integration/test_control_socket.py` — real `control.server` on a tmpdir socket, real `mcp.client.JsonRpcClient`. Validates framing, token handshake (success and rejection), error envelopes, concurrent connections.
- `tests/integration/test_mcp_end_to_end.py` — launch `python -m shipyard.mcp` as a subprocess against a TUI control server backed by fakes; speak the MCP protocol over stdio; assert tool round-trips. Uses the `mcp` SDK's test harness where available, otherwise hand-rolled JSON-RPC over stdio.

### Security regression tests

The following must not regress:

- Socket file is created with mode 0600; server fails to start if it cannot set those permissions.
- Token file is regenerated on each TUI start (different bytes than prior run).
- `get_secret_value` returns `secret_store_locked` when the store is locked.
- `inspect_template` never includes the resolved value for LINKED entries.
- `execute_sync` result payload does not contain rendered template body — only paths.
- `execute_deploy` with an expired / unknown / already-consumed token returns `invalid_confirmation_token`.
- No tool definition accepts a field named `password`, `master_password`, or similar.

## Rollout

1. Land the control plane + MCP modules behind `global.mcp.enabled: false`.
2. Document in `doc/mcp.md`, link from `README.md`, update `doc/architecture.md` and `doc/configuration.md` per the project's docs-up-to-date rule.
3. Validate end-to-end against Claude Code as the reference MCP client (enable in `shipyard.yaml`, configure the client, exercise each tool category at least once) before announcing the feature.

### Documentation deliverables

- `doc/architecture.md` — new section "MCP Server" describing the control plane and MCP layer.
- `doc/configuration.md` — new `global.mcp` section.
- `doc/screens.md` — note that the TUI must be running for MCP to work.
- `doc/mcp.md` (new) — user-facing guide: enabling MCP, configuring Claude Code/Desktop, full tool reference, security model summary.
- `README.md` — one-paragraph mention with a link to `doc/mcp.md`.

## Open questions

None blocking. Items deferred to follow-ups:

- A `shipyard ctl` CLI on top of the control socket.
- TUI viewer for the audit log.
- HTTP transport with bearer auth (for team-shared deployments).
- Live streaming via MCP `notifications/progress`.
