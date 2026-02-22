"""Template detail screen - inspect KEY=VALUE entries and manage secret linkage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from shipyard.secrets.store import SecretStore

_TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


class EntryType(Enum):
    LINKED = "linked"
    NON_LINKED = "non_linked"
    FAILED_LINK = "failed_link"


@dataclass
class TemplateEntry:
    key: str
    raw_value: str
    entry_type: EntryType
    secret_name: str | None
    line_number: int


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class LinkedSecretModal(ModalScreen[tuple[str, str] | str | None]):
    """Modal for editing or deleting a linked secret."""

    def __init__(self, secret_name: str, current_value: str) -> None:
        super().__init__()
        self._secret_name = secret_name
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        with Vertical(id="template-modal-dialog"):
            yield Static("[bold]Edit Linked Secret[/]", id="template-modal-title")
            yield Static(f"Secret: {self._secret_name}", classes="template-modal-label")
            yield Static("Value:", classes="template-modal-label")
            yield Input(
                value=self._current_value,
                id="template-modal-value",
                password=True,
            )
            with Horizontal(id="template-modal-buttons"):
                yield Button("Save", variant="success", id="btn-save")
                yield Button("Delete", variant="error", id="btn-delete")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#template-modal-value", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            value = self.query_one("#template-modal-value", Input).value
            self.dismiss((self._secret_name, value))
        elif event.button.id == "btn-delete":
            self.dismiss("delete")
        else:
            self.dismiss(None)


class ConvertToSecretModal(ModalScreen[tuple[str, str] | None]):
    """Modal for converting a plain value to a secret reference."""

    def __init__(self, key: str, current_value: str) -> None:
        super().__init__()
        self._key = key
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        with Vertical(id="template-modal-dialog"):
            yield Static("[bold]Convert to Secret[/]", id="template-modal-title")
            yield Static(f"Template key: {self._key}", classes="template-modal-label")
            yield Static("Secret name:", classes="template-modal-label")
            yield Input(id="template-modal-name", placeholder="e.g. APP_DB_PASSWORD")
            yield Static("Value:", classes="template-modal-label")
            yield Input(
                value=self._current_value,
                id="template-modal-value",
                password=True,
            )
            with Horizontal(id="template-modal-buttons"):
                yield Button("Convert", variant="success", id="btn-convert")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#template-modal-name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-convert":
            name = self.query_one("#template-modal-name", Input).value.strip()
            value = self.query_one("#template-modal-value", Input).value
            if name:
                self.dismiss((name, value))
            return
        self.dismiss(None)


class CreateMissingSecretModal(ModalScreen[tuple[str, str] | None]):
    """Modal for creating a secret that a template references but doesn't exist."""

    def __init__(self, secret_name: str) -> None:
        super().__init__()
        self._secret_name = secret_name

    def compose(self) -> ComposeResult:
        with Vertical(id="template-modal-dialog"):
            yield Static("[bold]Create Missing Secret[/]", id="template-modal-title")
            yield Static(
                f"Secret: {self._secret_name}", classes="template-modal-label"
            )
            yield Static("Value:", classes="template-modal-label")
            yield Input(id="template-modal-value", password=True)
            with Horizontal(id="template-modal-buttons"):
                yield Button("Create", variant="success", id="btn-create")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#template-modal-value", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            value = self.query_one("#template-modal-value", Input).value
            self.dismiss((self._secret_name, value))
            return
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class TemplateDetailScreen(Screen):
    """Detail screen for a single .j2 template file showing KEY=VALUE entries."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def __init__(
        self,
        local_path: str,
        template_rel_path: str,
        secret_store: SecretStore,
    ) -> None:
        super().__init__()
        self._local_path = local_path
        self._template_rel_path = template_rel_path
        self._secret_store = secret_store
        self._entries: list[TemplateEntry] = []
        self._raw_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="template-detail-container"):
            yield Static(
                f"[bold]Template: {self._template_rel_path}[/]",
                id="template-detail-title",
            )
            yield Static(f"Path: {self._local_path}", id="template-detail-path")
            table = DataTable(id="template-table", cursor_type="row")
            table.add_columns("Key", "Value", "Secret")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        self._parse_and_populate()

    def _parse_and_populate(self) -> None:
        """Parse the template file and populate the table."""
        self._entries.clear()
        file_path = Path(self._local_path).expanduser() / self._template_rel_path

        try:
            text = file_path.read_text()
        except (OSError, UnicodeDecodeError):
            self.notify(f"Cannot read {file_path}", severity="error")
            return

        self._raw_lines = text.splitlines(keepends=True)
        secrets = (
            self._secret_store.get_all() if self._secret_store.is_unlocked else {}
        )

        for line_number, line in enumerate(self._raw_lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue

            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()

            match = _TEMPLATE_RE.fullmatch(value)
            if match:
                secret_name = match.group(1)
                if secret_name in secrets:
                    entry_type = EntryType.LINKED
                else:
                    entry_type = EntryType.FAILED_LINK
                entry = TemplateEntry(
                    key=key,
                    raw_value=value,
                    entry_type=entry_type,
                    secret_name=secret_name,
                    line_number=line_number,
                )
            else:
                entry = TemplateEntry(
                    key=key,
                    raw_value=value,
                    entry_type=EntryType.NON_LINKED,
                    secret_name=None,
                    line_number=line_number,
                )
            self._entries.append(entry)

        self._populate_table()

    def _populate_table(self) -> None:
        """Fill the DataTable from current entries."""
        table = self.query_one("#template-table", DataTable)
        table.clear()
        for i, entry in enumerate(self._entries):
            if entry.entry_type == EntryType.LINKED:
                value_cell = "LINKED"
                secret_cell = f"[green]\u25cf[/] {entry.secret_name}"
            elif entry.entry_type == EntryType.FAILED_LINK:
                value_cell = "FAILED LINK"
                secret_cell = f"[red]x[/] {entry.secret_name}"
            else:
                value_cell = "******"
                secret_cell = "-"
            table.add_row(entry.key, value_cell, secret_cell, key=str(i))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the appropriate modal based on entry type."""
        row_key = event.row_key
        try:
            idx = int(str(row_key.value))
        except (ValueError, TypeError):
            return
        if idx < 0 or idx >= len(self._entries):
            return

        entry = self._entries[idx]

        if entry.entry_type == EntryType.LINKED:
            assert entry.secret_name is not None
            try:
                current_value = self._secret_store.get(entry.secret_name)
            except Exception:
                current_value = ""
            self.app.push_screen(
                LinkedSecretModal(entry.secret_name, current_value),
                callback=lambda result, e=entry: self._on_linked_result(result, e),
            )
        elif entry.entry_type == EntryType.NON_LINKED:
            self.app.push_screen(
                ConvertToSecretModal(entry.key, entry.raw_value),
                callback=lambda result, e=entry: self._on_convert_result(result, e),
            )
        elif entry.entry_type == EntryType.FAILED_LINK:
            assert entry.secret_name is not None
            self.app.push_screen(
                CreateMissingSecretModal(entry.secret_name),
                callback=lambda result, e=entry: self._on_create_result(result, e),
            )

    def _on_linked_result(
        self, result: tuple[str, str] | str | None, entry: TemplateEntry
    ) -> None:
        if result is None:
            return
        if result == "delete":
            assert entry.secret_name is not None
            try:
                self._secret_store.delete(entry.secret_name)
            except Exception:
                pass
            self._parse_and_populate()
            return
        name, new_value = result
        self._secret_store.set(name, new_value)
        self._parse_and_populate()

    def _on_convert_result(
        self, result: tuple[str, str] | None, entry: TemplateEntry
    ) -> None:
        if result is None:
            return
        secret_name, value = result
        self._secret_store.set(secret_name, value)
        self._rewrite_template_line(entry, f"{{{{{secret_name}}}}}")
        self._parse_and_populate()

    def _on_create_result(
        self, result: tuple[str, str] | None, entry: TemplateEntry
    ) -> None:
        if result is None:
            return
        secret_name, value = result
        self._secret_store.set(secret_name, value)
        self._parse_and_populate()

    def _rewrite_template_line(self, entry: TemplateEntry, new_value_expr: str) -> None:
        """Rewrite a single line in the template file."""
        file_path = Path(self._local_path).expanduser() / self._template_rel_path
        try:
            lines = file_path.read_text().splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return

        if entry.line_number < len(lines):
            lines[entry.line_number] = f"{entry.key}={new_value_expr}\n"
            file_path.write_text("".join(lines))

    def action_go_back(self) -> None:
        self.app.pop_screen()
