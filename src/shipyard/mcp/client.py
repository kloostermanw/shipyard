"""JSON-RPC client used by `shipyard mcp` to reach the in-TUI control server."""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ShipyardNotRunningError(Exception):
    """Raised when the control socket is unreachable (TUI not running / restarted)."""


@dataclass
class JsonRpcRemoteError(Exception):
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        return f"JSON-RPC error {self.code}: {self.message}"


class JsonRpcClient:
    """Connect to the TUI's Unix socket, perform handshake, send/receive requests."""

    def __init__(self, socket_path: Path, token_path: Path) -> None:
        self._socket_path = Path(socket_path).expanduser()
        self._token_path = Path(token_path).expanduser()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if not self._socket_path.exists():
            raise ShipyardNotRunningError(
                f"Shipyard control socket not found at {self._socket_path}. "
                f"Start the TUI with `shipyard --config <path>` first."
            )
        try:
            token = self._token_path.read_text().strip()
        except FileNotFoundError:
            raise ShipyardNotRunningError(
                "Control token file is missing — Shipyard is not running or is restarting."
            )
        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                str(self._socket_path)
            )
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise ShipyardNotRunningError(
                f"Cannot connect to Shipyard control socket: {exc}"
            )
        # Send handshake
        self._writer.write((json.dumps({"hello": token}) + "\n").encode("utf-8"))
        await self._writer.drain()

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        if self._writer is None or self._reader is None:
            raise ShipyardNotRunningError("Client is not connected")
        request_id = next(self._ids)
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        ) + "\n"

        async with self._lock:
            try:
                self._writer.write(payload.encode("utf-8"))
                await self._writer.drain()
                line = await self._reader.readline()
            except (ConnectionResetError, BrokenPipeError) as exc:
                raise ShipyardNotRunningError(
                    f"Connection to Shipyard lost: {exc}"
                )
            if not line:
                raise ShipyardNotRunningError(
                    "Shipyard closed the connection (TUI may have exited or token rejected)."
                )

        response = json.loads(line.decode("utf-8").rstrip("\n"))
        if "error" in response:
            err = response["error"]
            raise JsonRpcRemoteError(
                code=err.get("code", -32603),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )
        return response.get("result")

    async def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None
