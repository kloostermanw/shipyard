"""Tests for the in-TUI JSON-RPC control server."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer


@pytest.fixture
def short_tmp(tmp_path) -> Path:
    """Return a tmp dir with a path short enough for AF_UNIX (104-char limit on macOS)."""
    p = str(tmp_path)
    if len(p) + len("/control.sock") > 100:
        # Fall back to a short path under /tmp
        d = Path(tempfile.mkdtemp(prefix="sy_", dir="/tmp"))
        return d
    return tmp_path


@pytest.fixture
def socket_path(short_tmp) -> Path:
    return short_tmp / "control.sock"


@pytest.fixture
def token_path(short_tmp) -> Path:
    return short_tmp / "control.token"


@pytest.fixture
def audit_log(tmp_path) -> AuditLog:
    return AuditLog(path=tmp_path / "audit.log")


@pytest.fixture
async def running_server(socket_path, token_path, audit_log, control_deps):
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def _send_and_recv(socket_path: Path, frames: list[str]) -> list[str]:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        for frame in frames:
            writer.write((frame + "\n").encode("utf-8"))
            await writer.drain()
        responses: list[str] = []
        for _ in frames[1:]:  # one response per non-handshake frame
            line = await reader.readline()
            if not line:
                break
            responses.append(line.decode("utf-8").rstrip("\n"))
        return responses
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def test_socket_created_with_mode_0600(running_server, socket_path) -> None:
    assert socket_path.exists()
    mode = socket_path.stat().st_mode & 0o777
    assert mode == 0o600


async def test_token_file_created_with_mode_0600(running_server, token_path) -> None:
    assert token_path.exists()
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600
    token = token_path.read_text().strip()
    assert len(token) >= 22


async def test_apps_list_round_trip(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "apps.list", "params": {}})
    responses = await _send_and_recv(socket_path, [handshake, request])
    assert len(responses) == 1
    parsed = json.loads(responses[0])
    assert parsed["id"] == 1
    assert any(a["id"] == "frontend" for a in parsed["result"])


async def test_wrong_token_closes_connection(running_server, socket_path) -> None:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write((json.dumps({"hello": "wrong-token"}) + "\n").encode())
        await writer.drain()
        # Expect EOF
        data = await asyncio.wait_for(reader.read(1024), timeout=2)
        assert data == b""
    finally:
        writer.close()


async def test_unknown_method_returns_error(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "no.such.method", "params": {}})
    responses = await _send_and_recv(socket_path, [handshake, request])
    parsed = json.loads(responses[0])
    assert parsed["error"]["code"] == -32601  # Method not found


async def test_validation_error_on_bad_params(running_server, socket_path, token_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "apps.get", "params": {"app_id": "ghost"}
    })
    responses = await _send_and_recv(socket_path, [handshake, request])
    parsed = json.loads(responses[0])
    assert parsed["error"]["code"] == -32005  # NOT_FOUND


async def test_audit_log_records_calls(running_server, socket_path, token_path, tmp_path) -> None:
    token = token_path.read_text().strip()
    handshake = json.dumps({"hello": token})
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "apps.list", "params": {}})
    await _send_and_recv(socket_path, [handshake, request])

    audit_lines = (tmp_path / "audit.log").read_text().splitlines()
    assert len(audit_lines) >= 1
    rec = json.loads(audit_lines[-1])
    assert rec["method"] == "apps.list"
    assert rec["result_code"] == 0


async def test_server_unlinks_socket_on_stop(socket_path, token_path, audit_log, control_deps) -> None:
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    assert socket_path.exists()
    await server.stop()
    assert not socket_path.exists()
    assert not token_path.exists()


async def test_stale_socket_is_unlinked_before_bind(socket_path, token_path, audit_log, control_deps) -> None:
    socket_path.write_text("leftover")  # not a real socket; should be removed
    methods = ControlMethods(**control_deps)
    server = ControlServer(
        methods=methods,
        socket_path=socket_path,
        token_path=token_path,
        audit_log=audit_log,
    )
    await server.start()
    try:
        # After start, it's a real socket file (s_type, not the leftover text)
        assert socket_path.exists()
    finally:
        await server.stop()
