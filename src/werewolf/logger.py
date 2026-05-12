from __future__ import annotations

import json
import atexit
from datetime import datetime
from pathlib import Path
from typing import Any


class RunLogger:
    """JSON-lines logger with buffered writes.

    Writes to a .jsonl file. After the game ends, call write_readable_log()
    to generate a human-readable .txt version from the log data.
    """

    def __init__(self, path: Path, flush_interval: int = 1) -> None:
        self.path = path
        self._flush_interval = flush_interval
        self._buffer: list[str] = []
        self._write_count = 0
        self._fp = path.open("a", encoding="utf-8")
        atexit.register(self.close)

    @classmethod
    def create(cls, logs_dir: str = "logs") -> "RunLogger":
        directory = Path(logs_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(path=directory / f"run_{stamp}.jsonl")

    def write(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": payload,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        self._buffer.append(line)
        self._write_count += 1
        if self._write_count >= self._flush_interval:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self._fp.writelines(self._buffer)
            self._fp.flush()
            self._buffer.clear()
            self._write_count = 0

    def close(self) -> None:
        self.flush()
        self._fp.close()

    @property
    def readable_path(self) -> Path:
        return self.path.with_suffix(".txt")
