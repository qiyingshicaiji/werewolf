import asyncio
import unittest

from werewolf.agent import WerewolfAgent
from werewolf.config import load_config
from werewolf.game import SanguoWerewolfGame
from werewolf.logger import RunLogger


class GameRunTests(unittest.TestCase):
    def test_simulated_game_runs(self):
        cfg = load_config("config/game.example.yaml")
        cfg.game.max_days = 1
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            result = asyncio.run(game.run())
            self.assertIn("winner", result)
            self.assertTrue(logger.path.exists())
        finally:
            logger.close()

    def test_agent_construction(self):
        """Test that agents can be constructed for all player configs."""
        cfg = load_config("config/game.example.yaml")
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            game.agents = game._init_agents()
            self.assertEqual(len(game.agents), len(cfg.players))
            for agent in game.agents.values():
                self.assertIsInstance(agent, WerewolfAgent)
                self.assertTrue(agent.alive)
        finally:
            logger.close()

    def test_win_check_good_wins(self):
        """好人阵营获胜：所有狼人被消灭"""
        cfg = load_config("config/game.example.yaml")
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            game.agents = game._init_agents()
            for agent in game.agents.values():
                if agent.role == "werewolf":
                    agent.alive = False
            result = game._win_check()
            self.assertEqual(result, "好人阵营获胜")
        finally:
            logger.close()

    def test_win_check_werewolves_win(self):
        """狼人阵营获胜：狼人数 >= 好人数"""
        cfg = load_config("config/game.example.yaml")
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            game.agents = game._init_agents()
            for agent in game.agents.values():
                if agent.role != "werewolf":
                    agent.alive = False
                else:
                    agent.alive = True
            result = game._win_check()
            self.assertEqual(result, "狼人阵营获胜")
        finally:
            logger.close()

    def test_sim_seer_check_returns_result(self):
        cfg = load_config("config/game.example.yaml")
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            game.agents = game._init_agents()
            result = game._sim_seer_check()
            self.assertIsNotNone(result)
            self.assertTrue(result.target)
        finally:
            logger.close()

    def test_sim_witch_action(self):
        cfg = load_config("config/game.example.yaml")
        logger = RunLogger.create("logs")
        try:
            game = SanguoWerewolfGame(cfg, logger, seed=1)
            game.agents = game._init_agents()
            result = game._sim_witch_action("玩家1")
            self.assertIsNotNone(result)
            self.assertIn(result.action, ("save", "poison", "pass"))
        finally:
            logger.close()


if __name__ == "__main__":
    unittest.main()
