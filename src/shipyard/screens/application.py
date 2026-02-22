"""Application detail screen with tabbed environments."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListView, Static, TabbedContent, TabPane

from shipyard.widgets.environment_panel import EnvironmentPanel
from shipyard.widgets.fetch_status_bar import FetchStatusBar


class ApplicationScreen(Screen):
    """Detail screen for a single application, with one tab per environment."""

    BINDINGS = [
        Binding("d", "deploy", "Deploy", priority=True),
        Binding("l", "logs", "Logs", priority=True),
        Binding("y", "sync", "Sync", priority=True),
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
                            local_path=env_config.local_path,
                            id=f"env-panel-{env_id}",
                        )
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._apply_cached_status()
        self.run_worker(self._fetch_latest_version())
        self.run_worker(self._check_sync_statuses())

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

    async def _check_sync_statuses(self) -> None:
        """Check sync status for all environments that have local_path configured."""
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        syncer = self.app.file_syncer

        for env_id, env_config in app_config.environments.items():
            if not env_config.local_path:
                continue

            try:
                panel = self.query_one(f"#env-panel-{env_id}", EnvironmentPanel)
                panel.update_sync_status("checking")
            except Exception:
                continue

            try:
                result = await syncer.check_sync_status(
                    server_id=env_config.server,
                    local_path=env_config.local_path,
                    remote_path=env_config.path,
                )
                panel = self.query_one(f"#env-panel-{env_id}", EnvironmentPanel)
                if result.is_in_sync:
                    panel.update_sync_status("in_sync")
                else:
                    detail = f"{result.total_changes} file(s)"
                    panel.update_sync_status("out_of_sync", detail)
            except Exception:
                try:
                    panel = self.query_one(f"#env-panel-{env_id}", EnvironmentPanel)
                    panel.update_sync_status("error")
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

    def on_container_cache_updated(self) -> None:
        """React to global container cache refresh (called by App handler)."""
        self._apply_cached_status()
        self.run_worker(self._check_sync_statuses())

    def _get_active_env_id(self) -> str | None:
        """Get the environment ID of the currently active tab."""
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        try:
            tabbed = self.query_one(TabbedContent)
            active_tab = tabbed.active
            env_id = active_tab.replace("tab-", "") if active_tab else None
        except Exception:
            env_id = None

        if not env_id:
            env_id = next(iter(app_config.environments))

        return env_id

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection of a template from the templates ListView."""
        list_view = event.list_view
        if not (list_view.id and list_view.id.startswith("templates-")):
            return

        env_id = list_view.id.replace("templates-", "")
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        env_config = app_config.environments.get(env_id)
        if not env_config or not env_config.local_path:
            return

        store = self.app.secret_store
        if not store.is_unlocked:
            self.notify("Unlock the secret store first (press 'e' on dashboard)", severity="warning")
            return

        # Look up template path by index (same pattern as deploy.py)
        panel = self.query_one(f"#env-panel-{env_id}", EnvironmentPanel)
        idx = list_view.index
        if idx is None or idx >= len(panel.template_paths):
            return
        template_rel_path = panel.template_paths[idx]

        from shipyard.screens.template_detail import TemplateDetailScreen

        self.app.push_screen(
            TemplateDetailScreen(
                local_path=env_config.local_path,
                template_rel_path=template_rel_path,
                secret_store=store,
            )
        )

    def action_deploy(self) -> None:
        from shipyard.screens.deploy import DeployScreen

        self.app.push_screen(DeployScreen(self.app_id))

    def action_logs(self) -> None:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        env_id = self._get_active_env_id()

        if not env_id:
            return

        env_config = app_config.environments[env_id]
        if env_config.containers:
            from shipyard.screens.logs import LogViewerScreen

            self.app.push_screen(
                LogViewerScreen(
                    server_id=env_config.server,
                    container_name=env_config.containers[0],
                )
            )

    def action_sync(self) -> None:
        """Open sync screen for the active tab's environment."""
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        env_id = self._get_active_env_id()

        if not env_id:
            return

        env_config = app_config.environments[env_id]
        if not env_config.local_path:
            self.notify("No local-path configured for this environment", severity="warning")
            return

        from shipyard.screens.sync import SyncScreen

        self.app.push_screen(
            SyncScreen(
                app_id=self.app_id,
                env_id=env_id,
                server_id=env_config.server,
                local_path=env_config.local_path,
                remote_path=env_config.path,
            )
        )

    def action_refresh(self) -> None:
        self.app.refresh_container_cache()

    def action_go_back(self) -> None:
        self.app.pop_screen()
