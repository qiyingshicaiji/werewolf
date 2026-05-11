from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from agentscope.message import Msg
from agentscope.pipeline import MsgHub, fanout_pipeline

from .config import ProjectConfig
from .distributed import DistributedHook, run_map
from .logger import RunLogger
from .models import (
    DiscussionModelCN,
    SeerCheckModelCN,
    VoteModelCN,
    WerewolfKillModelCN,
    WitchActionModelCN,
)

CHARACTER_TRAITS = {
    "曹操": "多疑、果断、善于权谋",
    "司马懿": "隐忍、冷静、后发制人",
    "诸葛亮": "谨慎、善谋、以大局为重",
    "关羽": "忠义、刚直、重信守诺",
    "赵云": "沉稳、勇武、临危不乱",
    "甄姬": "冷静、细腻、擅于观察人心",
}


@dataclass
class PlayerState:
    name: str
    role: str
    character: str
    alive: bool = True
    memory: list[Msg] = field(default_factory=list)


class PlayerAgent:
    def __init__(self, state: PlayerState, rng: random.Random) -> None:
        self.state = state
        self.id = state.name
        self.rng = rng
        self._subs: dict[str, list["PlayerAgent"]] = {}

    @property
    def name(self) -> str:
        return self.state.name

    def reset_subscribers(self, hub_name: str, participants: list["PlayerAgent"]) -> None:
        self._subs[hub_name] = [p for p in participants if p.id != self.id]

    def remove_subscribers(self, hub_name: str) -> None:
        self._subs.pop(hub_name, None)

    async def observe(self, msg: Msg | list[Msg]) -> None:
        if isinstance(msg, list):
            self.state.memory.extend(msg)
        else:
            self.state.memory.append(msg)

    async def __call__(self, msg: Msg | list[Msg] | None = None, **_: Any) -> Msg:
        if msg is not None:
            await self.observe(msg)
        content = f"{self.name}（{self.state.character}）已收到信息。"
        out = Msg(name=self.name, content=content, role="assistant")
        for subscribers in self._subs.values():
            for agent in subscribers:
                await agent.observe(out)
        return out


class SanguoWerewolfGame:
    def __init__(self, config: ProjectConfig, logger: RunLogger, seed: int = 42) -> None:
        self.config = config
        self.logger = logger
        self.rng = random.Random(seed)
        self.players: list[PlayerState] = [
            PlayerState(name=p.name, role=p.role, character=p.character)
            for p in config.players
        ]
        self.agents = {p.name: PlayerAgent(p, self.rng) for p in self.players}
        self.witch_has_antidote = True
        self.witch_has_poison = True
        self.day = 1
        worker_ids = [w.id for w in config.game.distributed.workers]
        self.distributed_hook = DistributedHook(
            backend=config.game.distributed.backend,
            worker_ids=worker_ids,
        )

    def _alive(self, role: str | None = None) -> list[PlayerState]:
        base = [p for p in self.players if p.alive]
        if role is None:
            return base
        return [p for p in base if p.role == role]

    def _player_prompt(self, p: PlayerState) -> str:
        trait = CHARACTER_TRAITS.get(p.character, "沉着、审慎")
        return f"你是三国人物{p.character}，性格：{trait}。当前狼人杀身份：{p.role}。"

    def _safe_choose(self, candidates: list[PlayerState], exclude: str | None = None) -> PlayerState:
        options = [p for p in candidates if p.name != exclude]
        return self.rng.choice(options if options else candidates)

    def _safe_discussion(self, p: PlayerState, phase: str) -> DiscussionModelCN:
        try:
            return DiscussionModelCN(
                speech=f"{p.character}表示：{phase}阶段我会谨慎判断，维护己方利益。",
                strategy=f"{self._player_prompt(p)}",
            )
        except Exception:
            return DiscussionModelCN(speech="我暂时保留意见。", strategy="继续观察局势")

    def _werewolf_kill(self) -> WerewolfKillModelCN:
        wolves = self._alive("werewolf")
        villagers = [p for p in self._alive() if p.role != "werewolf"]
        if not villagers:
            target = wolves[0].name if wolves else ""
            return WerewolfKillModelCN(target=target, reason="无可击杀目标")
        fallback = WerewolfKillModelCN(target=villagers[0].name, reason="随机兜底")
        if not wolves or not villagers:
            return fallback
        try:
            target = self._safe_choose(villagers).name
            return WerewolfKillModelCN(target=target, reason="优先打击高威胁角色")
        except Exception:
            return fallback

    async def _werewolf_discussion_and_vote(self) -> WerewolfKillModelCN:
        wolves = self._alive("werewolf")
        if not wolves:
            return self._werewolf_kill()

        wolf_names = [w.name for w in wolves]
        for wolf in wolves:
            discussion = self._safe_discussion(wolf, phase="狼人密谈")
            self.logger.write("werewolf_discussion", {"speaker": wolf.name, **discussion.model_dump()})
            msg = Msg(name=wolf.name, content=discussion.speech, role="assistant")
            try:
                await self._fanout(wolf_names, msg)
            except Exception as exc:
                self.logger.write("error", {"where": "wolf_fanout", "speaker": wolf.name, "error": str(exc)})

        villagers = [p for p in self._alive() if p.role != "werewolf"]
        if not villagers:
            return WerewolfKillModelCN(target=wolves[0].name, reason="场上仅剩狼人，无需击杀")
        votes: list[VoteModelCN] = []
        for wolf in wolves:
            target = self._safe_choose(villagers).name
            vote = VoteModelCN(target=target, reason=f"{wolf.character}主张优先击杀该目标")
            votes.append(vote)
            self.logger.write("werewolf_vote", {"voter": wolf.name, **vote.model_dump()})

        tally: dict[str, int] = {}
        for vote in votes:
            tally[vote.target] = tally.get(vote.target, 0) + 1
        if not tally:
            return self._werewolf_kill()
        target = self._pick_by_tally(tally, "werewolf_vote")
        return WerewolfKillModelCN(target=target, reason="狼人内部投票结果")

    def _seer_check(self) -> SeerCheckModelCN | None:
        seers = self._alive("seer")
        if not seers:
            return None
        seer = seers[0]
        target = self._safe_choose(self._alive(), exclude=seer.name)
        return SeerCheckModelCN(target=target.name, reason="查验可疑对象")

    def _witch_action(self, werewolf_target: str | None) -> WitchActionModelCN | None:
        witches = self._alive("witch")
        if not witches:
            return None
        if werewolf_target and self.witch_has_antidote and self.rng.random() < 0.5:
            self.witch_has_antidote = False
            return WitchActionModelCN(
                action="save",
                use_antidote=True,
                target=werewolf_target,
                reason="判断该玩家暂时不该出局",
            )
        alive_non_witch = [p for p in self._alive() if p.role != "witch"]
        if self.witch_has_poison and alive_non_witch and self.rng.random() < 0.2:
            self.witch_has_poison = False
            poison_target = self._safe_choose(alive_non_witch)
            return WitchActionModelCN(
                action="poison",
                use_poison=True,
                target=poison_target.name,
                reason="压制潜在威胁",
            )
        return WitchActionModelCN(action="pass", reason="保留药剂", target=None)

    def _day_vote(self) -> list[VoteModelCN]:
        alive = self._alive()
        votes: list[VoteModelCN] = []
        for voter in alive:
            target = self._safe_choose(alive, exclude=voter.name)
            votes.append(VoteModelCN(target=target.name, reason=f"{voter.character}认为其发言可疑"))
        return votes

    def _pick_by_tally(self, tally: dict[str, int], reason: str) -> str:
        highest = max(tally.values())
        candidates = [name for name, score in tally.items() if score == highest]
        winner = self.rng.choice(candidates)
        if len(candidates) > 1:
            self.logger.write("tie_break", {"reason": reason, "candidates": candidates, "chosen": winner})
        return winner

    async def _fanout(self, speaker_names: list[str], msg: Msg) -> None:
        agents = [self.agents[n] for n in speaker_names]
        async with MsgHub(participants=agents, enable_auto_broadcast=True):
            await fanout_pipeline(agents, msg=msg, enable_gather=False)

    def _eliminate(self, name: str, reason: str) -> None:
        for p in self.players:
            if p.name == name and p.alive:
                p.alive = False
                self.logger.write("eliminate", {"name": name, "reason": reason})
                return

    def _win_check(self) -> str | None:
        wolves = self._alive("werewolf")
        good = [p for p in self._alive() if p.role != "werewolf"]
        if not wolves:
            return "好人阵营获胜"
        if len(wolves) >= len(good):
            return "狼人阵营获胜"
        return None

    async def run(self) -> dict[str, Any]:
        self.logger.write("game_start", {"players": [p.__dict__ for p in self.players]})
        self.logger.write("distributed", {"mode": self.distributed_hook.describe()})

        while self.day <= self.config.game.max_days:
            self.logger.write("phase", {"day": self.day, "name": "night"})
            werewolf_action = await self._werewolf_discussion_and_vote()
            self.logger.write("werewolf_kill", werewolf_action.model_dump())

            seer_action = self._seer_check()
            if seer_action:
                checked = next((p for p in self.players if p.name == seer_action.target), None)
                if checked:
                    self.logger.write(
                        "seer_check",
                        {**seer_action.model_dump(), "result": checked.role != "werewolf"},
                    )
                else:
                    self.logger.write("error", {"where": "seer_check", "error": "target not found"})

            witch_action = self._witch_action(werewolf_action.target)
            if witch_action:
                self.logger.write("witch_action", witch_action.model_dump())

            killed_tonight = werewolf_action.target
            if witch_action and witch_action.action == "save" and witch_action.target == killed_tonight:
                killed_tonight = None
            if witch_action and witch_action.action == "poison" and witch_action.target:
                self._eliminate(witch_action.target, "女巫毒杀")
            if killed_tonight:
                self._eliminate(killed_tonight, "狼人夜袭")

            result = self._win_check()
            if result:
                self.logger.write("game_end", {"day": self.day, "winner": result})
                return {"winner": result, "log_path": str(self.logger.path)}

            self.logger.write("phase", {"day": self.day, "name": "day"})
            alive_names = [p.name for p in self._alive()]
            for p in run_map(self._alive(), self.distributed_hook):
                discussion = self._safe_discussion(p, phase="白天")
                self.logger.write("discussion", {"speaker": p.name, **discussion.model_dump()})
                msg = Msg(name=p.name, content=discussion.speech, role="assistant")
                try:
                    await self._fanout(alive_names, msg)
                except Exception as exc:
                    self.logger.write("error", {"where": "fanout", "speaker": p.name, "error": str(exc)})

            votes = self._day_vote()
            for voter, vote in zip(self._alive(), votes):
                self.logger.write("vote", {"voter": voter.name, **vote.model_dump()})

            tally: dict[str, int] = {}
            for v in votes:
                tally[v.target] = tally.get(v.target, 0) + 1
            if not tally:
                self.logger.write("error", {"where": "day_vote", "error": "no votes generated"})
                result = self._win_check()
                if result:
                    self.logger.write("game_end", {"day": self.day, "winner": result})
                    return {"winner": result, "log_path": str(self.logger.path)}
                self.day += 1
                continue
            out_name = self._pick_by_tally(tally, "day_vote")
            self._eliminate(out_name, "白天公投")

            result = self._win_check()
            if result:
                self.logger.write("game_end", {"day": self.day, "winner": result})
                return {"winner": result, "log_path": str(self.logger.path)}

            self.day += 1

        self.logger.write("game_end", {"day": self.day, "winner": "达到最大天数，按剩余人数判定平衡结束"})
        return {"winner": "平衡结束", "log_path": str(self.logger.path)}
