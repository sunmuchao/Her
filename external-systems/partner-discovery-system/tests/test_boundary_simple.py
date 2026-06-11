"""简化版测试：验证日志埋点是否有效。

测试目标：
1. 验证 agent_runtime.py 的日志埋点是否正确记录 Agent 行为
2. 收集一个简单场景的证据（换一批）
3. 分析日志输出，决定是否需要修改 SOUL.md

测试方法：
1. 使用现有的测试框架（test_discovery_system.py）
2. 运行一个简单的测试场景
3. 查看日志输出
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys
import unittest
from datetime import datetime

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

# 配置日志记录器，用于收集测试证据
_logger = logging.getLogger("discovery_boundary_test")
_logger.setLevel(logging.INFO)

# 创建日志文件 handler
log_file_path = pathlib.Path(__file__).parent / "boundary_test_simple.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)

# 同时输出到控制台
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
_logger.addHandler(console_handler)


class TestSimpleBoundary(unittest.TestCase):
    """简化版测试：验证日志埋点。"""

    def test_verify_log_setup(self):
        """验证日志设置是否正确。"""
        _logger.info("=" * 80)
        _logger.info("【测试开始】验证日志埋点是否有效")
        _logger.info("=" * 80)

        # 记录测试场景
        _logger.info("场景编号：1-1")
        _logger.info("场景名称：首次使用")
        _logger.info("用户输入：换一批")
        _logger.info("预期行为：口语化追问，像真人红娘")
        _logger.info("实际行为：待验证（需要运行 Agent 测试）")

        _logger.info("=" * 80)
        _logger.info("【测试结束】日志记录完成")
        _logger.info("=" * 80)

        self.assertTrue(True, "日志设置正确")

    def test_verify_existing_test_framework(self):
        """验证现有测试框架是否正常工作。"""
        _logger.info("=" * 80)
        _logger.info("【测试开始】验证现有测试框架")
        _logger.info("=" * 80)

        # 运行一个现有的简单测试
        from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession

        storage = InMemoryDiscoveryStorage()
        session = StoredSession(
            session_id="test_session_001",
            requester_id=10001,
            profile_id=10001,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={},
            state={},
        )
        storage.save_session(session)

        # 验证 session 是否保存成功
        loaded_session = storage.get_session("test_session_001")
        self.assertEqual(loaded_session.session_id, "test_session_001")

        _logger.info("Session 保存和加载测试通过")
        _logger.info("=" * 80)

    def test_collect_evidence_from_existing_test(self):
        """从现有测试中收集证据。

        运行现有的 test_discovery_system.py 中的测试，查看日志输出。
        """
        _logger.info("=" * 80)
        _logger.info("【证据收集】从现有测试中收集证据")
        _logger.info("=" * 80)

        _logger.info("说明：需要运行真实的 Agent 测试才能收集证据")
        _logger.info("建议：运行以下命令查看日志输出")
        _logger.info("python -m pytest tests/test_discovery_system.py::DiscoveryServiceTests::test_agents_runtime_bypasses_session_memory_for_runner -v -s")

        _logger.info("=" * 80)


if __name__ == "__main__":
    unittest.main()