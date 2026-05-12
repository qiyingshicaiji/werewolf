"""Human-readable log formatter for werewolf game events.

Converts JSON log entries into structured, readable Chinese text sections
suitable for console output or Streamlit display.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROLE_LABELS: dict[str, str] = {
    "werewolf": "🐺 狼人",
    "seer": "🔮 预言家",
    "witch": "🧪 女巫",
    "villager": "👤 村民",
}

PHASE_LABELS: dict[str, str] = {
    "night": "🌙夜晚",
    "day": "☀️白天",
}


def _role_label_ascii(role: str) -> str:
    return {"werewolf": "[狼人]", "seer": "[预言家]", "witch": "[女巫]", "villager": "[村民]"}.get(role, role)


def _strip_emoji(text: str) -> str:
    """Remove emoji and special symbol characters for terminal compatibility."""
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        # ASCII printable
        if cp < 128:
            result.append(ch)
        # Box drawing (U+2500-257F)
        elif 0x2500 <= cp <= 0x257F:
            result.append(ch)
        # CJK Unified (U+4E00-9FFF), CJK Symbols (U+3000-303F)
        elif 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
            result.append(ch)
        # Fullwidth forms (U+FF00-FFEF) and halfwidth katakana
        elif 0xFF00 <= cp <= 0xFFEF:
            result.append(ch)
        # CJK Compatibility (U+3300-33FF)
        elif 0x3300 <= cp <= 0x33FF:
            result.append(ch)
        # General punctuation (U+2000-206F) — includes en/em dash, bullets
        elif 0x2000 <= cp <= 0x206F:
            result.append(ch)
        # Latin-1 supplement (U+00A0-00FF) for common symbols like ...
        elif 0x00A0 <= cp <= 0x00FF:
            result.append(ch)
        # Skip emoji, misc symbols, and other wide characters
        else:
            pass
    return "".join(result)


@dataclass
class PlayerInfo:
    name: str
    role: str
    character: str
    alive: bool = True


@dataclass
class GamePhase:
    day: int
    name: str


@dataclass
class FormattedEvent:
    event_type: str
    time: str
    text: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DaySection:
    day: int
    events: list[FormattedEvent] = field(default_factory=list)


class LogFormatter:
    """Converts raw JSON log entries into structured human-readable sections."""

    def __init__(self, log_path: str | Path | None = None, raw_lines: list[str] | None = None):
        self.entries: list[dict] = []
        self.sections: list[DaySection] = []
        self.players: list[PlayerInfo] = []
        self.winner: str = ""
        self.mode: str = "simulate"

        if log_path:
            self._load(Path(log_path))
        elif raw_lines:
            self._parse_lines(raw_lines)

    def _load(self, path: Path) -> None:
        if path.exists():
            self._parse_lines(path.read_text(encoding="utf-8").strip().split("\n"))

    def _parse_lines(self, lines: list[str]) -> None:
        self.entries = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                self.entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._build()

    def _find_player(self, name: str) -> PlayerInfo | None:
        for p in self.players:
            if p.name == name:
                return p
        return None

    def _build(self) -> None:
        """Parse entries into day-based sections."""
        current_day = 1
        current_section = DaySection(day=1)
        self.sections = [current_section]

        for entry in self.entries:
            event = entry.get("event", "")
            payload = entry.get("payload", {})
            time = entry.get("time", "")

            if event == "game_start":
                self._handle_game_start(payload)
                continue
            elif event == "game_end":
                self.winner = payload.get("winner", "")
                continue

            # Detect day transitions
            if event == "phase":
                day = payload.get("day", 1)
                if day != current_day:
                    current_day = day
                    current_section = DaySection(day=day)
                    self.sections.append(current_section)

            formatted = self._format_event(event, payload, time)
            if formatted:
                current_section.events.append(formatted)

            # Track eliminations
            if event == "eliminate":
                player = self._find_player(payload.get("name", ""))
                if player:
                    player.alive = False

    def _handle_game_start(self, payload: dict) -> None:
        self.players = [
            PlayerInfo(name=p["name"], role=p["role"], character=p["character"])
            for p in payload.get("players", [])
        ]
        self.mode = payload.get("mode", "simulate")

    def _format_event(self, event: str, payload: dict, time: str) -> FormattedEvent | None:
        handler = getattr(self, f"_fmt_{event}", None)
        if handler:
            text, detail = handler(payload)
            return FormattedEvent(event_type=event, time=time, text=text, detail=detail)
        return None

    # ---- Event formatters ----

    def _fmt_phase(self, p: dict) -> tuple[str, dict]:
        day = p.get("day", "?")
        name = p.get("name", "")
        label = PHASE_LABELS.get(name, name)
        return f"进入 第{day}天 {label}", {"day": day, "phase": name}

    def _fmt_werewolf_discussion(self, p: dict) -> tuple[str, dict]:
        speaker = p.get("speaker", "?")
        speech = p.get("speech", "")
        strategy = p.get("strategy", "")
        player = self._find_player(speaker)
        char = f"（{player.character}）" if player else ""
        return (
            f"🐺 狼人密谈 | {speaker}{char}：{speech}",
            {"speaker": speaker, "speech": speech, "strategy": strategy, "icon": "🐺"},
        )

    def _fmt_werewolf_vote(self, p: dict) -> tuple[str, dict]:
        voter = p.get("voter", "?")
        target = p.get("target", "?")
        reason = p.get("reason", "")
        player = self._find_player(voter)
        char = f"（{player.character}）" if player else ""
        return (
            f"  投票击杀 → {target}（理由：{reason}）",
            {"voter": voter, "voter_char": char, "target": target, "reason": reason},
        )

    def _fmt_werewolf_kill(self, p: dict) -> tuple[str, dict]:
        target = p.get("target", "")
        reason = p.get("reason", "")
        return (
            f"⚔️ 狼人最终决定击杀【{target}】，理由：{reason}",
            {"target": target, "reason": reason, "icon": "⚔️"},
        )

    def _fmt_seer_check(self, p: dict) -> tuple[str, dict]:
        target = p.get("target", "")
        reason = p.get("reason", "")
        result = p.get("result", "unknown")
        if result == "werewolf":
            result_text = "🐺 是狼人！"
        elif result == "not_werewolf":
            result_text = "✅ 是好人"
        else:
            result_text = "❓ 未知"
        return (
            f"🔮 预言家查验【{target}】，结果：{result_text}（理由：{reason}）",
            {"target": target, "reason": reason, "result": result, "icon": "🔮"},
        )

    def _fmt_witch_action(self, p: dict) -> tuple[str, dict]:
        action = p.get("action", "pass")
        target = p.get("target", "")
        reason = p.get("reason", "")
        if action == "save":
            text = f"🧪 女巫使用解药，救活【{target}】（理由：{reason}）"
        elif action == "poison":
            text = f"🧪 女巫使用毒药，毒杀【{target}】（理由：{reason}）"
        else:
            text = "🧪 女巫未使用药剂"
        return text, {"action": action, "target": target, "reason": reason, "icon": "🧪"}

    def _fmt_witch_save(self, p: dict) -> tuple[str, dict]:
        saved = p.get("saved", "")
        return f"💚 女巫的解药生效，【{saved}】免于死亡", {"saved": saved, "icon": "💚"}

    def _fmt_eliminate(self, p: dict) -> tuple[str, dict]:
        name = p.get("name", "")
        reason = p.get("reason", "")
        player = self._find_player(name)
        role_label = f"（{ROLE_LABELS.get(player.role, player.role)}）" if player else ""
        return (
            f"💀 【{name}】{role_label}被淘汰 — {reason}",
            {"name": name, "role": player.role if player else "?", "reason": reason, "icon": "💀"},
        )

    def _fmt_discussion(self, p: dict) -> tuple[str, dict]:
        speaker = p.get("speaker", "?")
        speech = p.get("speech", p.get("content", ""))
        player = self._find_player(speaker)
        char = f"（{player.character}）" if player else ""
        return (
            f"💬 {speaker}{char}：{speech}",
            {"speaker": speaker, "speech": speech, "icon": "💬"},
        )

    def _fmt_vote(self, p: dict) -> tuple[str, dict]:
        voter = p.get("voter", "?")
        target = p.get("target", "?")
        reason = p.get("reason", "")
        player = self._find_player(voter)
        char = f"（{player.character}）" if player else ""
        return (
            f"🗳️ {voter}{char} → 投票给【{target}】（理由：{reason}）",
            {"voter": voter, "target": target, "reason": reason, "icon": "🗳️"},
        )

    def _fmt_tie_break(self, p: dict) -> tuple[str, dict]:
        reason = p.get("reason", "")
        candidates = p.get("candidates", [])
        chosen = p.get("chosen", "")
        return (
            f"⚖️ 平票！候选：{', '.join(candidates)} → 随机选择：【{chosen}】",
            {"candidates": candidates, "chosen": chosen, "icon": "⚖️"},
        )

    def _fmt_error(self, p: dict) -> tuple[str, dict]:
        where = p.get("where", "")
        error = p.get("error", "")
        return f"⚠️ 错误 [{where}]：{error}", {"where": where, "error": error, "icon": "⚠️"}

    # ---- Output methods ----

    def render_text(self, ascii_only: bool = False) -> str:
        """Render the full game log as readable plain text.

        Args:
            ascii_only: If True, use ASCII-only borders and strip emoji.
        """
        lines: list[str] = []

        if ascii_only:
            h_line = "=" * 52
            s_line = "-" * 52
        else:
            h_line = "═" * 52
            s_line = "─" * 52

        lines.append(h_line)
        lines.append("  三国狼人杀 - AgentScope 对局回放")
        lines.append(h_line)
        lines.append("")

        # Player roster
        lines.append("[玩家阵容]")
        for p in self.players:
            label = _role_label_ascii(p.role) if ascii_only else ROLE_LABELS.get(p.role, p.role)
            lines.append(f"  {p.name} - {p.character} - {label}")
        lines.append("")

        # Day-by-day
        for section in self.sections:
            lines.append(s_line)
            lines.append(f" 第{section.day}天")
            lines.append(s_line)

            for evt in section.events:
                text = _strip_emoji(evt.text) if ascii_only else evt.text
                lines.append(text)

            # Vote tally for this day
            votes = [e for e in section.events if e.event_type == "vote"]
            if votes:
                tally: dict[str, list[str]] = {}
                for v in votes:
                    target = v.detail.get("target", "")
                    voter = v.detail.get("voter", "?")
                    tally.setdefault(target, []).append(voter)

                lines.append("")
                lines.append("  [投票统计]")
                for target, voters in sorted(tally.items(), key=lambda x: -len(x[1])):
                    lines.append(f"    {target}: {len(voters)}票 ({', '.join(voters)})")

            lines.append("")

        # Result
        lines.append(h_line)
        winner_text = f"[狼人] {self.winner}" if "狼人" in self.winner else f"[好人] {self.winner}"
        lines.append(f"  游戏结束: {winner_text}")
        lines.append(h_line)

        return "\n".join(lines)

    def render_html_sections(self) -> list[dict]:
        """Return structured sections for rich UI rendering.

        Each section is a dict with type and data suitable for Streamlit display.
        """
        sections: list[dict] = []

        # Player roster
        sections.append({
            "type": "roster",
            "players": [
                {
                    "name": p.name,
                    "character": p.character,
                    "role": ROLE_LABELS.get(p.role, p.role),
                    "role_raw": p.role,
                    "alive": p.alive,
                }
                for p in self.players
            ],
            "mode": self.mode,
        })

        # Day sections
        for section in self.sections:
            day_data: dict = {
                "type": "day",
                "day": section.day,
                "phase_events": [],  # phase headers
                "night_events": [],
                "day_events": [],
                "vote_tally": {},
            }

            current_phase = "night"
            for evt in section.events:
                if evt.event_type == "phase":
                    current_phase = evt.detail.get("phase", "night")
                    day_data["phase_events"].append(evt)
                elif current_phase == "night":
                    day_data["night_events"].append({
                        "type": evt.event_type,
                        "text": evt.text,
                        "detail": evt.detail,
                        "time": evt.time,
                    })
                else:
                    day_data["day_events"].append({
                        "type": evt.event_type,
                        "text": evt.text,
                        "detail": evt.detail,
                        "time": evt.time,
                    })

            # Vote tally
            votes = [e for e in section.events if e.event_type == "vote"]
            tally: dict[str, list[str]] = {}
            for v in votes:
                target = v.detail.get("target", "")
                voter = v.detail.get("voter", "?")
                tally.setdefault(target, []).append(voter)
            day_data["vote_tally"] = {
                target: {"count": len(voters), "voters": voters}
                for target, voters in sorted(tally.items(), key=lambda x: -len(x[1]))
            }

            sections.append(day_data)

        # Winner
        sections.append({
            "type": "result",
            "winner": self.winner,
            "winner_icon": "🐺" if "狼人" in self.winner else "🏘️",
        })

        return sections
