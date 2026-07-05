"""Pilot tests for the deploy screen's environment-aware workflow panel."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import ListView, Static

import shipyard.app as app_module
from shipyard.app import ShipyardApp
from shipyard.config.schema import ShipyardConfig
from shipyard.github.client import WorkflowRun
from shipyard.screens.deploy import DeployScreen


def _make_config() -> ShipyardConfig:
    return ShipyardConfig.model_validate(
        {
            "servers": {"s1": {"hostname": "10.0.0.1"}},
            "applications": {
                "myapp": {
                    "name": "My App",
                    "github": {"repo": "owner/repo", "track": "releases"},
                    "environments": {
                        "prd": {
                            "server": "s1",
                            "path": "/opt/myapp",
                            "workflow_filter": ["Build and Deploy"],
                        },
                        "uat": {"server": "s1", "path": "/opt/myapp-uat"},
                    },
                }
            },
        }
    )


class _TestApp(ShipyardApp):
    """App that skips the dashboard/SSH bootstrap so tests stay offline."""

    # CSS_PATH resolves relative to the defining module; pin it to the real file.
    CSS_PATH = str(Path(app_module.__file__).parent / "styles" / "app.tcss")

    def on_mount(self) -> None:  # noqa: D401 - override to no-op
        pass


async def _fake_workflow_runs(repo: str, status: str = "", limit: int = 5):
    if status == "in_progress":
        return [
            WorkflowRun("Build and Deploy", "in_progress", None, "u", "t"),
            WorkflowRun("Lint", "in_progress", None, "u", "t"),
        ]
    if status == "queued":
        return [WorkflowRun("Run Tests", "queued", None, "u", "t")]
    return []


async def _no_releases(repo: str, limit: int = 20):
    return []


def _panel_text(app: _TestApp) -> str:
    panel = app.screen.query_one("#workflow-runs", Static)
    return panel.render().plain


@pytest.mark.asyncio
async def test_env_switch_refilters_workflow_panel() -> None:
    app = _TestApp(_make_config())
    app.github_client.get_workflow_runs = _fake_workflow_runs  # type: ignore[assignment]
    app.github_client.get_releases = _no_releases  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await app.push_screen(DeployScreen("myapp"))
        await pilot.pause()

        # Default highlight is the first env (prd), which filters to its one workflow.
        text = _panel_text(app)
        assert "Build and Deploy" in text
        assert "Lint" not in text
        assert "Run Tests" not in text

        # Switching to uat (no filter) must instantly show all runs.
        env_list = app.screen.query_one("#env-list", ListView)
        env_list.index = 1
        await pilot.pause()
        text = _panel_text(app)
        assert "Build and Deploy" in text
        assert "Lint" in text
        assert "Run Tests" in text

        # Switching back to prd re-applies its filter instantly.
        env_list.index = 0
        await pilot.pause()
        text = _panel_text(app)
        assert "Lint" not in text
        assert "Run Tests" not in text
