"""Servers screen - server connectivity overview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class ServersScreen(Screen):
    """Screen showing all configured servers and their connectivity status."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="servers-container"):
            yield Static("[bold]Servers[/]", id="servers-title")
            table = DataTable(id="servers-table", cursor_type="row")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        self._populate_table()
        self._check_connectivity()

    def _populate_table(self) -> None:
        table = self.query_one("#servers-table", DataTable)
        table.clear(columns=True)
        self._col_keys = table.add_columns(
            "Server", "Hostname", "Port", "User", "Status", "Description"
        )
        config = self.app.shipyard_config
        self._server_status: dict[str, str] = {}
        for server_id, server in config.servers.items():
            user = server.user or config.global_.ssh.default_user
            self._server_status[server_id] = "checking..."
            table.add_row(
                server_id,
                server.hostname,
                str(server.port),
                user,
                "checking...",
                server.description,
                key=server_id,
            )

    def _check_connectivity(self) -> None:
        self.run_worker(self._check_all_servers(), exclusive=True)

    async def _check_all_servers(self) -> None:
        config = self.app.shipyard_config
        ssh_pool = self.app.ssh_pool

        for server_id in config.servers:
            try:
                reachable = await ssh_pool.check_connection(server_id)
                status = "[green]reachable[/]" if reachable else "[red]unreachable[/]"
            except Exception:
                status = "[red]unreachable[/]"

            self._server_status[server_id] = status
            try:
                table = self.query_one("#servers-table", DataTable)
                # Use the stored column key for "Status" (index 4)
                table.update_cell(server_id, self._col_keys[4], status)
            except Exception:
                pass

    def action_refresh(self) -> None:
        self._populate_table()
        self._check_connectivity()

    def action_go_back(self) -> None:
        self.app.pop_screen()
