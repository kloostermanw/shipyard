"""Config editor screen - edit the YAML configuration file."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, TextArea


class ConfigScreen(Screen):
    """Screen for editing the YAML configuration file."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._original_content: str = ""

    def compose(self) -> ComposeResult:
        config_path = self.app.config_manager.config_path
        yield Header()
        yield Static(f" Config: [bold]{config_path}[/]", id="section-title")
        yield TextArea(id="config-editor", language="yaml", show_line_numbers=True)
        yield Footer()

    def on_mount(self) -> None:
        config_path = self.app.config_manager.config_path
        if config_path and config_path.exists():
            self._original_content = config_path.read_text(encoding="utf-8")
            editor = self.query_one("#config-editor", TextArea)
            editor.load_text(self._original_content)

    def action_save(self) -> None:
        """Save the config file and reload configuration."""
        config_path = self.app.config_manager.config_path
        if not config_path:
            self.notify("No config path found", severity="error")
            return

        editor = self.query_one("#config-editor", TextArea)
        new_content = editor.text

        # Try to validate before saving
        from shipyard.config.manager import ConfigError, ConfigManager

        import tempfile
        from pathlib import Path

        # Write to temp file and validate
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write(new_content)
            tmp_path = Path(tmp.name)

        try:
            test_manager = ConfigManager(tmp_path)
            test_manager.load()
        except ConfigError as exc:
            tmp_path.unlink()
            self.notify(f"Invalid config: {exc}", severity="error", timeout=8)
            return
        finally:
            tmp_path.unlink(missing_ok=True)

        # Validation passed, save to actual file
        config_path.write_text(new_content, encoding="utf-8")
        self._original_content = new_content

        # Reload config in the app
        try:
            config = self.app.config_manager.load()
            # Reinitialize services with new config
            from shipyard.ssh.connection import SSHConnectionPool
            from shipyard.github.client import GitHubClient
            from shipyard.deploy.deployer import Deployer

            if self.app.ssh_pool:
                import asyncio
                asyncio.ensure_future(self.app.ssh_pool.close_all())

            self.app.ssh_pool = SSHConnectionPool(
                global_settings=config.global_,
                servers=config.servers,
            )
            if self.app.github_client:
                import asyncio
                asyncio.ensure_future(self.app.github_client.close())

            self.app.github_client = GitHubClient(config.global_.github)
            self.app.deployer = Deployer(self.app.ssh_pool)

            self.notify("Config saved and reloaded", severity="information")
        except ConfigError as exc:
            self.notify(f"Saved but reload failed: {exc}", severity="error")

    def action_go_back(self) -> None:
        editor = self.query_one("#config-editor", TextArea)
        if editor.text != self._original_content:
            self.notify("Unsaved changes! Press Ctrl+S to save or Esc again to discard.")
            # Allow second escape to discard
            self._original_content = editor.text
        self.app.pop_screen()
