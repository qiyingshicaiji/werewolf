from __future__ import annotations

import random
from typing import Type

from agentscope.agent import AgentBase
from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel

from .models import (
    DiscussionModelCN,
    SeerCheckModelCN,
    VoteModelCN,
    WerewolfKillModelCN,
    WitchActionModelCN,
)

CHARACTER_TRAITS: dict[str, str] = {
    "曹操": "多疑、果断、善于权谋，为达目的不择手段",
    "司马懿": "隐忍、冷静、后发制人，善于隐藏真实意图",
    "诸葛亮": "谨慎、善谋、以大局为重，观察入微",
    "关羽": "忠义、刚直、重信守诺，不屑于谎言",
    "赵云": "沉稳、勇武、临危不乱，言行一致",
    "甄姬": "冷静、细腻、擅于观察人心，善于利用信息优势",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "werewolf": "你是狼人，夜晚可以与其他狼人商议后击杀一名玩家。你的目标是消灭所有好人。注意：白天你必须伪装成好人，不能暴露身份。",
    "seer": "你是预言家，每晚可以查验一名玩家的身份是否为狼人。你要引导好人阵营找出狼人，但需要注意保护自己。",
    "witch": "你是女巫，拥有一瓶解药和一瓶毒药。解药可以救活夜晚被狼人击杀的玩家，毒药可以毒杀任意一名玩家。每瓶药只能使用一次。",
    "villager": "你是村民，没有特殊技能。你需要通过观察发言和投票找出狼人，保护好人阵营。",
}


class WerewolfAgent(AgentBase):
    """A werewolf game agent powered by LLM with Three Kingdoms character traits."""

    def __init__(
        self,
        name: str,
        role: str,
        character: str,
        model: ChatModelBase,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.player_role = role
        self.character = character
        self.model = model
        self.rng = rng or random.Random()
        self.alive = True
        self._msg_history: list[dict] = []

    @property
    def role(self) -> str:
        return self.player_role

    def _system_prompt(self) -> str:
        trait = CHARACTER_TRAITS.get(self.character, "沉着、审慎")
        role_desc = ROLE_DESCRIPTIONS.get(self.player_role, "")
        return (
            f"你正在参与一局狼人杀（三国杀版）。\n"
            f"你的三国人物身份是【{self.character}】，性格特点：{trait}\n"
            f"你的狼人杀身份是【{self.player_role}】。{role_desc}\n"
            f"你的游戏名是【{self.name}】。\n"
            f"请始终以{self.character}的口吻和思维方式来发言。你的发言应当体现{self.character}的性格特质。"
        )

    def _build_messages(self, instruction: str, context: list[dict] | None = None) -> list[dict]:
        msgs: list[dict] = [
            {"role": "system", "content": self._system_prompt()},
        ]
        for h in self._msg_history[-20:]:
            msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        if context:
            for c in context:
                msgs.append({"role": c.get("role", "user"), "content": c.get("content", "")})
        msgs.append({"role": "user", "content": instruction})
        return msgs

    def _record(self, role: str, content: str) -> None:
        self._msg_history.append({"role": role, "content": content})

    async def _structured_call(
        self, instruction: str, model_cls: Type[BaseModel], context: list[dict] | None = None
    ) -> dict:
        messages = self._build_messages(instruction, context)
        response = await self.model(messages, structured_model=model_cls)
        if response.metadata:
            self._record("assistant", str(response.metadata))
            return response.metadata
        text = response.get_text_content()
        self._record("assistant", text)
        return {"raw_text": text, "speech": text}

    async def discuss(self, phase: str, context: list[dict]) -> DiscussionModelCN:
        instruction = (
            f"当前是【{phase}】阶段。请根据你的身份和性格，发表一段公开讨论。\n"
            f"你的发言应当：\n"
            f"1. 符合{self.character}的性格和说话方式\n"
            f"2. 根据你的狼人杀身份（{self.player_role}）采取合适的策略\n"
            f"3. 参考之前的发言和事件做出合理推断\n"
            f"4. 发言字段（speech）是你的公开讲话，策略字段（strategy）是你内心的真实想法（只有你自己知道）"
        )
        result = await self._structured_call(instruction, DiscussionModelCN, context)
        try:
            return DiscussionModelCN.model_validate(result)
        except Exception:
            return DiscussionModelCN(
                speech=result.get("speech", "我暂时保留意见。"),
                strategy=result.get("strategy", "继续观察局势"),
            )

    async def werewolf_vote(self, context: list[dict]) -> VoteModelCN:
        alive_non_wolves = [c for c in context if c.get("role") != "werewolf"]
        names = [c.get("name", "未知") for c in alive_non_wolves]
        instruction = (
            f"你是狼人，现在是夜晚击杀表决阶段。\n"
            f"当前存活的非狼人玩家有：{', '.join(names) if names else '无'}\n"
            f"请选择你要击杀的目标，并给出理由。"
        )
        result = await self._structured_call(instruction, VoteModelCN, context)
        try:
            return VoteModelCN.model_validate(result)
        except Exception:
            fallback = alive_non_wolves[0]["name"] if alive_non_wolves else ""
            return VoteModelCN(target=fallback, reason="团队决定")

    async def seer_check(self, context: list[dict]) -> SeerCheckModelCN:
        candidates = [
            c for c in context
            if c.get("name") != self.name and not c.get("checked", False)
        ]
        names = [c.get("name", "未知") for c in candidates]
        instruction = (
            f"你是预言家，现在是夜晚查验阶段。\n"
            f"你可以查验的玩家有：{', '.join(names) if names else '无'}\n"
            f"请选择你要查验的目标，并给出理由。优先查验发言可疑的人。"
        )
        result = await self._structured_call(instruction, SeerCheckModelCN, context)
        try:
            return SeerCheckModelCN.model_validate(result)
        except Exception:
            return SeerCheckModelCN(
                target=candidates[0]["name"] if candidates else "",
                reason="常规查验",
            )

    async def witch_decide(
        self, killed_player: str | None, context: list[dict]
    ) -> WitchActionModelCN:
        kill_info = f"今晚狼人击杀了【{killed_player}】。" if killed_player else "今晚无人被狼人击杀。"
        instruction = (
            f"你是女巫，现在是夜晚行动阶段。\n"
            f"{kill_info}\n"
            f"请决定是否使用解药（救人）或毒药（毒人），或者选择 pass（不使用任何药）。\n"
            f"注意：解药和毒药各只能使用一次，请谨慎选择。"
        )
        result = await self._structured_call(instruction, WitchActionModelCN, context)
        try:
            return WitchActionModelCN.model_validate(result)
        except Exception:
            return WitchActionModelCN(action="pass", reason="暂不使用药剂")

    async def vote(self, context: list[dict]) -> VoteModelCN:
        candidates = [
            c for c in context if c.get("name") != self.name
        ]
        names = [c.get("name", "未知") for c in candidates]
        instruction = (
            f"现在是白天公投阶段。\n"
            f"可以投票的玩家有：{', '.join(names) if names else '无'}\n"
            f"请根据之前的讨论和你的判断，投票给你认为最可疑的玩家，并给出理由。"
        )
        result = await self._structured_call(instruction, VoteModelCN, context)
        try:
            return VoteModelCN.model_validate(result)
        except Exception:
            fallback = candidates[0]["name"] if candidates else ""
            return VoteModelCN(target=fallback, reason="综合判断")

    def observe(self, msg: Msg | list[Msg] | None) -> None:
        """Store messages in agent's memory."""
        if msg is None:
            return
        if isinstance(msg, list):
            for m in msg:
                self._record(m.role, m.get_text_content())
        else:
            self._record(msg.role, msg.get_text_content())

    async def reply(self, *args, **kwargs) -> Msg:
        """Default reply: acknowledge receipt."""
        content = f"{self.name}（{self.character}）已收到信息。"
        return Msg(name=self.name, content=content, role="assistant")
