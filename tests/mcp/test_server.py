"""Tests for the MCP server dispatcher (mapping MCP tool calls to RPC calls)."""

from __future__ import annotations

import json

import pytest

from shipyard.mcp.client import JsonRpcRemoteError, ShipyardNotRunningError
from shipyard.mcp.server import build_server, handle_call_tool


class FakeClient:
    def __init__(self, responses: dict[str, object] | None = None, raises: Exception | None = None) -> None:
        self.responses = responses or {}
        self.raises = raises
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict) -> object:
        self.calls.append((method, params))
        if self.raises is not None:
            raise self.raises
        return self.responses.get(method, {})


async def test_list_applications_round_trips() -> None:
    client = FakeClient(responses={"apps.list": [{"id": "frontend"}]})
    result = await handle_call_tool(client, "list_applications", {})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload == [{"id": "frontend"}]
    assert client.calls == [("apps.list", {})]


async def test_get_application_passes_args() -> None:
    client = FakeClient(responses={"apps.get": {"id": "frontend"}})
    await handle_call_tool(client, "get_application", {"app_id": "frontend"})
    assert client.calls == [("apps.get", {"app_id": "frontend"})]


async def test_unknown_tool_returns_is_error() -> None:
    client = FakeClient()
    result = await handle_call_tool(client, "no_such_tool", {})
    assert result[0].text.lower().startswith("error:")
    assert "unknown tool" in result[0].text.lower()


async def test_remote_error_becomes_error_result() -> None:
    client = FakeClient(raises=JsonRpcRemoteError(code=-32005, message="not found"))
    result = await handle_call_tool(client, "get_application", {"app_id": "ghost"})
    assert result[0].text.lower().startswith("error:")
    assert "not found" in result[0].text


async def test_shipyard_not_running_becomes_error_result() -> None:
    client = FakeClient(raises=ShipyardNotRunningError("nope"))
    result = await handle_call_tool(client, "list_applications", {})
    assert result[0].text.lower().startswith("error:")
    assert "shipyard is not running" in result[0].text.lower()


async def test_secret_store_locked_friendly_message() -> None:
    client = FakeClient(raises=JsonRpcRemoteError(code=-32002, message="Secret store is locked"))
    result = await handle_call_tool(client, "list_secret_keys", {})
    assert result[0].text.lower().startswith("error:")
    assert "locked" in result[0].text.lower()


def test_build_server_registers_all_tools(tmp_path) -> None:
    from shipyard.mcp.tools import TOOL_SPECS

    server, _ = build_server(socket_path=tmp_path / "x.sock", token_path=tmp_path / "x.token")
    # The Server's internal tool registry is implementation-defined; we use the same
    # spec list and rely on the integration test for the protocol level. Here we just
    # ensure build_server returns successfully and the spec list is non-empty.
    assert server is not None
    assert len(TOOL_SPECS) >= 19
