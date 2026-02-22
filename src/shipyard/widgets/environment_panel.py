"""Environment panel widget showing server, path, and container status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static
from textual.widget import Widget

from shipyard.widgets.sync_indicator import SyncIndicator


class EnvironmentPanel(Widget):
    """Panel displaying an environment's details and container statuses."""

    def __init__(
        self,
        env_id: str,
        server_id: str,
        path: str,
        local_path: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.env_id = env_id
        self.server_id = server_id
        self.deploy_path = path
        self.local_path = local_path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Server: {self.server_id}", classes="env-server")
            if self.local_path:
                with Horizontal(classes="env-path-row"):
                    yield Static(f"Path: {self.deploy_path}", classes="env-path")
                    yield SyncIndicator(id=f"sync-indicator-{self.env_id}")
                yield Static(
                    f"Local: {self.local_path}", classes="env-local-path"
                )
            else:
                yield Static(f"Path: {self.deploy_path}", classes="env-path")
            table = DataTable(id=f"containers-{self.env_id}")
            table.add_columns("Container", "Status", "Image", "Uptime")
            yield table

    def update_containers(self, containers: list[dict]) -> None:
        """Update the container table with fresh data."""
        table = self.query_one(f"#containers-{self.env_id}", DataTable)
        table.clear()
        for c in containers:
            table.add_row(
                c.get("name", ""),
                c.get("status", "unknown"),
                c.get("image", ""),
                c.get("uptime", ""),
            )

    def update_sync_status(self, status: str, detail: str = "") -> None:
        """Update the sync indicator status."""
        if not self.local_path:
            return
        try:
            indicator = self.query_one(
                f"#sync-indicator-{self.env_id}", SyncIndicator
            )
            indicator.status = status
            indicator.detail = detail
        except Exception:
            pass
