"""Sync status indicator widget."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget


class SyncIndicator(Widget):
    """A colored indicator showing file sync status."""

    DEFAULT_CSS = """
    SyncIndicator {
        width: auto;
        height: 1;
    }
    """

    status: reactive[str] = reactive("unknown")
    detail: reactive[str] = reactive("")

    STATUS_STYLES: dict[str, tuple[str, str, str]] = {
        "in_sync": ("green", "●", "synced"),
        "out_of_sync": ("yellow", "◉", "out of sync"),
        "syncing": ("cyan", "◉", "syncing..."),
        "checking": ("$text-muted", "○", "checking..."),
        "error": ("red", "●", "error"),
        "unknown": ("$text-muted", "○", "unknown"),
    }

    def __init__(self, status: str = "unknown", **kwargs) -> None:
        super().__init__(**kwargs)
        self.status = status

    def render(self) -> str:
        color, symbol, label = self.STATUS_STYLES.get(
            self.status, ("$text-muted", "○", "unknown")
        )
        text = f"[{color}]{symbol} {label}[/]"
        if self.detail:
            text += f" [dim]({self.detail})[/]"
        return text
