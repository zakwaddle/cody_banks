"""Configuration loading for Cody Banks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "local"
    model: str = "local-model"
    temperature: float = 0.2
    max_tokens: int = 4096


@dataclass(frozen=True)
class PermissionsConfig:
    mode: str = "ask"


@dataclass(frozen=True)
class Config:
    model: ModelConfig = ModelConfig()
    permissions: PermissionsConfig = PermissionsConfig()


def load_config(path: Path | None = None) -> Config:
    if path is None:
        return Config()

    with path.expanduser().resolve().open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    model_config = raw_config.get("model", {})
    permissions_config = raw_config.get("permissions", {})

    return Config(
        model=ModelConfig(
            base_url=model_config.get("base_url", ModelConfig.base_url),
            api_key=model_config.get("api_key", ModelConfig.api_key),
            model=model_config.get("model", ModelConfig.model),
            temperature=model_config.get("temperature", ModelConfig.temperature),
            max_tokens=model_config.get("max_tokens", ModelConfig.max_tokens),
        ),
        permissions=PermissionsConfig(
            mode=permissions_config.get("mode", PermissionsConfig.mode),
        ),
    )

