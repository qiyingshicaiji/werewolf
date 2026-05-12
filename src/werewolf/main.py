from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .game import SanguoWerewolfGame
from .log_formatter import LogFormatter
from .logger import RunLogger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="三国狼人杀 AgentScope Demo")
    parser.add_argument("--config", default="config/game.example.yaml", help="配置文件路径")
    parser.add_argument("--mode", choices=["simulate", "llm"], default=None, help="运行模式")
    parser.add_argument("--max-days", type=int, default=None, help="最大天数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--logs-dir", default="logs", help="日志目录")
    return parser.parse_args()


async def _run(
    config_path: str,
    mode: str | None,
    max_days: int | None,
    seed: int,
    logs_dir: str,
) -> dict:
    load_dotenv()
    cfg = load_config(config_path)
    if mode:
        cfg.game.mode = mode
    if max_days is not None:
        cfg.game.max_days = max_days

    logger = RunLogger.create(logs_dir=logs_dir)
    try:
        game = SanguoWerewolfGame(config=cfg, logger=logger, seed=seed)
        result = await game.run()
        readable_path = _write_readable_log(logger)
        return {
            "winner": result["winner"],
            "log_path": str(logger.path),
            "readable_log": str(readable_path),
            "config": Path(config_path).as_posix(),
            "mode": cfg.game.mode,
        }
    finally:
        logger.close()


def _write_readable_log(logger: RunLogger) -> Path:
    """Generate a human-readable .txt log from the JSON log."""
    formatter = LogFormatter(log_path=logger.path)
    text = formatter.render_text()
    readable_path = logger.readable_path
    readable_path.write_text(text, encoding="utf-8")
    return readable_path


def main() -> None:
    # Ensure UTF-8 output on Windows terminals
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = parse_args()
    result = asyncio.run(
        _run(args.config, args.mode, args.max_days, args.seed, args.logs_dir)
    )
    # Print the result
    log_path = result.get("log_path", "")
    if log_path and Path(log_path).exists():
        fmt = LogFormatter(log_path=Path(log_path))
        # Use ascii_only on Windows if stdout couldn't switch to utf-8
        ascii_only = sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8")
        print(fmt.render_text(ascii_only=ascii_only))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
