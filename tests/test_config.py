"""Tests for config schema and manager."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from shipyard.config.manager import ConfigError, load_config
from shipyard.config.schema import (
    ApplicationConfig,
    EnvironmentConfig,
    GitHubRepoConfig,
    ShipyardConfig,
    ServerConfig,
)


class TestSchema:
    """Tests for Pydantic config models."""

    def test_valid_config(self, sample_config_dict: dict) -> None:
        config = ShipyardConfig.model_validate(sample_config_dict)
        assert "prod-01" in config.servers
        assert "frontend" in config.applications
        assert config.global_.ssh.default_user == "deploy"

    def test_global_defaults(self) -> None:
        config = ShipyardConfig.model_validate({
            "servers": {"s1": {"hostname": "10.0.0.1"}},
            "applications": {},
        })
        assert config.global_.ssh.default_user == "root"
        assert config.global_.ssh.key_path == "~/.ssh/id_ed25519"
        assert config.global_.github.token_env == "GITHUB_TOKEN"

    def test_invalid_repo_format(self) -> None:
        with pytest.raises(ValidationError, match="owner/repo"):
            GitHubRepoConfig(repo="not-valid")

    def test_invalid_repo_missing_parts(self) -> None:
        with pytest.raises(ValidationError, match="owner/repo"):
            GitHubRepoConfig(repo="/repo")

    def test_invalid_path_not_absolute(self) -> None:
        with pytest.raises(ValidationError, match="absolute"):
            EnvironmentConfig(server="s1", path="relative/path")

    def test_valid_environment(self) -> None:
        env = EnvironmentConfig(
            server="prod-01",
            path="/opt/apps/test",
            containers=["test-web"],
        )
        assert env.server == "prod-01"
        assert env.containers == ["test-web"]

    def test_containers_default_empty(self) -> None:
        env = EnvironmentConfig(server="s1", path="/opt/apps/test")
        assert env.containers == []

    def test_server_user_optional(self) -> None:
        server = ServerConfig(hostname="10.0.0.1")
        assert server.user is None
        assert server.port == 22

    def test_track_validation(self) -> None:
        gh = GitHubRepoConfig(repo="org/repo", track="tags")
        assert gh.track == "tags"

        with pytest.raises(ValidationError):
            GitHubRepoConfig(repo="org/repo", track="branches")


class TestCrossReferences:
    """Tests for cross-reference validation."""

    def test_valid_references(self, sample_config: ShipyardConfig) -> None:
        errors = sample_config.validate_references()
        assert errors == []

    def test_unknown_server_reference(self, sample_config_dict: dict) -> None:
        sample_config_dict["applications"]["frontend"]["environments"]["prd"]["server"] = (
            "nonexistent"
        )
        config = ShipyardConfig.model_validate(sample_config_dict)
        errors = config.validate_references()
        assert len(errors) == 1
        assert "nonexistent" in errors[0]


class TestConfigManager:
    """Tests for config file loading."""

    def test_load_config_from_path(self, tmp_path: Path, sample_config_dict: dict) -> None:
        import yaml

        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(sample_config_dict))

        config = load_config(str(config_file))
        assert "prod-01" in config.servers

    def test_load_config_missing_file(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config("/nonexistent/path.yaml")

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.yaml"
        config_file.write_text(": invalid: yaml: {{{}}")

        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(str(config_file))

    def test_load_config_invalid_schema(self, tmp_path: Path) -> None:
        import yaml

        config_file = tmp_path / "bad_schema.yaml"
        config_file.write_text(yaml.dump({"servers": "not-a-dict", "applications": {}}))

        with pytest.raises(ConfigError, match="validation failed"):
            load_config(str(config_file))

    def test_load_config_bad_references(self, tmp_path: Path, sample_config_dict: dict) -> None:
        import yaml

        sample_config_dict["applications"]["frontend"]["environments"]["prd"]["server"] = (
            "missing"
        )
        config_file = tmp_path / "bad_ref.yaml"
        config_file.write_text(yaml.dump(sample_config_dict))

        with pytest.raises(ConfigError, match="reference errors"):
            load_config(str(config_file))
