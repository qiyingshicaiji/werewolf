from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .game import SanguoWerewolfGame
from .logger import RunLogger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="三国狼人杀 AgentScope Demo")
    parser.add_argument("--config", default="config/game.example.yaml", help="配置文件路径")
    parser.add_argument("--mode", choices=["simulate", "llm"], default=None, help="运行模式")
    parser.add_argument("--max-days", type=int, default=None, help="最大天数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--logs-dir", default="logs", help="日志目录")
    return parser.parse_args()


async def _run(config_path: str, mode: str | None, max_days: int | None, seed: int, logs_dir: str) -> dict:
    load_dotenv()
    cfg = load_config(config_path)
    if mode:
        cfg.game.mode = mode
    if max_days is not None:
        cfg.game.max_days = max_days

    logger = RunLogger.create(logs_dir=logs_dir)
    game = SanguoWerewolfGame(config=cfg, logger=logger, seed=seed)
    result = await game.run()
    return {
        "winner": result["winner"],
        "log_path": result["log_path"],
        "config": Path(config_path).as_posix(),
        "mode": cfg.game.mode,
    }


def main() -> None:
    args = parse_args()
    result = asyncio.run(_run(args.config, args.mode, args.max_days, args.seed, args.logs_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
