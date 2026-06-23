"""验证工具 description 是否包含关键使用规则。"""

from __future__ import annotations

import inspect
import pathlib
import sys
import unittest

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system import agent_runtime  # noqa: E402


class ToolDescriptionVerificationTests(unittest.TestCase):
    """验证工具 description 是否正确承载规则。"""

    def test_search_tool_description_contains_refresh_rules(self) -> None:
        source_code = inspect.getsource(agent_runtime)

        required_markers = [
            '这是"重新搜人"的唯一工具',
            '不要假设系统会自动理解"换一批"',
            'exclude_current_results',
            '用户想"换一批 / 看别的 / 再看看别人 / 不要刚才那批"',
            '用户只是追问当前候选人、解释推荐理由、比较现有候选人',
            '如果不传 true，你可能会再次拿到当前这批候选人',
        ]

        missing_markers = [marker for marker in required_markers if marker not in source_code]
        self.assertEqual(missing_markers, [], f"缺失的 search tool description 内容: {missing_markers}")

    def test_search_tool_description_covers_direct_user_message_refresh(self) -> None:
        source_code = inspect.getsource(agent_runtime)

        self.assertIn(
            '用户想"换一批 / 看别的 / 再看看别人 / 不要刚才那批"',
            source_code,
            "工具描述应覆盖用户直接文字表达的换人意图，而不只是按钮点击",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
