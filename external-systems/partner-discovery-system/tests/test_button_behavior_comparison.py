"""对比测试：验证"换一批"和"看看其他人"都属于重新搜人语义。"""

from __future__ import annotations

import pathlib
import sys
import unittest

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system import agent_runtime  # noqa: E402


class TestButtonBehaviorComparison(unittest.TestCase):
    """验证按钮语义与工具契约一致。"""

    def test_search_tool_description_covers_batch_refresh_and_see_others(self) -> None:
        source = pathlib.Path(agent_runtime.__file__).read_text(encoding="utf-8")

        self.assertIn('用户想"换一批 / 看别的 / 再看看别人 / 不要刚才那批"', source)
        self.assertIn("exclude_current_results", source)

    def test_show_more_candidates_is_only_ui_action_not_search_contract(self) -> None:
        source = pathlib.Path(
            DISCOVERY_ROOT / "discovery_system" / "decision_models.py"
        ).read_text(encoding="utf-8")

        self.assertIn("统一使用 show_more_candidates", source)
        self.assertIn("exclude_current_results", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
