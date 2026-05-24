"""Tests for ControlMethods — thin RPC wrappers over services."""

from __future__ import annotations

import pytest

from shipyard.control.methods import ControlMethods, ControlError, ErrorCode


@pytest.fixture
def methods(control_deps) -> ControlMethods:
    return ControlMethods(**control_deps)


async def test_apps_list_returns_all_apps(methods) -> None:
    result = await methods.apps_list()
    assert isinstance(result, list)
    assert {a["id"] for a in result} == {"frontend"}
    frontend = result[0]
    assert frontend["name"] == "Frontend App"
    assert frontend["github"]["repo"] == "myorg/frontend"
    env_ids = {e["id"] for e in frontend["environments"]}
    assert env_ids == {"prd", "staging"}


async def test_apps_get_returns_full_detail(methods) -> None:
    result = await methods.apps_get(app_id="frontend")
    assert result["id"] == "frontend"
    envs = {e["id"]: e for e in result["environments"]}
    assert envs["prd"]["server"] == "prod-01"
    assert envs["prd"]["path"] == "/opt/apps/frontend"
    containers = {c["name"]: c for c in envs["prd"]["containers"]}
    assert containers["frontend-prd-web"]["status"] == "running"
    assert containers["frontend-prd-web"]["image"] == "myorg/frontend:v3.2"


async def test_apps_get_unknown_app_raises_not_found(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.apps_get(app_id="does-not-exist")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_apps_refresh_status_calls_refresher(monkeypatch, methods) -> None:
    called = []

    async def fake_refresh() -> None:
        called.append(True)

    methods._refresh_status_callback = fake_refresh
    result = await methods.apps_refresh_status()
    assert called == [True]
    assert result == {"ok": True}


async def test_servers_list_returns_all(methods) -> None:
    result = await methods.servers_list()
    assert {s["id"] for s in result} == {"prod-01", "staging-01"}
    prod = next(s for s in result if s["id"] == "prod-01")
    assert prod["hostname"] == "10.0.1.10"
    assert prod["port"] == 22
    assert prod["user"] == "deploy"


async def test_servers_get_includes_containers_and_reachability(methods) -> None:
    result = await methods.servers_get(server_id="prod-01")
    assert result["id"] == "prod-01"
    assert result["reachable"] is True
    names = {c["name"] for c in result["containers"]}
    assert "frontend-prd-web" in names


async def test_servers_get_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.servers_get(server_id="nope")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_containers_list_returns_cached_entries(methods) -> None:
    result = await methods.containers_list(server_id="prod-01")
    assert len(result) == 2
    assert {c["name"] for c in result} == {"frontend-prd-web", "frontend-prd-nginx"}


async def test_containers_list_unknown_server_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.containers_list(server_id="ghost")
    assert exc_info.value.code == ErrorCode.NOT_FOUND
