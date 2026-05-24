"""JSON-RPC 2.0 framing helpers (newline-delimited)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass
class JsonRpcError(Exception):
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        return f"JSON-RPC error {self.code}: {self.message}"


@dataclass
class JsonRpcRequest:
    id: Any
    method: str
    params: dict[str, Any]


def parse_request(raw: str) -> JsonRpcRequest:
    """Parse a single JSON-RPC request frame. Raises JsonRpcError on protocol problems."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        raise JsonRpcError(INVALID_REQUEST, "Request must be a JSON object")
    if data.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, "Missing or unsupported jsonrpc version")
    method = data.get("method")
    if not isinstance(method, str):
        raise JsonRpcError(INVALID_REQUEST, "Missing or invalid method")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object")
    return JsonRpcRequest(id=data.get("id"), method=method, params=params)


def encode_result(request_id: Any, result: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def encode_error(
    request_id: Any, code: int, message: str, data: Any = None
) -> str:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "error": err})
