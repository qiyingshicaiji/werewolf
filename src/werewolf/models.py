from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    use_antidote: bool = Field(default=False)
    use_poison: bool = Field(default=False)
    target: str | None = Field(default=None, description="目标玩家")
    reason: str = Field(..., min_length=1, description="行动理由")


class VoteModelCN(BaseModel):
    target: str = Field(..., min_length=1, description="投票目标")
    reason: str = Field(..., min_length=1, description="投票理由")
