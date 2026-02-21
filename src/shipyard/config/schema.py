"""Pydantic v2 models for the Shipyard YAML configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SSHSettings(BaseModel):
    default_user: str = "root"
    key_path: str = "~/.ssh/id_ed25519"
    connect_timeout: int = 10
    keepalive_interval: int = 30


class GitHubSettings(BaseModel):
    token_env: str = "GITHUB_TOKEN"
    api_base: str = "https://api.github.com"


class GlobalSettings(BaseModel):
    ssh: SSHSettings = SSHSettings()
    github: GitHubSettings = GitHubSettings()


class ServerConfig(BaseModel):
    hostname: str
    port: int = 22
    user: str | None = None
    key_path: str | None = None
    description: str = ""


class GitHubRepoConfig(BaseModel):
    repo: str
    track: Literal["releases", "tags"] = "releases"

    @field_validator("repo")
    @classmethod
    def validate_repo_format(cls, v: str) -> str:
        if "/" not in v or v.count("/") != 1:
            raise ValueError(f"repo must be in 'owner/repo' format, got '{v}'")
        owner, repo = v.split("/")
        if not owner or not repo:
            raise ValueError(f"repo must be in 'owner/repo' format, got '{v}'")
        return v


class EnvironmentConfig(BaseModel):
    server: str
    path: str
    containers: list[str] = []

    @field_validator("path")
    @classmethod
    def validate_absolute_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"path must be absolute (start with /), got '{v}'")
        return v


class ApplicationConfig(BaseModel):
    name: str
    description: str = ""
    github: GitHubRepoConfig
    environments: dict[str, EnvironmentConfig]


class ShipyardConfig(BaseModel):
    global_: GlobalSettings = Field(default_factory=GlobalSettings, alias="global")
    servers: dict[str, ServerConfig]
    applications: dict[str, ApplicationConfig]

    model_config = {"populate_by_name": True}

    def validate_references(self) -> list[str]:
        """Validate cross-references between sections. Returns list of errors."""
        errors = []
        for app_id, app in self.applications.items():
            for env_id, env in app.environments.items():
                if env.server not in self.servers:
                    errors.append(
                        f"Application '{app_id}' environment '{env_id}' references "
                        f"unknown server '{env.server}'"
                    )
        return errors
