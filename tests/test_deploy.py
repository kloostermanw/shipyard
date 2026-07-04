"""Tests for the deployer module."""

from __future__ import annotations

from shipyard.deploy.deployer import DeployEvent, DeployStatus
from shipyard.github.client import WorkflowRun
from shipyard.screens.deploy import SPINNER_FRAMES, filter_workflow_runs


def test_deploy_event_creation() -> None:
    """DeployEvent can be created with status and message."""
    event = DeployEvent(status=DeployStatus.RUNNING, message="test")
    assert event.status == DeployStatus.RUNNING
    assert event.message == "test"
    assert event.timestamp is not None


def test_deploy_status_values() -> None:
    """DeployStatus has the expected values."""
    assert DeployStatus.PENDING.value == "pending"
    assert DeployStatus.RUNNING.value == "running"
    assert DeployStatus.SUCCESS.value == "success"
    assert DeployStatus.FAILED.value == "failed"


def _run(name: str, status: str = "in_progress") -> WorkflowRun:
    return WorkflowRun(
        name=name,
        status=status,
        conclusion=None,
        html_url="https://example.com",
        created_at="2026-07-04T00:00:00Z",
    )


def test_filter_empty_returns_all() -> None:
    runs = [_run("Build"), _run("Test")]
    assert filter_workflow_runs(runs, []) == runs


def test_filter_exact_match() -> None:
    runs = [_run("Build and Deploy"), _run("Run Tests"), _run("Lint")]
    result = filter_workflow_runs(runs, ["Build and Deploy", "Lint"])
    assert [r.name for r in result] == ["Build and Deploy", "Lint"]


def test_filter_no_match_returns_empty() -> None:
    runs = [_run("Build"), _run("Test")]
    assert filter_workflow_runs(runs, ["Nonexistent"]) == []


def test_filter_preserves_order() -> None:
    runs = [_run("A"), _run("B"), _run("C")]
    result = filter_workflow_runs(runs, ["C", "A"])
    assert [r.name for r in result] == ["A", "C"]


def test_spinner_frames_nonempty() -> None:
    assert len(SPINNER_FRAMES) > 0
