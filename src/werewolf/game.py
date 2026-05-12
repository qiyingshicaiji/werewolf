from __future__ import annotations

import asyncio
import os
import random
from typing import Any

from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.pipeline import MsgHub, fanout_pipeline

from .agent import WerewolfAgent
from .config import ModelConfig, ProjectConfig
from .logger import RunLogger
from .models import (
    GamePhase,
    SeerCheckModelCN,
    VoteModelCN,
    WerewolfKillModelCN,
    WitchActionModelCN,
)


class SanguoWerewolfGame:
    def __init__(self, config: ProjectConfig, logger: RunLogger, seed: int = 42) -> None:
        self.config = config
        self.logger = logger
        self.rng = random.Random(seed)
        self.model: OpenAIChatModel | None = None
        self.agents: dict[str, WerewolfAgent] = {}
        self.witch_has_antidote = True
        self.witch_has_poison = True
        self.day = 1
        self._seer_results: dict[str, bool] = {}

    def _init_model(self, model_cfg: ModelConfig) -> OpenAIChatModel:
        api_key = os.getenv(model_cfg.api_key_env, "")
        client_kwargs = {}
        if model_cfg.base_url:
            client_kwargs["base_url"] = model_cfg.base_url
        return OpenAIChatModel(
            model_name=model_cfg.model_name,
            api_key=api_key,
            stream=False,
            client_kwargs=client_kwargs,
            generate_kwargs={"temperature": model_cfg.temperature},
        )

    def _init_agents(self) -> dict[str, WerewolfAgent]:
        agents = {}
        for p in self.config.players:
            agent = WerewolfAgent(
                name=p.name,
                role=p.role,
                character=p.character,
                model=self.model,
                rng=self.rng,
            )
            agents[p.name] = agent
        return agents

    def _alive(self, role: str | None = None) -> list[WerewolfAgent]:
        agents = [a for a in self.agents.values() if a.alive]
        if role is None:
            return agents
        return [a for a in agents if a.role == role]

    def _alive_names(self) -> list[str]:
        return [a.name for a in self._alive()]

    def _game_context(self) -> list[dict]:
        """Build context about current game state for agents."""
        ctx: list[dict] = [
            {"role": "system", "content": f"第{self.day}天。当前存活玩家：" + ", ".join(self._alive_names())},
        ]
        for a in self._alive():
            ctx.append({
                "role": "system",
                "content": f"玩家【{a.name}】存活。",
                "name": a.name,
            })
        return ctx

    def _eliminate(self, name: str, reason: str) -> None:
        agent = self.agents.get(name)
        if agent and agent.alive:
            agent.alive = False
            self.logger.write("eliminate", {"name": name, "reason": reason})

    def _win_check(self) -> str | None:
        wolves = self._alive("werewolf")
        good = [a for a in self._alive() if a.role != "werewolf"]
        if not wolves:
            return "好人阵营获胜"
        if len(wolves) >= len(good):
            return "狼人阵营获胜"
        return None

    def _pick_by_tally(self, tally: dict[str, int], reason: str) -> str:
        if not tally:
            return ""
        highest = max(tally.values())
        candidates = [name for name, score in tally.items() if score == highest]
        winner = self.rng.choice(candidates)
        if len(candidates) > 1:
            self.logger.write("tie_break", {"reason": reason, "candidates": candidates, "chosen": winner})
        return winner

    # ---- Simulate mode (random) ----

    def _sim_discussion(self, agent: WerewolfAgent, phase: str) -> Msg:
        speech = f"{agent.character}表示：{phase}阶段我会谨慎判断，维护己方利益。"
        return Msg(name=agent.name, content=speech, role="assistant")

    def _sim_werewolf_kill(self) -> WerewolfKillModelCN:
        villagers = [a for a in self._alive() if a.role != "werewolf"]
        if not villagers:
            return WerewolfKillModelCN(target="", reason="无可击杀目标")
        target = self.rng.choice(villagers)
        return WerewolfKillModelCN(target=target.name, reason="优先打击高威胁角色")

    def _sim_seer_check(self) -> SeerCheckModelCN | None:
        seers = self._alive("seer")
        if not seers:
            return None
        candidates = [a for a in self._alive() if a.role != "seer"]
        if not candidates:
            return None
        target = self.rng.choice(candidates)
        return SeerCheckModelCN(target=target.name, reason="查验可疑对象")

    def _sim_witch_action(self, werewolf_target: str | None) -> WitchActionModelCN | None:
        witches = self._alive("witch")
        if not witches:
            return None
        if werewolf_target and self.witch_has_antidote and self.rng.random() < 0.3:
            self.witch_has_antidote = False
            return WitchActionModelCN(action="save", target=werewolf_target, reason="判断该玩家不该出局")
        alive_non_witch = [a for a in self._alive() if a.role != "witch"]
        if self.witch_has_poison and alive_non_witch and self.rng.random() < 0.15:
            self.witch_has_poison = False
            poison_target = self.rng.choice(alive_non_witch)
            return WitchActionModelCN(action="poison", target=poison_target.name, reason="压制潜在威胁")
        return WitchActionModelCN(action="pass", reason="保留药剂")

    def _sim_vote(self, voters: list[WerewolfAgent]) -> list[VoteModelCN]:
        votes = []
        for voter in voters:
            candidates = [a for a in self._alive() if a.name != voter.name]
            if candidates:
                target = self.rng.choice(candidates)
                votes.append(VoteModelCN(target=target.name, reason=f"{voter.character}认为其可疑"))
        return votes

    # ---- LLM mode ----

    async def _llm_werewolf_phase(self) -> WerewolfKillModelCN:
        wolves = self._alive("werewolf")
        if not wolves:
            return WerewolfKillModelCN(target="", reason="无狼人存活")

        # Wolf discussion via MsgHub
        context = self._game_context()
        for a in self._alive():
            context.append({"role": "system", "content": f"狼人杀身份提示：{a.name}是{a.role}。", "name": a.name, "role": a.role})

        async with MsgHub(participants=wolves, enable_auto_broadcast=True, name="wolf_den"):
            for wolf in wolves:
                prompt = Msg(
                    name="game_master",
                    content=f"狼人密谈阶段：你是狼人同伴之一。请与其他狼人商议今晚要击杀的目标。当前存活玩家（非狼人）：" + ", ".join(
                        a.name for a in self._alive() if a.role != "werewolf"
                    ),
                    role="user",
                )
                discussion = await wolf.discuss("狼人密谈", context)
                self.logger.write("werewolf_discussion", {"speaker": wolf.name, **discussion.model_dump()})
                speech_msg = Msg(name=wolf.name, content=discussion.speech, role="assistant")
                # MsgHub auto-broadcasts when agent is called, but here we need manual broadcast
                for other in wolves:
                    if other.name != wolf.name:
                        other.observe(speech_msg)

        # Wolf vote
        context = self._game_context()
        tasks = [wolf.werewolf_vote(context) for wolf in wolves]
        votes: list[VoteModelCN] = list(await asyncio.gather(*tasks))

        for wolf, vote in zip(wolves, votes):
            self.logger.write("werewolf_vote", {"voter": wolf.name, **vote.model_dump()})

        tally: dict[str, int] = {}
        for v in votes:
            if v.target:
                tally[v.target] = tally.get(v.target, 0) + 1
        if not tally:
            return WerewolfKillModelCN(target="", reason="未达成一致")
        target = self._pick_by_tally(tally, "werewolf_vote")
        return WerewolfKillModelCN(target=target, reason="狼人团队投票结果")

    async def _llm_seer_check(self) -> SeerCheckModelCN | None:
        seers = self._alive("seer")
        if not seers:
            return None
        seer = seers[0]
        context = self._game_context()
        for a in self._alive():
            checked = self._seer_results.get(a.name)
            if checked is not None:
                context.append({
                    "role": "system",
                    "content": f"你之前查验过【{a.name}】，结果是{'狼人' if checked else '好人'}。",
                })
        result = await seer.seer_check(context)
        return result

    async def _llm_witch_action(self, werewolf_target: str | None) -> WitchActionModelCN | None:
        witches = self._alive("witch")
        if not witches:
            return None
        witch = witches[0]
        context = self._game_context()
        context.append({
            "role": "system",
            "content": f"解药状态：{'可用' if self.witch_has_antidote else '已使用'}。毒药状态：{'可用' if self.witch_has_poison else '已使用'}。",
        })
        result = await witch.witch_decide(werewolf_target, context)
        if result.action == "save" and self.witch_has_antidote:
            self.witch_has_antidote = False
        elif result.action == "poison" and self.witch_has_poison:
            self.witch_has_poison = False
        return result

    async def _llm_day_discussion(self) -> None:
        alive = self._alive()
        alive_names = self._alive_names()
        context = self._game_context()

        async with MsgHub(participants=alive, enable_auto_broadcast=True, name="day_court"):
            for agent in alive:
                prompt = Msg(
                    name="game_master",
                    content=(
                        f"白天讨论阶段：请根据你的身份和之前的游戏事件发表你的看法。"
                        f"当前存活玩家：{', '.join(alive_names)}。"
                        f"今天是第{self.day}天。"
                    ),
                    role="user",
                )
                try:
                    discussion = await agent.discuss("白天讨论", context)
                    self.logger.write("discussion", {"speaker": agent.name, **discussion.model_dump()})
                    for other in alive:
                        if other.name != agent.name:
                            other.observe(Msg(name=agent.name, content=discussion.speech, role="assistant"))
                    context.append({"role": "assistant", "content": f"{agent.name}: {discussion.speech}"})
                except Exception as exc:
                    self.logger.write("error", {"where": "day_discussion", "speaker": agent.name, "error": str(exc)})

    async def _llm_day_vote(self) -> list[VoteModelCN]:
        alive = self._alive()
        context = self._game_context()
        tasks = [agent.vote(context) for agent in alive]
        return list(await asyncio.gather(*tasks))

    # ---- Main game loop ----

    async def run(self) -> dict[str, Any]:
        # Initialize
        if self.config.game.mode == "llm":
            self.model = self._init_model(self.config.model)
        self.agents = self._init_agents()

        self.logger.write("game_start", {
            "players": [{"name": p.name, "role": p.role, "character": p.character} for p in self.config.players],
            "mode": self.config.game.mode,
        })

        use_llm = self.config.game.mode == "llm"

        while self.day <= self.config.game.max_days:
            self.logger.write("phase", {"day": self.day, "name": "night"})

            # ---- Night: Werewolf ----
            if use_llm:
                werewolf_action = await self._llm_werewolf_phase()
            else:
                werewolf_action = self._sim_werewolf_kill()
            self.logger.write("werewolf_kill", werewolf_action.model_dump())

            # ---- Night: Seer ----
            if use_llm:
                seer_action = await self._llm_seer_check()
            else:
                seer_action = self._sim_seer_check()

            if seer_action:
                checked_agent = self.agents.get(seer_action.target)
                check_result = checked_agent.role == "werewolf" if checked_agent else None
                if check_result is not None:
                    self._seer_results[seer_action.target] = check_result
                self.logger.write("seer_check", {
                    **seer_action.model_dump(),
                    "result": "werewolf" if check_result else "not_werewolf" if check_result is False else "unknown",
                })

            # ---- Night: Witch ----
            if use_llm:
                witch_action = await self._llm_witch_action(werewolf_action.target)
            else:
                witch_action = self._sim_witch_action(werewolf_action.target)

            if witch_action:
                self.logger.write("witch_action", witch_action.model_dump())

            # ---- Resolve night ----
            killed_tonight = werewolf_action.target
            if witch_action and witch_action.action == "save" and witch_action.target == killed_tonight:
                self.logger.write("witch_save", {"saved": killed_tonight})
                killed_tonight = None
            if witch_action and witch_action.action == "poison" and witch_action.target:
                self._eliminate(witch_action.target, "女巫毒杀")
            if killed_tonight:
                self._eliminate(killed_tonight, "狼人击杀")

            result = self._win_check()
            if result:
                self.logger.write("game_end", {"day": self.day, "winner": result})
                return {"winner": result, "log_path": str(self.logger.path)}

            # ---- Day: Discussion ----
            self.logger.write("phase", {"day": self.day, "name": "day"})

            if use_llm:
                await self._llm_day_discussion()
            else:
                for agent in self._alive():
                    msg = self._sim_discussion(agent, "白天")
                    self.logger.write("discussion", {"speaker": agent.name, "content": msg.content})

            # ---- Day: Vote ----
            if use_llm:
                votes = await self._llm_day_vote()
            else:
                votes = self._sim_vote(self._alive())

            for voter, vote in zip(self._alive(), votes):
                self.logger.write("vote", {"voter": voter.name, **vote.model_dump()})

            tally: dict[str, int] = {}
            for v in votes:
                if v.target:
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
