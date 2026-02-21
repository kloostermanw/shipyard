"""Fetch status bar widget - shows server fetch progress."""

from __future__ import annotations

from textual.timer import Timer
from textual.widgets import Static


class FetchStatusBar(Static):
    """A 1-line bar showing container fetch progress across servers."""

    DEFAULT_CSS = """
    FetchStatusBar {
        dock: bottom;
        height: 1;
        width: 100%;
        padding: 0 1;
        display: none;
    }
    """

    _clear_timer: Timer | None = None

    def show_progress(self, completed: int, total: int) -> None:
        """Update the bar as each server completes."""
        if self._clear_timer is not None:
            self._clear_timer.stop()
            self._clear_timer = None

        if completed < total:
            self.update(f"[yellow]Fetching servers: {completed}/{total}[/]")
        else:
            self.update(f"[green]Fetching servers: {completed}/{total} ✓[/]")

        self.display = True

    def show_complete(self) -> None:
        """Start a timer to clear the bar after the cache is fully updated."""
        self._clear_timer = self.set_timer(2.0, self._clear_bar)

    def _clear_bar(self) -> None:
        self._clear_timer = None
        self.update("")
        self.display = False
