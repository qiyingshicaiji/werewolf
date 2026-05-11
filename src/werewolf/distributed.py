from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeVar

T = TypeVar("T")


@dataclass
class DistributedHook:
    backend: str
    worker_ids: list[str]

    def describe(self) -> str:
        if not self.worker_ids:
            return f"backend={self.backend}, workers=local-single"
        return f"backend={self.backend}, workers={','.join(self.worker_ids)}"


def run_map(items: Iterable[T], hook: DistributedHook) -> list[T]:
    """Simulated distributed execution hook.

    - simulated: run in current process, keeping interface stable.
    - local_multiprocess / remote_stub: reserved for future executors.
    """

    if hook.backend == "simulated":
        return list(items)
    return list(items)
