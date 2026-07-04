"""Deploy screen - version selection, confirmation, and live deploy output."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, ListView, ListItem, Label, Static

from shipyard.deploy.deployer import DeployStatus
from shipyard.github.client import WorkflowRun
from shipyard.widgets.deploy_progress import DeployProgress
from shipyard.widgets.fetch_status_bar import FetchStatusBar

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def filter_workflow_runs(
    runs: list[WorkflowRun], filter_names: list[str]
) -> list[WorkflowRun]:
    """Return runs whose name is in filter_names. Empty filter returns all runs."""
    if not filter_names:
        return list(runs)
    allowed = set(filter_names)
    return [r for r in runs if r.name in allowed]


class DeployConfirmModal(ModalScreen[bool]):
    """Confirmation dialog before deploying."""

    def __init__(
        self, app_name: str, version: str, env_id: str, server_id: str
    ) -> None:
        super().__init__()
        self.app_name = app_name
        self.version = version
        self.env_id = env_id
        self.server_id = server_id

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"[bold]Deploy {self.app_name}?[/]", id="confirm-title")
            yield Static(f"  Version:     {self.version}", classes="confirm-detail")
            yield Static(f"  Environment: {self.env_id}", classes="confirm-detail")
            yield Static(f"  Server:      {self.server_id}", classes="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Deploy", variant="success", id="btn-deploy")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-deploy")


class DeployScreen(Screen):
    """Screen for selecting a version and deploying an application."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(self, app_id: str) -> None:
        super().__init__()
        self.app_id = app_id
        self._selected_env: str | None = None
        self._selected_version: str | None = None
        self._deploying = False
        self._env_ids: list[str] = []
        self._version_names: list[str] = []
        self._workflow_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        yield Header()
        with Vertical(id="deploy-container"):
            yield Static(f"[bold]Deploy {app_config.name}[/]", id="deploy-title")
            yield Static("", id="workflow-runs")
            with Horizontal(id="version-selection"):
                self._env_ids = list(app_config.environments.keys())
                env_items = [
                    ListItem(Label(env_id.upper()))
                    for env_id in self._env_ids
                ]
                yield ListView(*env_items, id="env-list")
                yield ListView(id="version-list")
            yield DeployProgress(id="deploy-progress")
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        # Hide progress initially
        self.query_one("#deploy-progress").display = False
        self.query_one("#workflow-runs").display = False
        self._load_versions()
        self.run_worker(self._fetch_workflow_runs())
        # Start polling for workflow run updates
        interval_ms = self.app.shipyard_config.global_.github.polling_interval
        self._workflow_timer = self.set_interval(
            interval_ms / 1000, self._poll_workflow_runs
        )

    def _load_versions(self) -> None:
        self.run_worker(self._fetch_versions(), exclusive=True)

    async def _fetch_versions(self) -> None:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        github_client = self.app.github_client

        version_list = self.query_one("#version-list", ListView)
        version_list.clear()

        self._version_names = []
        if app_config.github.track == "releases":
            releases = await github_client.get_releases(app_config.github.repo, limit=10)
            for release in releases:
                label = release.tag_name
                if release.prerelease:
                    label += " [pre-release]"
                self._version_names.append(release.tag_name)
                version_list.append(ListItem(Label(label)))
        else:
            tags = await github_client.get_tags(app_config.github.repo, limit=10)
            for tag in tags:
                self._version_names.append(tag)
                version_list.append(ListItem(Label(tag)))

        self._version_names.append("develop")
        version_list.append(ListItem(Label("develop")))

    def _poll_workflow_runs(self) -> None:
        """Periodic callback to refresh workflow runs."""
        if not self._deploying:
            self.run_worker(self._fetch_workflow_runs())

    async def _fetch_workflow_runs(self) -> None:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]
        github_client = self.app.github_client

        runs = await github_client.get_workflow_runs(
            app_config.github.repo, status="in_progress"
        )
        runs += await github_client.get_workflow_runs(
            app_config.github.repo, status="queued"
        )

        panel = self.query_one("#workflow-runs", Static)
        if runs:
            lines = ["[bold yellow]GitHub Actions running:[/]"]
            for run in runs:
                icon = "\u25cb" if run.status == "queued" else "\u25cf"
                lines.append(f"  {icon} {run.name} [{run.status}]")
            panel.update("\n".join(lines))
            panel.display = True
        else:
            panel.update("[dim]No active workflows[/]")
            panel.display = True

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Track environment selection when the cursor moves."""
        if event.list_view.id == "env-list":
            idx = event.list_view.index
            if idx is not None and idx < len(self._env_ids):
                self._selected_env = self._env_ids[idx]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_view = event.list_view
        idx = event.list_view.index
        if idx is None:
            return
        if list_view.id == "env-list" and idx < len(self._env_ids):
            self._selected_env = self._env_ids[idx]
        elif list_view.id == "version-list" and idx < len(self._version_names):
            self._selected_version = self._version_names[idx]
            self._try_confirm()

    def _try_confirm(self) -> None:
        if self._deploying:
            return

        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        # Auto-select first env if only one
        if not self._selected_env:
            if len(app_config.environments) == 1:
                self._selected_env = next(iter(app_config.environments))
            else:
                return

        if not self._selected_version:
            return

        env_config = app_config.environments[self._selected_env]
        self.app.push_screen(
            DeployConfirmModal(
                app_name=app_config.name,
                version=self._selected_version,
                env_id=self._selected_env,
                server_id=env_config.server,
            ),
            callback=self._on_confirm,
        )

    def _on_confirm(self, confirmed: bool) -> None:
        if confirmed and self._selected_env and self._selected_version:
            self._start_deploy()

    def _start_deploy(self) -> None:
        self._deploying = True
        if self._workflow_timer:
            self._workflow_timer.stop()
        # Show progress, hide selection
        self.query_one("#workflow-runs").display = False
        self.query_one("#version-selection").display = False
        self.query_one("#deploy-progress").display = True
        self.run_worker(self._run_deploy(), exclusive=True)

    async def _run_deploy(self) -> None:
        config = self.app.shipyard_config
        env_config = config.applications[self.app_id].environments[self._selected_env]
        deployer = self.app.deployer
        progress = self.query_one("#deploy-progress", DeployProgress)

        async for event in deployer.deploy(
            app_id=self.app_id,
            env_id=self._selected_env,
            version=self._selected_version,
            env_config=env_config,
        ):
            if event.status == DeployStatus.RUNNING:
                progress.set_status("running", event.message)
                progress.write_line(event.message)
            elif event.status == DeployStatus.SUCCESS:
                progress.set_status("success", event.message)
                progress.write_line(f"[green]{event.message}[/]")
            elif event.status == DeployStatus.FAILED:
                progress.set_status("failed", event.message)
                progress.write_line(f"[red]{event.message}[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()
