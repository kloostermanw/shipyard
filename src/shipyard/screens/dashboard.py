"""Dashboard screen - home screen showing all applications."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from shipyard.widgets.fetch_status_bar import FetchStatusBar

# Environment column priority — lower index = further left.
_ENV_PRIORITY = ["prd", "uat", "staging", "dev"]


def _extract_version(image: str) -> str:
    """Extract the tag from a Docker image string (e.g. 'myorg/app:v3.2' → 'v3.2')."""
    if ":" in image:
        return image.rsplit(":", 1)[1]
    return "-"


def _collect_env_columns(config) -> list[str]:
    """Return the union of all environment names across apps, priority-sorted."""
    env_names: set[str] = set()
    for app_config in config.applications.values():
        env_names.update(app_config.environments.keys())

    def sort_key(name: str) -> tuple[int, str]:
        try:
            return (_ENV_PRIORITY.index(name), name)
        except ValueError:
            return (len(_ENV_PRIORITY), name)

    return sorted(env_names, key=sort_key)


class DashboardScreen(Screen):
    """Home screen listing all configured applications."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("s", "servers", "Servers", priority=True),
        Binding("e", "secrets", "Secrets", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._env_columns: list[str] = []
        self._column_keys: list = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-container"):
            yield Static("[bold]Applications[/]")
            yield DataTable(id="app-table", cursor_type="row")
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._populate_table()
        self.run_worker(self._fetch_all_latest_versions())

    def _populate_table(self) -> None:
        config = self.app.shipyard_config
        table = self.query_one("#app-table", DataTable)
        table.clear(columns=True)

        self._env_columns = _collect_env_columns(config)

        # Build columns: Application | Latest | <env1> | <env2> | ...
        # Use add_column individually so we can set minimum widths on version columns.
        _VERSION_COL_WIDTH = 12
        self._column_keys = [
            table.add_column("Application"),
            table.add_column("Latest", width=_VERSION_COL_WIDTH),
        ]
        for env_name in self._env_columns:
            self._column_keys.append(
                table.add_column(env_name.upper(), width=_VERSION_COL_WIDTH)
            )

        for app_id, app_config in config.applications.items():
            row_values = [app_config.name, "..."]  # "..." = loading GitHub
            for env_name in self._env_columns:
                row_values.append(self._get_env_version(app_id, env_name))
            table.add_row(*row_values, key=app_id)

    def _get_env_version(self, app_id: str, env_name: str) -> str:
        """Get the deployed version for an app's environment from the container cache."""
        cache = self.app.container_cache
        app_data = cache.get(app_id, {})
        containers = app_data.get(env_name, [])
        if containers:
            image = containers[0].get("image", "")
            if image:
                return _extract_version(image)
        return "-"

    async def _fetch_all_latest_versions(self) -> None:
        """Fetch latest GitHub version for every app in parallel, updating cells progressively."""
        config = self.app.shipyard_config
        github_client = self.app.github_client

        async def fetch_one(app_id: str) -> None:
            app_config = config.applications[app_id]
            repo = app_config.github.repo
            version: str | None = None
            try:
                if app_config.github.track == "releases":
                    release = await github_client.get_latest_release(repo)
                    if release:
                        version = release.tag_name
                else:
                    tags = await github_client.get_tags(repo, limit=1)
                    if tags:
                        version = tags[0]
            except Exception:
                pass

            try:
                table = self.query_one("#app-table", DataTable)
                table.update_cell(app_id, self._column_keys[1], version or "-")
            except Exception:
                pass

        await asyncio.gather(*(fetch_one(aid) for aid in config.applications))

    def on_container_cache_updated(self) -> None:
        """React to global container cache refresh — update environment columns."""
        config = self.app.shipyard_config
        try:
            table = self.query_one("#app-table", DataTable)
        except Exception:
            return

        for app_id in config.applications:
            for i, env_name in enumerate(self._env_columns):
                col_key = self._column_keys[2 + i]  # skip Application, Latest
                version = self._get_env_version(app_id, env_name)
                try:
                    table.update_cell(app_id, col_key, version)
                except Exception:
                    pass

    def action_quit(self) -> None:
        self.app.exit()

    def action_refresh(self) -> None:
        self._populate_table()
        self.app.refresh_container_cache()
        self.run_worker(self._fetch_all_latest_versions())

    def action_servers(self) -> None:
        from shipyard.screens.servers import ServersScreen

        self.app.push_screen(ServersScreen())

    def action_secrets(self) -> None:
        from shipyard.screens.secrets import SecretsScreen

        self.app.push_screen(SecretsScreen())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle enter key on a table row."""
        app_id = str(event.row_key.value)
        from shipyard.screens.application import ApplicationScreen

        self.app.push_screen(ApplicationScreen(app_id))
