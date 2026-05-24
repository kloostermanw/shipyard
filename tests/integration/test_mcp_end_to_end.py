"""End-to-end test: real shipyard.mcp.server against a real ControlServer.

We don't spin up an actual subprocess here — we exercise the Server in-process by
calling the registered handlers directly. The handlers go through the real
JsonRpcClient and a real Unix socket, so this catches the full chain.
"""

from __future__ import annotations

import json

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
from shipyard.mcp.server import handle_call_tool
from shipyard.mcp.client import JsonRpcClient


def _is_error(text_content) -> bool:
    return text_content.text.lower().startswith("error:")


@pytest.fixture
async def stack(short_tmp, control_deps):
    socket_path = short_tmp / "control.sock"
    token_path = short_tmp / "control.token"
    audit = AuditLog(path=short_tmp / "audit.log")
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit,
    )
    await server.start()
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
        await server.stop()


async def test_list_applications_via_mcp_handler(stack) -> None:
    client = stack
    result = await handle_call_tool(client, "list_applications", {})
    assert len(result) == 1
    assert not _is_error(result[0])
    payload = json.loads(result[0].text)
    assert any(a["id"] == "frontend" for a in payload)


async def test_get_secret_value_unlocked(stack) -> None:
    client = stack
    result = await handle_call_tool(client, "get_secret_value", {"key": "DB_PASSWORD"})
    assert not _is_error(result[0])
    payload = json.loads(result[0].text)
    assert payload == {"value": "supersecret"}


async def test_full_deploy_flow_via_mcp(stack) -> None:
    client = stack
    prep_result = await handle_call_tool(
        client,
        "prepare_deploy",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    assert not _is_error(prep_result[0])
    prep_payload = json.loads(prep_result[0].text)
    token = prep_payload["token"]

    exec_result = await handle_call_tool(
        client, "execute_deploy", {"confirmation_token": token}
    )
    assert not _is_error(exec_result[0])
    exec_payload = json.loads(exec_result[0].text)
    assert exec_payload["success"] is True


async def test_invalid_token_returns_user_friendly_error(stack) -> None:
    client = stack
    result = await handle_call_tool(
        client, "execute_deploy", {"confirmation_token": "bogus"}
    )
    assert _is_error(result[0])
    body = result[0].text.lower()
    assert "expired" in body or "invalid" in body


def test_no_tool_definition_accepts_password_field() -> None:
    """Security regression: no tool definition should accept a password-like field."""
    from shipyard.mcp.tools import TOOL_SPECS

    for spec in TOOL_SPECS:
        for prop in spec.input_schema.get("properties", {}).keys():
            assert prop not in {"password", "master_password", "passphrase"}
