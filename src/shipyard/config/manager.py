"""Load, validate, and resolve the Shipyard YAML configuration."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from shipyard.config.schema import ShipyardConfig


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def find_config_file(cli_path: str | None = None) -> Path:
    """Locate the config file using the lookup order:
    1. --config CLI argument
    2. ./shipyard.yaml
    3. ~/.config/shipyard/config.yaml
    """
    if cli_path:
        p = Path(cli_path).expanduser()
        if not p.exists():
            raise ConfigError(f"Config file not found: {p}")
        return p

    local = Path("shipyard.yaml")
    if local.exists():
        return local

    user_config = Path.home() / ".config" / "shipyard" / "config.yaml"
    if user_config.exists():
        return user_config

    raise ConfigError(
        "No config file found. Provide --config, or create shipyard.yaml "
        "or ~/.config/shipyard/config.yaml"
    )


def load_config(cli_path: str | None = None) -> ShipyardConfig:
    """Load and validate the configuration file."""
    path = find_config_file(cli_path)

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {path} must contain a YAML mapping")

    try:
        config = ShipyardConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Configuration validation failed:\n{exc}") from exc

    ref_errors = config.validate_references()
    if ref_errors:
        raise ConfigError(
            "Configuration reference errors:\n" + "\n".join(f"  - {e}" for e in ref_errors)
        )

    return config
