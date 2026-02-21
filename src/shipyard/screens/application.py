"""Application detail screen with tabbed environments."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from shipyard.widgets.environment_panel import EnvironmentPanel


class ApplicationScreen(Screen):
    """Detail screen for a single application, with one tab per environment."""

    BINDINGS = [
        Binding("d", "deploy", "Deploy", priority=True),
        Binding("l", "logs", "Logs", priority=True),
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(self, app_id: str) -> None:
        super().__init__()
        self.app_id = app_id

    def compose(self) -> ComposeResult:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        yield Header()
        with Vertical(id="application-container"):
            with Vertical(classes="app-header-info"):
                with Horizontal(classes="app-header-row"):
                    yield Static(f"[bold]{app_config.name}[/]", classes="app-name")
                    if app_config.description:
                        yield Static(app_config.description, classes="app-description")
                with Horizontal(classes="app-header-row"):
                    yield Static(
                        f"GitHub: {app_config.github.repo} (tracking {app_config.github.track})",
                        classes="app-github",
                    )
                    yield Static("", id="app-latest-version", classes="app-latest-version")

            with TabbedContent():
                for env_id, env_config in app_config.environments.items():
                    with TabPane(env_id.upper(), id=f"tab-{env_id}"):
                        yield EnvironmentPanel(
                            env_id=env_id,
                            server_id=env_config.server,
                            path=env_config.path,
                            id=f"env-panel-{env_id}",
                        )
        yield Footer()

    def on_mount(self) -> None:
        self._apply_cached_status()
        self.run_worker(self._fetch_latest_version())

    async def _fetch_latest_version(self) -> None:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        github_client = self.app.github_client
        repo = app_config.github.repo
        version = None

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

        if version:
            try:
                widget = self.query_one("#app-latest-version", Static)
                widget.update(f"Latest: {version}")
            except Exception:
                pass

    def _apply_cached_status(self) -> None:
        """Apply cached container status from the app-level cache to all panels."""
        cache = self.app.container_cache
        app_data = cache.get(self.app_id, {})
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        for env_id in app_config.environments:
            try:
                panel = self.query_one(f"#env-panel-{env_id}", EnvironmentPanel)
                containers_data = app_data.get(env_id, [])
                panel.update_containers(containers_data)
            except Exception:
                pass

    def on_shipyard_app_container_cache_updated(self, event) -> None:
        """React to global container cache refresh."""
        self._apply_cached_status()

    def action_deploy(self) -> None:
        from shipyard.screens.deploy import DeployScreen

        self.app.push_screen(DeployScreen(self.app_id))

    def action_logs(self) -> None:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        # Get the active tab's environment
        try:
            tabbed = self.query_one(TabbedContent)
            active_tab = tabbed.active
            # active is the tab id like "tab-prd"
            env_id = active_tab.replace("tab-", "") if active_tab else None
        except Exception:
            env_id = None

        if not env_id:
            env_id = next(iter(app_config.environments))

        env_config = app_config.environments[env_id]
        if env_config.containers:
            from shipyard.screens.logs import LogViewerScreen

            self.app.push_screen(
                LogViewerScreen(
                    server_id=env_config.server,
                    container_name=env_config.containers[0],
                )
            )

    def action_refresh(self) -> None:
        self.app.refresh_container_cache()

    def action_go_back(self) -> None:
        self.app.pop_screen()
