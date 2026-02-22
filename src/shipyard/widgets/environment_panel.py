"""Environment panel widget showing server, path, and container status."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Label, ListView, ListItem, Static
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
        self.template_paths: list[str] = []

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
            if self.local_path:
                yield Static("[bold]Templates[/]", classes="templates-section-title")
                yield ListView(id=f"templates-{self.env_id}", classes="templates-list")

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

    def on_mount(self) -> None:
        self.update_templates()

    def update_templates(self) -> None:
        """Scan local_path for .j2 files and populate the templates ListView."""
        if not self.local_path:
            return
        try:
            list_view = self.query_one(f"#templates-{self.env_id}", ListView)
            title = self.query_one(".templates-section-title", Static)
        except Exception:
            return

        list_view.clear()
        self.template_paths = []
        root = Path(self.local_path).expanduser().resolve()
        if not root.is_dir():
            title.display = False
            list_view.display = False
            return

        j2_files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in sorted(filenames):
                if filename.endswith(".j2") and not filename.startswith("."):
                    full_path = Path(dirpath) / filename
                    rel = str(full_path.relative_to(root))
                    j2_files.append(rel)

        self.template_paths = sorted(j2_files)

        if not self.template_paths:
            title.display = False
            list_view.display = False
            return

        title.display = True
        list_view.display = True
        for rel_path in self.template_paths:
            list_view.append(ListItem(Label(rel_path)))

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
