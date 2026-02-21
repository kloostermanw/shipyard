"""Environment panel widget showing server, path, and container status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from textual.widget import Widget


class EnvironmentPanel(Widget):
    """Panel displaying an environment's details and container statuses."""

    def __init__(
        self,
        env_id: str,
        server_id: str,
        path: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.env_id = env_id
        self.server_id = server_id
        self.deploy_path = path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Server: {self.server_id}", classes="env-server")
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
