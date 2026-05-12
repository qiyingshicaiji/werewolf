import unittest
import uuid
from pathlib import Path

from werewolf.config import load_config, resolve_config_path
from werewolf.models import (
    DiscussionModelCN,
    VoteModelCN,
    WerewolfKillModelCN,
    WitchActionModelCN,
)


class ConfigModelTests(unittest.TestCase):
    def test_load_config(self):
        cfg = load_config("config/game.example.yaml")
        self.assertGreaterEqual(len(cfg.players), 5)
        self.assertEqual(cfg.game.max_days, 3)

    def test_resolve_config_path(self):
        path = resolve_config_path("game.example.yaml")
        self.assertTrue(path.exists())
        self.assertIn("config", str(path))

    def test_resolve_config_path_rejects_escape(self):
        with self.assertRaises(ValueError):
            resolve_config_path("../secrets/config.yaml")

    def test_structured_models(self):
        discussion = DiscussionModelCN(speech="发言", strategy="策略")
        vote = VoteModelCN(target="玩家2", reason="可疑")
        kill = WerewolfKillModelCN(target="玩家1", reason="测试")
        self.assertEqual(discussion.speech, "发言")
        self.assertEqual(vote.target, "玩家2")
        self.assertEqual(kill.target, "玩家1")

    def test_witch_model_save_requires_target(self):
        with self.assertRaises(ValueError):
            WitchActionModelCN(action="save", reason="想救人，但没指定目标")

    def test_witch_model_poison_requires_target(self):
        with self.assertRaises(ValueError):
            WitchActionModelCN(action="poison", reason="想毒人，但没指定目标")

    def test_witch_model_pass_rejects_target(self):
        with self.assertRaises(ValueError):
            WitchActionModelCN(action="pass", target="玩家1", reason="pass不应有目标")

    def test_validate_roles(self):
        content = """
game:
  max_days: 2
players:
  - {name: A, role: werewolf, character: 曹操}
  - {name: B, role: villager, character: 关羽}
  - {name: C, role: villager, character: 赵云}
  - {name: D, role: villager, character: 孙尚香}
  - {name: E, role: villager, character: 刘备}
"""
        config_dir = Path("config")
        temp_path = config_dir / f"test_missing_seer_{uuid.uuid4().hex}.yaml"
        temp_path.write_text(content, encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                load_config(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
