"""Main Shipyard TUI application."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from textual.app import App
from textual.message import Message

from shipyard.config.manager import ConfigError, load_config
from shipyard.config.schema import ShipyardConfig
from shipyard.deploy.deployer import Deployer
from shipyard.github.client import GitHubClient
from shipyard.ssh.connection import SSHConnectionPool


class ShipyardApp(App):
    """Shipyard - Docker Deployment TUI."""

    TITLE = "Shipyard - Docker Deployment Manager"
    CSS_PATH = "styles/app.tcss"

    class ContainerCacheUpdated(Message):
        """Posted when the shared container status cache has been refreshed."""

    def __init__(self, config: ShipyardConfig) -> None:
        super().__init__()
        self.shipyard_config = config
        self.ssh_pool = SSHConnectionPool(config.global_, config.servers)
        self.github_client = GitHubClient(config.global_.github)
        self.deployer = Deployer(self.ssh_pool)
        self.container_cache: dict[str, dict[str, list[dict[str, str]]]] = {}

    def on_mount(self) -> None:
        from shipyard.screens.dashboard import DashboardScreen

        self.push_screen(DashboardScreen())
        self.refresh_container_cache()

    async def on_unmount(self) -> None:
        await self.ssh_pool.close_all()
        await self.github_client.close()

    def refresh_container_cache(self) -> None:
        """Trigger a background refresh of all container statuses."""
        self.run_worker(
            self._fetch_all_container_status(), exclusive=True, group="container_cache"
        )

    async def _fetch_all_container_status(self) -> None:
        """Fetch container status for every app/env and populate the cache."""
        config = self.shipyard_config

        # Group work by server to minimise SSH connections
        # Each task is (app_id, env_id, server_id, container_names)
        tasks_by_server: dict[str, list[tuple[str, str, list[str]]]] = {}
        for app_id, app_config in config.applications.items():
            for env_id, env_config in app_config.environments.items():
                tasks_by_server.setdefault(env_config.server, []).append(
                    (app_id, env_id, env_config.containers)
                )

        cache: dict[str, dict[str, list[dict[str, str]]]] = {}

        async def fetch_server(server_id: str, entries: list[tuple[str, str, list[str]]]) -> None:
            try:
                conn = await self.ssh_pool.get_connection(server_id)
            except Exception:
                # Mark all containers on this server as unknown
                for app_id, env_id, container_names in entries:
                    cache.setdefault(app_id, {})[env_id] = [
                        {"name": c, "status": "unknown", "image": "", "uptime": ""}
                        for c in container_names
                    ]
                return

            for app_id, env_id, container_names in entries:
                containers_data: list[dict[str, str]] = []
                for container_name in container_names:
                    try:
                        result = await conn.run(
                            f"docker ps -a --format json --filter name=^/{container_name}$",
                            timeout=10,
                        )
                        stdout = result.stdout or ""
                        for line in stdout.strip().splitlines():
                            if not line:
                                continue
                            data = json.loads(line)
                            containers_data.append({
                                "name": data.get("Names", container_name),
                                "status": data.get("State", "unknown"),
                                "image": data.get("Image", ""),
                                "uptime": data.get("Status", ""),
                            })
                    except Exception:
                        containers_data.append({
                            "name": container_name,
                            "status": "unknown",
                            "image": "",
                            "uptime": "",
                        })
                cache.setdefault(app_id, {})[env_id] = containers_data

        await asyncio.gather(
            *(fetch_server(sid, entries) for sid, entries in tasks_by_server.items())
        )

        self.container_cache = cache
        self.post_message(self.ContainerCacheUpdated())


def main() -> None:
    parser = argparse.ArgumentParser(description="Shipyard - Docker Deployment TUI")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = ShipyardApp(config)
    app.run()
