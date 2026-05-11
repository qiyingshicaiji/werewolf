import asyncio
import unittest

from werewolf.config import load_config
from werewolf.game import SanguoWerewolfGame
from werewolf.logger import RunLogger


class GameRunTests(unittest.TestCase):
    def test_simulated_game_runs(self):
        cfg = load_config("config/game.example.yaml")
        cfg.game.max_days = 1
        logger = RunLogger.create("logs")
        game = SanguoWerewolfGame(cfg, logger, seed=1)
        result = asyncio.run(game.run())
        self.assertIn("winner", result)
        self.assertTrue(logger.path.exists())


if __name__ == "__main__":
    unittest.main()
