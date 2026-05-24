"""Tests for the static MCP tool registry."""

from __future__ import annotations

from shipyard.mcp.tools import TOOL_SPECS, ToolSpec


def test_all_specs_have_required_fields() -> None:
    for spec in TOOL_SPECS:
        assert isinstance(spec, ToolSpec)
        assert spec.name
        assert spec.description
        assert isinstance(spec.input_schema, dict)
        assert spec.input_schema.get("type") == "object"
        assert spec.rpc_method


def test_tool_names_are_unique() -> None:
    names = [s.name for s in TOOL_SPECS]
    assert len(names) == len(set(names))


def test_destructive_tools_have_confirmation_directive() -> None:
    destructive = {"execute_deploy", "execute_sync"}
    for spec in TOOL_SPECS:
        if spec.name in destructive:
            assert "prepare" in spec.description.lower()


def test_no_tool_accepts_master_password_field() -> None:
    forbidden = {"password", "master_password", "passphrase"}
    for spec in TOOL_SPECS:
        props = set(spec.input_schema.get("properties", {}).keys())
        assert not (props & forbidden), f"Tool {spec.name} accepts a forbidden password field"


def test_expected_tools_are_present() -> None:
    names = {s.name for s in TOOL_SPECS}
    expected = {
        "list_applications", "get_application", "refresh_status",
        "list_servers", "get_server", "list_containers",
        "tail_container_logs", "list_github_versions",
        "list_secret_keys", "get_secret_value", "secret_store_status",
        "list_templates", "inspect_template",
        "prepare_deploy", "execute_deploy",
        "prepare_sync", "execute_sync",
        "set_secret", "delete_secret",
    }
    assert expected.issubset(names)
