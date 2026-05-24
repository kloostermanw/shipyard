"""Main Shipyard TUI application."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from textual.app import App

from shipyard.config.manager import ConfigError, load_config
from shipyard.config.schema import ShipyardConfig
from shipyard.control.audit import AuditLog
from shipyard.control.methods import ControlMethods
from shipyard.control.server import ControlServer
from shipyard.deploy.deployer import Deployer
from shipyard.github.client import GitHubClient
from shipyard.ssh.connection import SSHConnectionPool
from shipyard.secrets.store import SecretStore
from shipyard.sync.syncer import FileSyncer


class ShipyardApp(App):
    """Shipyard - Docker Deployment TUI."""

    TITLE = "Shipyard - Docker Deployment Manager"
    CSS_PATH = "styles/app.tcss"

    def __init__(self, config: ShipyardConfig) -> None:
        super().__init__()
        self.shipyard_config = config
        self.ssh_pool = SSHConnectionPool(config.global_, config.servers)
        self.github_client = GitHubClient(config.global_.github)
        self.deployer = Deployer(self.ssh_pool)
        self.secret_store = SecretStore()
        self.file_syncer = FileSyncer(self.ssh_pool, self.secret_store)
        self._control_server: ControlServer | None = None
        self.container_cache: dict[str, dict[str, list[dict[str, str]]]] = {}
        self.server_container_cache: dict[str, list[dict[str, str]]] = {}

    def on_mount(self) -> None:
        from shipyard.screens.dashboard import DashboardScreen

        self.push_screen(DashboardScreen())
        self.refresh_container_cache()
        if self.shipyard_config.global_.mcp.enabled:
            self.run_worker(self._start_control_server(), exclusive=True, group="control_server")

    async def _start_control_server(self) -> None:
        cfg = self.shipyard_config.global_.mcp
        socket_path = Path(cfg.socket_path).expanduser()
        token_path = socket_path.with_name("control.token")
        audit = AuditLog(path=Path(cfg.audit_log_path).expanduser())

        methods = ControlMethods(
            config=self.shipyard_config,
            ssh_pool=self.ssh_pool,
            deployer=self.deployer,
            syncer=self.file_syncer,
            github_client=self.github_client,
            executor=_AppRemoteExecutor(self.ssh_pool),
            secret_store=self.secret_store,
            container_cache=self.container_cache,
            server_container_cache=self.server_container_cache,
            refresh_status_callback=self._refresh_for_control,
        )
        self._control_server = ControlServer(
            methods=methods,
            socket_path=socket_path,
            token_path=token_path,
            audit_log=audit,
        )
        await self._control_server.start()

    async def _refresh_for_control(self) -> None:
        """Wait for an in-flight refresh to complete, then trigger one and wait."""
        await self._fetch_all_container_status()

    async def on_unmount(self) -> None:
        if self._control_server is not None:
            try:
                await self._control_server.stop()
            except Exception:
                pass
        await self.ssh_pool.close_all()
        await self.github_client.close()

    def refresh_container_cache(self) -> None:
        """Trigger a background refresh of all container statuses."""
        self.run_worker(
            self._fetch_all_container_status(), exclusive=True, group="container_cache"
        )

    def _update_fetch_bar(self, completed: int, total: int) -> None:
        """Push progress to the FetchStatusBar on the active screen."""
        from shipyard.widgets.fetch_status_bar import FetchStatusBar

        try:
            bar = self.screen.query_one(FetchStatusBar)
            bar.show_progress(completed, total)
        except Exception:
            pass

    async def _fetch_all_container_status(self) -> None:
        """Fetch container status for every server and derive per-app/env cache."""
        from shipyard.widgets.fetch_status_bar import FetchStatusBar

        config = self.shipyard_config
        server_cache: dict[str, list[dict[str, str]]] = {}
        total = len(config.servers)
        completed = 0

        self._update_fetch_bar(0, total)

        async def fetch_server(server_id: str) -> None:
            nonlocal completed
            try:
                conn = await self.ssh_pool.get_connection(server_id)
                result = await conn.run("docker ps -a --format json", timeout=15)
                stdout = result.stdout or ""
                containers: list[dict[str, str]] = []
                for line in stdout.strip().splitlines():
                    if not line:
                        continue
                    data = json.loads(line)
                    containers.append({
                        "name": data.get("Names", ""),
                        "status": data.get("State", "unknown"),
                        "image": data.get("Image", ""),
                        "uptime": data.get("Status", ""),
                    })
                server_cache[server_id] = containers
            except Exception:
                server_cache[server_id] = []
            finally:
                completed += 1
                self._update_fetch_bar(completed, total)

        await asyncio.gather(
            *(fetch_server(sid) for sid in config.servers)
        )

        # Derive per-app/env container cache from server-level data
        cache: dict[str, dict[str, list[dict[str, str]]]] = {}
        for app_id, app_config in config.applications.items():
            for env_id, env_config in app_config.environments.items():
                server_containers = server_cache.get(env_config.server, [])
                names_on_server = {c["name"] for c in server_containers}
                containers_data: list[dict[str, str]] = []
                for container_name in env_config.containers:
                    if container_name in names_on_server:
                        for c in server_containers:
                            if c["name"] == container_name:
                                containers_data.append(c)
                                break
                    else:
                        containers_data.append({
                            "name": container_name,
                            "status": "unknown",
                            "image": "",
                            "uptime": "",
                        })
                cache.setdefault(app_id, {})[env_id] = containers_data

        self.server_container_cache = server_cache
        self.container_cache = cache

        # Notify the active screen of cache update
        screen = self.screen
        if hasattr(screen, "on_container_cache_updated"):
            screen.on_container_cache_updated()

        # Start the hide timer on the status bar
        try:
            bar = screen.query_one(FetchStatusBar)
            bar.show_complete()
        except Exception:
            pass


class _AppRemoteExecutor:
    """Minimal adapter exposing docker_logs_tail for the control plane."""

    def __init__(self, ssh_pool: SSHConnectionPool) -> None:
        self._ssh_pool = ssh_pool

    async def docker_logs_tail(
        self, server_id: str, container: str, lines: int
    ) -> str:
        conn = await self._ssh_pool.get_connection(server_id)
        result = await conn.run(
            f"docker logs --tail {lines} {container} 2>&1", timeout=30
        )
        return result.stdout or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Shipyard - Docker Deployment TUI")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)

    subparsers = parser.add_subparsers(dest="command")
    mcp_parser = subparsers.add_parser(
        "mcp", help="Run the Shipyard MCP server over stdio (requires the TUI to be running)"
    )
    mcp_parser.add_argument("--config", "-c", help="Path to config file", default=None)

    args = parser.parse_args()

    if args.command == "mcp":
        from shipyard.mcp.__main__ import main as mcp_main
        mcp_main(config_path=args.config)
        return

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = ShipyardApp(config)
    app.run()
