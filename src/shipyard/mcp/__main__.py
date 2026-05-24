"""`python -m shipyard.mcp` — stdio MCP server.

Loads the same Shipyard YAML config as the TUI to discover where the control socket lives,
then runs the MCP server over stdio. The actual work is forwarded to the running TUI
process via the Unix socket.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from mcp.server.stdio import stdio_server

from shipyard.config.manager import ConfigError, load_config
from shipyard.mcp.server import build_server


_LOG = logging.getLogger("shipyard.mcp")


def main(config_path: str | None = None) -> None:
    """Entry point used by `shipyard mcp`."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"shipyard mcp: config error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not config.global_.mcp.enabled:
        print(
            "shipyard mcp: MCP is disabled in your config. Set `global.mcp.enabled: true` "
            "in shipyard.yaml and restart the TUI.",
            file=sys.stderr,
        )
        sys.exit(3)

    socket_path = Path(config.global_.mcp.socket_path).expanduser()
    token_path = socket_path.with_name("control.token")

    server, _client = build_server(socket_path=socket_path, token_path=token_path)

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
