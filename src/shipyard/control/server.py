"""In-TUI JSON-RPC control server over Unix domain socket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import struct
import sys
from pathlib import Path
from typing import Any

from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlError, ControlMethods, ErrorCode
from shipyard.control.protocol import (
    INVALID_REQUEST,
    JsonRpcError,
    METHOD_NOT_FOUND,
    encode_error,
    encode_result,
    parse_request,
)


_LOG = logging.getLogger(__name__)

# Map JSON-RPC method name → (ControlMethods coroutine attr name, allowed param keys)
# Allowed param keys keep dispatch strict so unexpected kwargs are rejected.
_METHODS: dict[str, tuple[str, set[str]]] = {
    "apps.list": ("apps_list", set()),
    "apps.get": ("apps_get", {"app_id"}),
    "apps.refresh_status": ("apps_refresh_status", set()),
    "servers.list": ("servers_list", set()),
    "servers.get": ("servers_get", {"server_id"}),
    "containers.list": ("containers_list", {"server_id"}),
    "logs.tail": ("logs_tail", {"server_id", "container", "lines"}),
    "github.versions": ("github_versions", {"app_id", "limit"}),
    "secrets.is_unlocked": ("secrets_is_unlocked", set()),
    "secrets.list_keys": ("secrets_list_keys", set()),
    "secrets.get": ("secrets_get", {"key"}),
    "secrets.set": ("secrets_set", {"key", "value"}),
    "secrets.delete": ("secrets_delete", {"key"}),
    "templates.list": ("templates_list", {"app_id", "env_id"}),
    "templates.inspect": ("templates_inspect", {"app_id", "env_id", "path"}),
    "deploy.prepare": ("deploy_prepare", {"app_id", "env_id", "version"}),
    "deploy.execute": ("deploy_execute", {"token"}),
    "sync.prepare": ("sync_prepare", {"app_id", "env_id"}),
    "sync.execute": ("sync_execute", {"token"}),
}

# Methods whose params_summary should NOT include sensitive fields in the audit log.
_PARAMS_REDACT_KEYS: set[str] = {"value", "password", "master_password"}


def _summarize_params(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in _PARAMS_REDACT_KEYS}


def _get_peer_creds(transport: asyncio.BaseTransport) -> dict[str, int] | None:
    sock = transport.get_extra_info("socket")
    if sock is None:
        return None
    try:
        if sys.platform.startswith("linux"):
            # SO_PEERCRED → struct { pid_t pid; uid_t uid; gid_t gid; }
            import socket as _socket
            data = sock.getsockopt(_socket.SOL_SOCKET, 17, struct.calcsize("3i"))  # SO_PEERCRED = 17
            pid, uid, _gid = struct.unpack("3i", data)
            return {"pid": pid, "uid": uid}
        if sys.platform == "darwin":
            import socket as _socket
            # LOCAL_PEEREUID = 2, LOCAL_PEERPID = 3, level = 0 (SOL_LOCAL)
            try:
                uid = sock.getsockopt(0, 2)
            except OSError:
                uid = -1
            try:
                pid = sock.getsockopt(0, 3)
            except OSError:
                pid = -1
            return {"pid": pid, "uid": uid}
    except Exception:  # pragma: no cover (kernel idiosyncrasies)
        return None
    return None


class ControlServer:
    """Asyncio Unix-socket JSON-RPC server inside the TUI."""

    def __init__(
        self,
        methods: ControlMethods,
        socket_path: Path,
        token_path: Path,
        audit_log: AuditLog,
    ) -> None:
        self._methods = methods
        self._socket_path = Path(socket_path).expanduser()
        self._token_path = Path(token_path).expanduser()
        self._audit = audit_log
        self._server: asyncio.AbstractServer | None = None
        self._token: str = ""

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove stale socket / token files from a prior crashed run.
        for p in (self._socket_path, self._token_path):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _LOG.warning("Could not remove stale %s: %s", p, exc)

        # Write the token file BEFORE the socket is reachable.
        self._token = secrets.token_urlsafe(32)
        self._token_path.write_text(self._token)
        os.chmod(self._token_path, 0o600)

        self._server = await asyncio.start_unix_server(
            self._handle_connection, path=str(self._socket_path)
        )
        os.chmod(self._socket_path, 0o600)
        _LOG.info("Control server listening at %s", self._socket_path)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        for p in (self._socket_path, self._token_path):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _LOG.warning("Could not remove %s on shutdown: %s", p, exc)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = _get_peer_creds(writer.transport)
        try:
            # Step 1: token handshake
            line = await reader.readline()
            if not line:
                return
            try:
                handshake = json.loads(line.decode("utf-8").rstrip("\n"))
            except json.JSONDecodeError:
                self._audit.write("handshake.fail", {"reason": "invalid_json"}, 1, peer=peer)
                return
            if not isinstance(handshake, dict) or handshake.get("hello") != self._token:
                self._audit.write("handshake.fail", {"reason": "bad_token"}, 1, peer=peer)
                return

            # Step 2: request loop
            while True:
                line = await reader.readline()
                if not line:
                    return
                raw = line.decode("utf-8").rstrip("\n")
                if not raw:
                    continue
                response = await self._handle_one(raw, peer)
                writer.write((response + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            return
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_one(self, raw: str, peer: dict[str, int] | None) -> str:
        try:
            req = parse_request(raw)
        except JsonRpcError as exc:
            self._audit.write("parse.error", {}, exc.code, peer=peer)
            return encode_error(None, exc.code, exc.message)

        spec = _METHODS.get(req.method)
        if spec is None:
            self._audit.write(req.method, _summarize_params(req.method, req.params), METHOD_NOT_FOUND, peer=peer)
            return encode_error(req.id, METHOD_NOT_FOUND, f"Unknown method: {req.method}")

        attr_name, allowed = spec
        extra = set(req.params) - allowed
        if extra:
            self._audit.write(req.method, _summarize_params(req.method, req.params), INVALID_REQUEST, peer=peer)
            return encode_error(
                req.id,
                INVALID_REQUEST,
                f"Unexpected parameter(s): {sorted(extra)}",
            )

        handler = getattr(self._methods, attr_name)
        try:
            result = await handler(**req.params)
        except ControlError as exc:
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(exc.code), peer=peer)
            return encode_error(req.id, int(exc.code), exc.message)
        except TypeError as exc:
            # Missing required kwargs from params
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(ErrorCode.VALIDATION_ERROR), peer=peer)
            return encode_error(
                req.id, int(ErrorCode.VALIDATION_ERROR), f"Invalid parameters: {exc}"
            )
        except Exception as exc:
            _LOG.exception("Internal error handling %s", req.method)
            self._audit.write(req.method, _summarize_params(req.method, req.params), int(ErrorCode.INTERNAL_ERROR), peer=peer)
            return encode_error(req.id, int(ErrorCode.INTERNAL_ERROR), "Internal error")

        self._audit.write(req.method, _summarize_params(req.method, req.params), 0, peer=peer)
        return encode_result(req.id, result)
