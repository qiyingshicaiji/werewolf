from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class WorkerConfig(BaseModel):
    id: str
    host: str


class DistributedConfig(BaseModel):
    backend: Literal["simulated", "local_multiprocess", "remote_stub"] = "simulated"
    workers: list[WorkerConfig] = Field(default_factory=list)


class GameConfig(BaseModel):
    max_days: int = 3
    speaking_rounds: int = 1
    mode: Literal["simulate", "llm"] = "simulate"
    enable_distributed: bool = False
    distributed: DistributedConfig = Field(default_factory=DistributedConfig)


class PlayerConfig(BaseModel):
    name: str
    role: Literal["werewolf", "seer", "witch", "villager"]
    character: str


class ModelConfig(BaseModel):
    provider: str = "openai_compatible"
    model_name: str = "gpt-4o-mini"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.7


class ProjectConfig(BaseModel):
    game: GameConfig
    players: list[PlayerConfig]
    model: ModelConfig = Field(default_factory=ModelConfig)

    @model_validator(mode="after")
    def validate_players(self) -> "ProjectConfig":
        if len(self.players) < 5:
            raise ValueError("至少需要 5 名玩家")
        roles = [p.role for p in self.players]
        if roles.count("werewolf") < 1:
            raise ValueError("至少需要 1 个狼人")
        if "seer" not in roles:
            raise ValueError("需要预言家")
        if "witch" not in roles:
            raise ValueError("需要女巫")
        return self


def _expand_env_vars(value: object) -> object:
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def load_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path).expanduser().resolve(strict=True)
    if config_path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("配置文件必须是 .yaml 或 .yml")
    workspace_root = Path.cwd().resolve()
    if not config_path.is_relative_to(workspace_root):
        raise ValueError("配置文件必须位于当前工作目录中")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    expanded = _expand_env_vars(data)
    return ProjectConfig.model_validate(expanded)
