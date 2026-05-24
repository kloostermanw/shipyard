"""Tests for JSON-RPC 2.0 framing helpers."""

from __future__ import annotations

import json

import pytest

from shipyard.control.protocol import (
    JsonRpcError,
    encode_error,
    encode_result,
    parse_request,
)


def test_parse_valid_request() -> None:
    raw = '{"jsonrpc":"2.0","id":1,"method":"apps.list","params":{}}'
    req = parse_request(raw)
    assert req.id == 1
    assert req.method == "apps.list"
    assert req.params == {}


def test_parse_request_without_params() -> None:
    raw = '{"jsonrpc":"2.0","id":7,"method":"apps.list"}'
    req = parse_request(raw)
    assert req.params == {}


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request("not json")
    assert exc_info.value.code == -32700  # Parse error


def test_parse_wrong_jsonrpc_version() -> None:
    raw = '{"jsonrpc":"1.0","id":1,"method":"x"}'
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request(raw)
    assert exc_info.value.code == -32600  # Invalid request


def test_parse_missing_method() -> None:
    raw = '{"jsonrpc":"2.0","id":1}'
    with pytest.raises(JsonRpcError) as exc_info:
        parse_request(raw)
    assert exc_info.value.code == -32600


def test_encode_result_round_trip() -> None:
    payload = encode_result(request_id=42, result={"ok": True})
    parsed = json.loads(payload)
    assert parsed == {"jsonrpc": "2.0", "id": 42, "result": {"ok": True}}


def test_encode_error_round_trip() -> None:
    payload = encode_error(request_id=42, code=-32005, message="not found")
    parsed = json.loads(payload)
    assert parsed == {
        "jsonrpc": "2.0",
        "id": 42,
        "error": {"code": -32005, "message": "not found"},
    }


def test_encode_error_includes_data_when_provided() -> None:
    payload = encode_error(
        request_id=1, code=-32006, message="bad", data={"field": "version"}
    )
    parsed = json.loads(payload)
    assert parsed["error"]["data"] == {"field": "version"}
