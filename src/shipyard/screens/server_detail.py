"""Server detail screen - shows all Docker containers on a server."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from shipyard.widgets.fetch_status_bar import FetchStatusBar


class ServerDetailScreen(Screen):
    """Screen showing all Docker containers running on a specific server."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(self, server_id: str) -> None:
        super().__init__()
        self.server_id = server_id

    def compose(self) -> ComposeResult:
        config = self.app.shipyard_config
        server = config.servers[self.server_id]

        yield Header()
        with Vertical(id="server-detail-container"):
            yield Static(
                f"[bold]{self.server_id}[/] — {server.hostname}",
                id="server-detail-title",
            )
            yield Static("Loading containers...", id="server-detail-status")
            table = DataTable(id="server-detail-table", cursor_type="row")
            table.add_columns("Container", "Status", "Image", "Uptime")
            yield table
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._apply_cached_containers()

    def _apply_cached_containers(self) -> None:
        """Populate the table from the shared server container cache."""
        status_widget = self.query_one("#server-detail-status", Static)
        table = self.query_one("#server-detail-table", DataTable)
        table.clear()

        containers = self.app.server_container_cache.get(self.server_id, [])

        if not containers:
            status_widget.update("No containers found")
            return

        for c in containers:
            state = c.get("status", "unknown")
            if state == "running":
                status_text = f"[green]{state}[/]"
            elif state in ("exited", "dead"):
                status_text = f"[red]{state}[/]"
            else:
                status_text = f"[yellow]{state}[/]"

            table.add_row(c.get("name", ""), status_text, c.get("image", ""), c.get("uptime", ""))

        status_widget.update(f"{len(containers)} container(s)")

    def on_container_cache_updated(self) -> None:
        """React to global container cache refresh (called by App handler)."""
        self._apply_cached_containers()

    def action_refresh(self) -> None:
        self.app.refresh_container_cache()

    def action_go_back(self) -> None:
        self.app.pop_screen()
