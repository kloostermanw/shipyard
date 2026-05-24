"""End-to-end: real ControlServer + real JsonRpcClient over Unix sockets."""

from __future__ import annotations

from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
from shipyard.mcp.client import JsonRpcClient, JsonRpcRemoteError


@pytest.fixture
async def running(short_tmp, control_deps):
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
        yield client, server
    finally:
        await client.close()
        await server.stop()


async def test_full_method_listing(running) -> None:
    client, _ = running
    result = await client.call("apps.list", {})
    assert any(a["id"] == "frontend" for a in result)


async def test_deploy_prepare_execute_flow(running) -> None:
    client, _ = running
    prep = await client.call(
        "deploy.prepare",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    assert prep["summary"]["version"] == "v3.4.0"
    result = await client.call("deploy.execute", {"token": prep["token"]})
    assert result["success"] is True


async def test_replay_token_fails(running) -> None:
    client, _ = running
    prep = await client.call(
        "deploy.prepare",
        {"app_id": "frontend", "env_id": "prd", "version": "v3.4.0"},
    )
    await client.call("deploy.execute", {"token": prep["token"]})
    with pytest.raises(JsonRpcRemoteError) as exc_info:
        await client.call("deploy.execute", {"token": prep["token"]})
    assert exc_info.value.code == -32003


async def test_locked_store_returns_locked_error(short_tmp, control_deps, locked_secrets) -> None:
    socket_path = short_tmp / "ctl.sock"
    token_path = short_tmp / "ctl.token"
    audit = AuditLog(path=short_tmp / "audit.log")
    control_deps["secret_store"] = locked_secrets
    server = ControlServer(
        methods=ControlMethods(**control_deps),
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit,
    )
    await server.start()
    client = JsonRpcClient(socket_path=socket_path, token_path=token_path)
    await client.connect()
    try:
        with pytest.raises(JsonRpcRemoteError) as exc_info:
            await client.call("secrets.get", {"key": "anything"})
        assert exc_info.value.code == -32002
    finally:
        await client.close()
        await server.stop()
