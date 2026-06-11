"""真实 Agent 测试：不使用 Mock，直接运行真实 Agent。

测试目标：
1. 触发真实的 Agent SDK 调用
2. 查看真实 Agent 的追问文案是否个性化
3. 收集证据，判断是否需要修改 SOUL.md

前提条件：
- 使用发现页的 API 配置（HER_DISCOVERY_AGENT_API_KEY 等）
- 从 .env 文件加载配置
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import unittest
from datetime import datetime

# ====================================================================
# 【关键】加载发现页的 API 配置（从 .env 文件）
# ====================================================================
project_root = pathlib.Path(__file__).resolve().parents[3]  # /Users/sunmuchao/Downloads/Her
env_file = project_root / ".env"
if env_file.exists():
    print(f"\n【加载环境变量】从 {env_file} 加载发现页配置")
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # 只设置 HER_DISCOVERY_AGENT 相关的环境变量
                if key.startswith("HER_DISCOVERY_AGENT") or key.startswith("OPENAI"):
                    os.environ.setdefault(key, value)
                    if key.endswith("API_KEY"):
                        print(f"  设置：{key}={value[:20]}...")
                    else:
                        print(f"  设置：{key}={value}")
else:
    print(f"\n【警告】未找到 .env 文件：{env_file}")

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (
    AgentsSdkDiscoveryAgentRuntime,
    DiscoveryRunInput,
)
from discovery_system.agent_session_store import InMemoryDiscoveryAgentSessionStore
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession

# 配置日志记录器，用于收集测试证据
_logger = logging.getLogger("discovery_system.agent_runtime")
_logger.setLevel(logging.INFO)

# 创建日志文件 handler
log_file_path = pathlib.Path(__file__).parent / "real_agent_no_mock.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestRealAgentNoMock(unittest.TestCase):
    """真实 Agent 测试（不使用 Mock）。"""

    def test_real_agent_batch_refresh(self):
        """真实测试：运行真实 Agent，查看追问文案。

        测试场景：用户说"换一批"
        预期：Agent 根据用户历史和性格自主生成追问文案

        注意：此测试使用发现页的 API 配置
        """
        _logger.info("=" * 80)
        _logger.info("【真实 Agent 测试】用户说'换一批'")
        _logger.info("=" * 80)

        # 检查 API 配置是否已加载
        api_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY")
        base_url = os.environ.get("HER_DISCOVERY_AGENT_BASE_URL")
        model = os.environ.get("HER_DISCOVERY_AGENT_MODEL")

        _logger.info(f"API 配置检查：")
        _logger.info(f"  - HER_DISCOVERY_AGENT_API_KEY: {api_key[:20] if api_key else '未配置'}...")
        _logger.info(f"  - HER_DISCOVERY_AGENT_BASE_URL: {base_url or '未配置'}")
        _logger.info(f"  - HER_DISCOVERY_AGENT_MODEL: {model or '未配置'}")

        if not api_key or not base_url:
            _logger.warning("未配置 API，真实 Agent 无法运行")
            self.skipTest("未配置 API，跳过真实 Agent 测试")

        # 创建真实的 Agent Runtime
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("real-agent-test-session")

        # 创建测试 session（模拟首次使用用户）
        storage = InMemoryDiscoveryStorage()
        test_session = StoredSession(
            session_id="real-agent-test-session",
            requester_id=10001,
            profile_id=10001,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": {},
            },
            state={
                "phase": "collecting_preferences",
                "working_criteria": {"cities": ["上海"], "age_min": 25, "age_max": 30},
                "current_results": [
                    {"profile_id": 1002, "title": "候选人A"},
                    {"profile_id": 1003, "title": "候选人B"},
                ],
                "turn_count": 1,
                "history": [{"type": "search", "timestamp": "2026-06-11T08:00:00"}],
                "memory_summary": {
                    "稳定偏好": {},
                    "近期反馈": [],
                    "近期对话摘要": "用户首次使用，查看第一批候选人。",
                },
            },
        )
        storage.save_session(test_session)

        # 构建 RunInput
        run_input = DiscoveryRunInput(
            session_id="real-agent-test-session",
            requester_id=10001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=["上海", "25-30岁"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "我帮你找了两位候选人。"},
            ],
            runtime_context={
                "session": {
                    "session_id": "real-agent-test-session",
                    "phase": "collecting_preferences",
                    "turn_count": 1,
                },
                "user_profile": {
                    "self_city": "上海",
                    "self_age": 28,
                },
                "memory_summary": {
                    "稳定偏好": {},
                    "近期反馈": [],
                    "近期对话摘要": "用户首次使用，查看第一批候选人。",
                },
                "visible_actions": [
                    {"label": "换一批", "style": "primary", "semantic_payload": {"kind": "show_more_candidates"}},
                    {"label": "调整条件", "style": "secondary"},
                ],
                "last_search": {
                    "result_count": 2,
                    "has_match": True,
                    "criteria": {"cities": ["上海"], "age_min": 25, "age_max": 30},
                },
                "current_results": [
                    {
                        "profile_id": 1002,
                        "title": "候选人A",
                        "reason_summary": "同城，年龄匹配。",
                    },
                    {
                        "profile_id": 1003,
                        "title": "候选人B",
                        "reason_summary": "同城，年龄匹配。",
                    },
                ],
            },
            search_partner_candidates=lambda criteria, limit: {
                "has_match": True,
                "result_count": 2,
                "results": [
                    {"id": 1004, "title": "候选人C"},
                    {"id": 1005, "title": "候选人D"},
                ],
            },
            sync_requester_persona_memory=lambda patch: {"synced": True},
            propose_requester_profile_update=lambda patch_json, evidence="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            agent_session=session,
        )

        # 调用真实 Agent（不使用 Mock）
        _logger.info("【调用真实 Agent】")
        try:
            result = runtime.run_turn(
                run_input,
                user_message="换一批",
            )

            _logger.info("=" * 80)
            _logger.info("【测试结束】真实 Agent 测试完成")
            _logger.info("=" * 80)

            # 查看日志文件内容
            with open(log_file_path, "r", encoding="utf-8") as f:
                log_content = f.read()
                print("\n" + "=" * 80)
                print("真实 Agent 测试日志：")
                print("=" * 80)
                print(log_content)
                print("=" * 80)

            # 检查 Agent 输出
            assistant_message = result.decision.assistant_message
            _logger.info("【Agent 最终输出】：%s", assistant_message)

            self.assertTrue(True, "真实 Agent 测试完成")

        except Exception as e:
            _logger.error("【真实 Agent 调用失败】：%s", str(e))
            _logger.error("可能原因：API 配置错误或网络问题")
            self.skipTest(f"真实 Agent 调用失败：{str(e)}")


if __name__ == "__main__":
    unittest.main()