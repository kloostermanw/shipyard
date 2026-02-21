"""Dashboard screen - home screen showing all applications."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from shipyard.widgets.fetch_status_bar import FetchStatusBar


class DashboardScreen(Screen):
    """Home screen listing all configured applications."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("s", "servers", "Servers", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-container"):
            yield Static("[bold]Applications[/]")
            table = DataTable(id="app-table", cursor_type="row")
            table.add_columns("Application", "Environments", "GitHub")
            yield table
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._populate_table()

    def _populate_table(self) -> None:
        table = self.query_one("#app-table", DataTable)
        table.clear()
        config = self.app.shipyard_config
        for app_id, app_config in config.applications.items():
            envs = ", ".join(app_config.environments.keys())
            table.add_row(
                app_config.name,
                envs,
                app_config.github.repo,
                key=app_id,
            )

    def action_quit(self) -> None:
        self.app.exit()

    def action_refresh(self) -> None:
        self._populate_table()

    def action_servers(self) -> None:
        from shipyard.screens.servers import ServersScreen

        self.app.push_screen(ServersScreen())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle enter key on a table row."""
        app_id = str(event.row_key.value)
        from shipyard.screens.application import ApplicationScreen

        self.app.push_screen(ApplicationScreen(app_id))
