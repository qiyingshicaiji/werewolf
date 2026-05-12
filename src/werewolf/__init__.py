"""三国狼人杀 AgentScope project package."""

from .agent import WerewolfAgent
from .config import load_config, resolve_config_path
from .game import SanguoWerewolfGame
from .logger import RunLogger
from .main import main
from .models import (
    DiscussionModelCN,
    SeerCheckModelCN,
    VoteModelCN,
    WerewolfKillModelCN,
    WitchActionModelCN,
)

__all__ = [
    "main",
    "load_config",
    "resolve_config_path",
    "RunLogger",
    "SanguoWerewolfGame",
    "WerewolfAgent",
    "DiscussionModelCN",
    "SeerCheckModelCN",
    "VoteModelCN",
    "WerewolfKillModelCN",
    "WitchActionModelCN",
]
