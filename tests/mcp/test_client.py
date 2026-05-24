"""Tests for the MCP-side JSON-RPC client (Unix socket)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from shipyard.mcp.client import (
    JsonRpcClient,
    JsonRpcRemoteError,
    ShipyardNotRunningError,
)


async def _start_fake_server(
    socket_path: Path,
    token: str,
    handler,
) -> asyncio.AbstractServer:
    async def serve(reader, writer):
        try:
            hs_line = await reader.readline()
            if not hs_line:
                writer.close()
                return
            hs = json.loads(hs_line.decode().rstrip("\n"))
            if hs.get("hello") != token:
                writer.close()
                return
            while True:
                line = await reader.readline()
                if not line:
                    return
                req = json.loads(line.decode().rstrip("\n"))
                response = handler(req)
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_unix_server(serve, path=str(socket_path))


async def test_client_round_trip(short_tmp) -> None:
    socket_path = short_tmp / "ctl.sock"
    token_path = short_tmp / "ctl.token"
    token = "test-token-1234567890123456"
    token_path.write_text(token)

    def handler(req):
        assert req["method"] == "apps.list"
        return {"jsonrpc": "2.0", "id": req["id"], "result": [{"id": "frontend"}]}

    server = await _start_fake_server(socket_path, token, handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            result = await client.call("apps.list", {})
        finally:
            await client.close()
        assert result == [{"id": "frontend"}]
    finally:
        server.close()
        await server.wait_closed()


async def test_client_remote_error(short_tmp) -> None:
    socket_path = short_tmp / "ctl.sock"
    token_path = short_tmp / "ctl.token"
    token = "token-aaaaaaaaaaaaaaaaaaaaaa"
    token_path.write_text(token)

    def handler(req):
        return {
            "jsonrpc": "2.0",
            "id": req["id"],
            "error": {"code": -32005, "message": "not found"},
        }

    server = await _start_fake_server(socket_path, token, handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            with pytest.raises(JsonRpcRemoteError) as exc_info:
                await client.call("apps.get", {"app_id": "ghost"})
        finally:
            await client.close()
        assert exc_info.value.code == -32005
        assert exc_info.value.message == "not found"
    finally:
        server.close()
        await server.wait_closed()


async def test_client_shipyard_not_running(short_tmp) -> None:
    socket_path = short_tmp / "missing.sock"
    token_path = short_tmp / "missing.token"
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    with pytest.raises(ShipyardNotRunningError):
        await client.connect()


async def test_client_handshake_rejected(short_tmp) -> None:
    socket_path = short_tmp / "ctl.sock"
    token_path = short_tmp / "ctl.token"
    token_path.write_text("wrong-token-xxxxxxxxxxxxxxxxxxxxxxxx")

    def handler(req):
        return {"jsonrpc": "2.0", "id": req["id"], "result": "should-not-get-here"}

    server = await _start_fake_server(socket_path, "real-token-yyyyyyyyyyyyyyyyyyyyyyy", handler)
    try:
        client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
        await client.connect()
        try:
            # Server will close the connection after rejecting handshake → next call fails
            with pytest.raises(ShipyardNotRunningError):
                await client.call("apps.list", {})
        finally:
            await client.close()
    finally:
        server.close()
        await server.wait_closed()
