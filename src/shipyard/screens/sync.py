"""Sync screen - file sync progress display."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from shipyard.sync.syncer import SyncStatus
from shipyard.widgets.deploy_progress import DeployProgress


class SyncScreen(Screen):
    """Screen showing file sync progress for an environment."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(
        self,
        app_id: str,
        env_id: str,
        server_id: str,
        local_path: str,
        remote_path: str,
    ) -> None:
        super().__init__()
        self.app_id = app_id
        self.env_id = env_id
        self.server_id = server_id
        self.local_path = local_path
        self.remote_path = remote_path

    def compose(self) -> ComposeResult:
        config = self.app.shipyard_config
        app_config = config.applications[self.app_id]

        yield Header()
        with Vertical(id="sync-container"):
            yield Static(
                f"[bold]Sync {app_config.name} / {self.env_id.upper()}[/]",
                id="sync-title",
            )
            yield Static(
                f"Local: {self.local_path} → Remote: {self.server_id}:{self.remote_path}",
                id="sync-paths",
            )
            yield DeployProgress(id="sync-progress")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run_sync(), exclusive=True)

    async def _run_sync(self) -> None:
        syncer = self.app.file_syncer
        progress = self.query_one("#sync-progress", DeployProgress)

        async for event in syncer.sync(
            server_id=self.server_id,
            local_path=self.local_path,
            remote_path=self.remote_path,
        ):
            if event.status == SyncStatus.SYNCING:
                msg = event.message
                if event.progress:
                    msg = f"[{event.progress[0]}/{event.progress[1]}] {msg}"
                progress.set_status("running", msg)
                progress.write_line(event.message)
            elif event.status == SyncStatus.IN_SYNC:
                progress.set_status("success", event.message)
                progress.write_line(f"[green]{event.message}[/]")
            elif event.status == SyncStatus.ERROR:
                progress.set_status("failed", event.message)
                progress.write_line(f"[red]{event.message}[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()
