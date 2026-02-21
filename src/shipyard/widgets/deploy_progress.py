"""Deploy progress widget for showing real-time deploy output."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static
from textual.widget import Widget


class DeployProgress(Widget):
    """Widget showing deployment output and status."""

    DEFAULT_CSS = """
    DeployProgress {
        height: 1fr;
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status = "pending"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="deploy-status")
            yield RichLog(
                id="deploy-log",
                highlight=True,
                markup=True,
                auto_scroll=True,
                wrap=True,
            )

    def write_line(self, line: str) -> None:
        """Write a line to the deploy log."""
        log = self.query_one("#deploy-log", RichLog)
        log.write(line)

    def set_status(self, status: str, message: str = "") -> None:
        """Update the status display."""
        self._status = status
        status_widget = self.query_one("#deploy-status", Static)
        if status == "running":
            status_widget.update(f"[bold yellow]DEPLOYING[/] {message}")
        elif status == "success":
            status_widget.update(f"[bold green]SUCCESS[/] {message}")
            status_widget.set_class(True, "success")
        elif status == "failed":
            status_widget.update(f"[bold red]FAILED[/] {message}")
            status_widget.set_class(True, "error")
        else:
            status_widget.update(message)
