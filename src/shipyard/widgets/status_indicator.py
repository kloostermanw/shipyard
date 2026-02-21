"""Colored status indicator widget."""

from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive


class StatusIndicator(Widget):
    """A colored dot with a label showing status."""

    DEFAULT_CSS = """
    StatusIndicator {
        width: auto;
        height: 1;
    }
    """

    status: reactive[str] = reactive("unknown")

    STATUS_STYLES = {
        "running": ("green", "●"),
        "healthy": ("green", "●"),
        "stopped": ("red", "●"),
        "exited": ("red", "●"),
        "error": ("red", "●"),
        "reachable": ("green", "●"),
        "unreachable": ("red", "●"),
        "unknown": ("yellow", "○"),
        "deploying": ("yellow", "◉"),
    }

    def __init__(self, status: str = "unknown", **kwargs) -> None:
        super().__init__(**kwargs)
        self.status = status

    def render(self) -> str:
        color, symbol = self.STATUS_STYLES.get(self.status, ("yellow", "○"))
        return f"[{color}]{symbol}[/] {self.status}"
