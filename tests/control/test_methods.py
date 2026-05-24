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


async def test_logs_tail_returns_snapshot(methods, fake_executor) -> None:
    fake_executor.log_output[("prod-01", "frontend-prd-web")] = "line a\nline b\nline c\n"
    result = await methods.logs_tail(server_id="prod-01", container="frontend-prd-web", lines=100)
    assert result["output"] == "line a\nline b\nline c\n"
    assert result["truncated"] is False


async def test_logs_tail_truncates_oversized_output(methods, fake_executor) -> None:
    big = "x" * (70 * 1024)  # 70 KB
    fake_executor.log_output[("prod-01", "frontend-prd-web")] = big
    result = await methods.logs_tail(server_id="prod-01", container="frontend-prd-web", lines=2000)
    assert len(result["output"].encode()) <= 64 * 1024
    assert result["truncated"] is True
    assert result["bytes_dropped"] > 0


async def test_logs_tail_clamps_lines(methods, fake_executor) -> None:
    fake_executor.log_output[("prod-01", "x")] = "ok"
    result = await methods.logs_tail(server_id="prod-01", container="x", lines=99999)
    # lines arg has been clamped to 2000 (max); we don't observe directly but the
    # call must succeed.
    assert result["output"] == "ok"


async def test_logs_tail_unknown_server_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.logs_tail(server_id="ghost", container="x", lines=100)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_github_versions_returns_list(methods) -> None:
    result = await methods.github_versions(app_id="frontend", limit=10)
    assert [v["name"] for v in result] == ["v3.4.0", "v3.3.0"]


async def test_github_versions_unknown_app_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.github_versions(app_id="ghost", limit=10)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_secrets_is_unlocked_when_open(methods) -> None:
    result = await methods.secrets_is_unlocked()
    assert result == {"unlocked": True}


async def test_secrets_list_keys_returns_sorted(methods) -> None:
    result = await methods.secrets_list_keys()
    assert result == ["API_KEY", "DB_PASSWORD"]


async def test_secrets_get_returns_value(methods) -> None:
    result = await methods.secrets_get(key="DB_PASSWORD")
    assert result == {"value": "supersecret"}


async def test_secrets_get_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.secrets_get(key="MISSING")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_secrets_set_creates_new(methods) -> None:
    result = await methods.secrets_set(key="NEW_ONE", value="abc")
    assert result == {"ok": True, "created": True}
    assert (await methods.secrets_get(key="NEW_ONE")) == {"value": "abc"}


async def test_secrets_set_overwrites_existing(methods) -> None:
    result = await methods.secrets_set(key="DB_PASSWORD", value="newpw")
    assert result == {"ok": True, "created": False}
    assert (await methods.secrets_get(key="DB_PASSWORD")) == {"value": "newpw"}


async def test_secrets_delete_removes_key(methods) -> None:
    result = await methods.secrets_delete(key="DB_PASSWORD")
    assert result == {"ok": True}
    with pytest.raises(ControlError):
        await methods.secrets_get(key="DB_PASSWORD")


async def test_secrets_delete_unknown_raises(methods) -> None:
    with pytest.raises(ControlError) as exc_info:
        await methods.secrets_delete(key="MISSING")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


async def test_secret_ops_locked_store_raises(locked_secrets, control_deps) -> None:
    control_deps["secret_store"] = locked_secrets
    m = ControlMethods(**control_deps)
    assert (await m.secrets_is_unlocked()) == {"unlocked": False}
    for coro in (
        m.secrets_list_keys(),
        m.secrets_get(key="X"),
        m.secrets_set(key="X", value="1"),
        m.secrets_delete(key="X"),
    ):
        with pytest.raises(ControlError) as exc_info:
            await coro
        assert exc_info.value.code == ErrorCode.SECRET_STORE_LOCKED
