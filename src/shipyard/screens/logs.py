"""Log viewer screen - live container log streaming."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static

from shipyard.widgets.fetch_status_bar import FetchStatusBar


class LogViewerScreen(Screen):
    """Screen for streaming Docker container logs via SSH."""

    BINDINGS = [
        Binding("f", "toggle_follow", "Follow"),
        Binding("c", "clear_logs", "Clear"),
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(self, server_id: str, container_name: str) -> None:
        super().__init__()
        self.server_id = server_id
        self.container_name = container_name
        self._following = True
        self._process = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="logs-container"):
            with Horizontal(id="logs-header"):
                yield Static(
                    f"[bold]Logs: {self.container_name}[/] on {self.server_id}",
                    id="logs-title",
                )
                yield Static("[green]FOLLOWING[/]", id="logs-follow-indicator")
            yield RichLog(
                id="logs-output",
                highlight=True,
                markup=True,
                auto_scroll=True,
                wrap=True,
            )
        yield FetchStatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._start_log_stream()

    def _start_log_stream(self) -> None:
        self.run_worker(self._stream_logs(), exclusive=True)

    async def _stream_logs(self) -> None:
        ssh_pool = self.app.ssh_pool
        log_output = self.query_one("#logs-output", RichLog)

        try:
            conn = await ssh_pool.get_connection(self.server_id)
            command = f"docker logs -f --tail 100 {self.container_name}"
            self._process = await conn.create_process(command, stderr=asyncio.subprocess.STDOUT)

            if self._process.stdout is not None:
                async for line in self._process.stdout:
                    if not self._following:
                        continue
                    log_output.write(line.rstrip("\n"))
        except Exception as exc:
            log_output.write(f"[red]Error: {exc}[/]")

    def action_toggle_follow(self) -> None:
        self._following = not self._following
        indicator = self.query_one("#logs-follow-indicator", Static)
        if self._following:
            indicator.update("[green]FOLLOWING[/]")
            log_output = self.query_one("#logs-output", RichLog)
            log_output.auto_scroll = True
        else:
            indicator.update("[dim]PAUSED[/]")
            log_output = self.query_one("#logs-output", RichLog)
            log_output.auto_scroll = False

    def action_clear_logs(self) -> None:
        log_output = self.query_one("#logs-output", RichLog)
        log_output.clear()

    def action_go_back(self) -> None:
        if self._process is not None:
            self._process.close()
        self.app.pop_screen()
