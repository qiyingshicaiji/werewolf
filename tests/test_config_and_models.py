from pathlib import Path
import tempfile
import unittest

from werewolf.config import load_config
from werewolf.models import DiscussionModelCN, VoteModelCN


class ConfigModelTests(unittest.TestCase):
    def test_load_config(self):
        cfg = load_config("config/game.example.yaml")
        self.assertGreaterEqual(len(cfg.players), 5)
        self.assertEqual(cfg.game.max_days, 3)

    def test_structured_models(self):
        discussion = DiscussionModelCN(speech="发言", strategy="策略")
        vote = VoteModelCN(target="玩家2", reason="可疑")
        self.assertEqual(discussion.speech, "发言")
        self.assertEqual(vote.target, "玩家2")

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
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=Path.cwd(), delete=False, encoding="utf-8") as fp:
            fp.write(content)
            temp_path = Path(fp.name)
        try:
            with self.assertRaises(ValueError):
                load_config(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
