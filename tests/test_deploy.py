"""Tests for the deployer module."""

from __future__ import annotations

from shipyard.deploy.deployer import DeployEvent, DeployStatus


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
