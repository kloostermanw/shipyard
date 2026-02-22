"""Secrets screen - manage encrypted secret store."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from shipyard.secrets.store import SecretStoreError


class SecretInputModal(ModalScreen[tuple[str, str] | None]):
    """Modal for adding or editing a secret key-value pair."""

    def __init__(self, key: str = "", value: str = "", editing: bool = False) -> None:
        super().__init__()
        self._initial_key = key
        self._initial_value = value
        self._editing = editing

    def compose(self) -> ComposeResult:
        with Vertical(id="secret-dialog"):
            yield Static(
                "[bold]Edit Secret[/]" if self._editing else "[bold]Add Secret[/]",
                id="secret-dialog-title",
            )
            yield Static("Key:", classes="secret-label")
            yield Input(
                value=self._initial_key,
                id="secret-key-input",
                disabled=self._editing,
            )
            yield Static("Value:", classes="secret-label")
            yield Input(
                value=self._initial_value,
                id="secret-value-input",
                password=True,
            )
            with Horizontal(id="secret-buttons"):
                yield Button("Save", variant="success", id="btn-save")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        if self._editing:
            self.query_one("#secret-value-input", Input).focus()
        else:
            self.query_one("#secret-key-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            key = self.query_one("#secret-key-input", Input).value.strip()
            value = self.query_one("#secret-value-input", Input).value
            if key:
                self.dismiss((key, value))
            return
        self.dismiss(None)


class SecretsScreen(Screen):
    """Screen for managing the encrypted secret store."""

    BINDINGS = [
        Binding("a", "add_secret", "Add", priority=True),
        Binding("e", "edit_secret", "Edit", priority=True),
        Binding("x", "delete_secret", "Delete", priority=True),
        Binding("escape", "go_back", "Back", priority=True),
    ]

    def compose(self) -> ComposeResult:
        store = self.app.secret_store
        yield Header()
        with Vertical(id="secrets-container"):
            if store.is_unlocked:
                yield Static("[bold]Secrets[/]", id="secrets-title")
                yield DataTable(id="secrets-table", cursor_type="row")
            else:
                yield Static("[bold]Unlock Secret Store[/]", id="secrets-title")
                yield Static(
                    "Enter the master password to unlock your secrets.",
                    id="secrets-hint",
                )
                yield Input(
                    placeholder="Master password",
                    password=True,
                    id="password-input",
                )
                yield Static("", id="secrets-error")
        yield Footer()

    def on_mount(self) -> None:
        store = self.app.secret_store
        if store.is_unlocked:
            self._populate_table()
        else:
            self.query_one("#password-input", Input).focus()

    def _populate_table(self) -> None:
        store = self.app.secret_store
        table = self.query_one("#secrets-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Key", "Value")
        for key in store.list_keys():
            table.add_row(key, "********", key=key)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            password = event.input.value
            store = self.app.secret_store
            try:
                store.unlock(password)
            except SecretStoreError as exc:
                error_widget = self.query_one("#secrets-error", Static)
                error_widget.update(f"[red]{exc}[/]")
                event.input.value = ""
                return
            # Re-push screen to rebuild with table view
            self.app.pop_screen()
            self.app.push_screen(SecretsScreen())

    def action_add_secret(self) -> None:
        store = self.app.secret_store
        if not store.is_unlocked:
            return
        self.app.push_screen(SecretInputModal(), callback=self._on_add)

    def _on_add(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        key, value = result
        store = self.app.secret_store
        store.set(key, value)
        self._populate_table()

    def action_edit_secret(self) -> None:
        store = self.app.secret_store
        if not store.is_unlocked:
            return
        table = self.query_one("#secrets-table", DataTable)
        if table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        key = str(row_key.value)
        try:
            value = store.get(key)
        except SecretStoreError:
            return
        self.app.push_screen(
            SecretInputModal(key=key, value=value, editing=True),
            callback=self._on_edit,
        )

    def _on_edit(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        key, value = result
        store = self.app.secret_store
        store.set(key, value)
        self._populate_table()

    def action_delete_secret(self) -> None:
        store = self.app.secret_store
        if not store.is_unlocked:
            return
        table = self.query_one("#secrets-table", DataTable)
        if table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        key = str(row_key.value)
        try:
            store.delete(key)
        except SecretStoreError:
            return
        self._populate_table()

    def action_go_back(self) -> None:
        self.app.pop_screen()
