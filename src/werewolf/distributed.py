"""Distributed execution hooks (reserved for future use).

Current implementation is a placeholder. To enable real distributed execution:
1. Replace run_map with an actual executor (Ray actor / Celery worker).
2. Use a shared message bus (Redis / Kafka) for cross-worker communication.
3. Declare workers in the config and map players to workers.
"""

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
    """Execute items through the configured distributed backend.

    Currently all backends run locally. Reserved for future multiprocess /
    remote execution support.
    """
    return list(items)
