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


def _error(text: str) -> list[TextContent]:
    """Return an error result. Since mcp>=1.x TextContent has no is_error field,
    we prefix the message with 'ERROR: ' so callers can detect errors."""
    return [TextContent(type="text", text=f"ERROR: {text}")]


async def handle_call_tool(
    client: Any, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch one MCP tool call to a JSON-RPC method via `client`."""
    spec = get_spec(name)
    if spec is None:
        return _error(f"Unknown tool: {name}")

    # Translate parameter names for execute_* tools (MCP uses confirmation_token, RPC uses token).
    translated = dict(arguments)
    if name in {"execute_deploy", "execute_sync"} and "confirmation_token" in translated:
        translated["token"] = translated.pop("confirmation_token")

    try:
        result = await client.call(spec.rpc_method, translated)
    except ShipyardNotRunningError as exc:
        return _error(f"Shipyard is not running: {exc}")
    except JsonRpcRemoteError as exc:
        hint = _ERROR_HINTS.get(exc.code, "")
        body = exc.message if not hint else f"{hint}\n\n(Detail: {exc.message})"
        return _error(body)

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
        if client._writer is None:  # lazy-connect on first call
            try:
                await client.connect()
            except ShipyardNotRunningError as exc:
                return _error(f"Shipyard is not running: {exc}")
        return await handle_call_tool(client, name, arguments)

    return server, client
