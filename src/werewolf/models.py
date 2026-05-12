from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GamePhase(str, Enum):
    WEREWOLF_DISCUSSION = "werewolf_discussion"
    WEREWOLF_VOTE = "werewolf_vote"
    SEER_CHECK = "seer_check"
    WITCH_ACTION = "witch_action"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"
    GAME_END = "game_end"


class DiscussionModelCN(BaseModel):
    speech: str = Field(..., min_length=1, description="公开发言")
    strategy: str = Field(..., min_length=1, description="本轮策略")


class WerewolfKillModelCN(BaseModel):
    target: str = Field(..., min_length=1, description="击杀目标")
    reason: str = Field(..., min_length=1, description="击杀理由")


class SeerCheckModelCN(BaseModel):
    target: str = Field(..., min_length=1, description="查验目标")
    reason: str = Field(..., min_length=1, description="查验理由")


class WitchActionModelCN(BaseModel):
    action: Literal["save", "poison", "pass"] = Field(..., description="女巫行动")
    target: str | None = Field(default=None, description="目标玩家")
    reason: str = Field(..., min_length=1, description="行动理由")

    @model_validator(mode="after")
    def validate_action_target(self) -> "WitchActionModelCN":
        if self.action in ("save", "poison") and not self.target:
            raise ValueError(f"女巫行动为 {self.action} 时必须指定 target")
        if self.action == "pass" and self.target:
            raise ValueError("女巫选择 pass 时不应指定 target")
        return self


class VoteModelCN(BaseModel):
    target: str = Field(..., min_length=1, description="投票目标")
    reason: str = Field(..., min_length=1, description="投票理由")
