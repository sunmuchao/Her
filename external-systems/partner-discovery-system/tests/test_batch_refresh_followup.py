"""验证"换一批"相关规则位于工具契约，而不是固定追问模板。"""

from __future__ import annotations

import pathlib
import sys
import unittest

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))


class TestBatchRefreshFollowupQuestion(unittest.TestCase):
    """验证换一批场景的当前设计约束。"""

    def test_search_tool_description_does_not_require_followup_as_only_path(self) -> None:
        content = (DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py").read_text(encoding="utf-8")

        self.assertIn('不要假设系统会自动理解"换一批"', content)
        self.assertIn("exclude_current_results", content)
        self.assertNotIn('每次换一批都追问', content)

    def test_refresh_semantics_are_expressed_by_search_param(self) -> None:
        content = (DISCOVERY_ROOT / "discovery_system" / "service_integrations.py").read_text(encoding="utf-8")

        self.assertIn("exclude_current_results: bool = False", content)
        self.assertIn("last_shown_candidate_ids", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
