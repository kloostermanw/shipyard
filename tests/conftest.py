"""Shared test fixtures."""

from __future__ import annotations

import pytest

from shipyard.config.schema import (
    ApplicationConfig,
    EnvironmentConfig,
    GitHubRepoConfig,
    GitHubSettings,
    GlobalSettings,
    ShipyardConfig,
    ServerConfig,
    SSHSettings,
)


@pytest.fixture
def sample_config_dict() -> dict:
    """A valid config dict for testing."""
    return {
        "global": {
            "ssh": {
                "default_user": "deploy",
                "key_path": "~/.ssh/id_ed25519",
                "connect_timeout": 10,
                "keepalive_interval": 30,
            },
            "github": {
                "token_env": "GITHUB_TOKEN",
            },
        },
        "servers": {
            "prod-01": {
                "hostname": "10.0.1.10",
                "port": 22,
                "user": "deploy",
                "description": "Production server",
            },
            "staging-01": {
                "hostname": "10.0.2.10",
                "port": 22,
                "description": "Staging server",
            },
        },
        "applications": {
            "frontend": {
                "name": "Frontend App",
                "description": "Next.js frontend",
                "github": {
                    "repo": "myorg/frontend",
                    "track": "releases",
                },
                "environments": {
                    "prd": {
                        "server": "prod-01",
                        "path": "/opt/apps/frontend",
                        "containers": ["frontend-prd-web", "frontend-prd-nginx"],
                    },
                    "staging": {
                        "server": "staging-01",
                        "path": "/opt/apps/frontend",
                        "containers": ["frontend-staging-web"],
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_config(sample_config_dict: dict) -> ShipyardConfig:
    """A valid ShipyardConfig for testing."""
    return ShipyardConfig.model_validate(sample_config_dict)
