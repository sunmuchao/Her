#!/usr/bin/env python3
"""简化的测试：只测试会话创建和timeout配置"""

import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = REPO_ROOT / "external-systems" / "partner-discovery-system"

for root in (REPO_ROOT, DISCOVERY_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage
from discovery_system.agent_runtime import create_default_discovery_agent_runtime
from datetime import datetime

print("=" * 80)
print("简化测试：验证Tracing禁用和timeout配置")
print("=" * 80)

# 创建服务
storage = InMemoryDiscoveryStorage()
runtime = create_default_discovery_agent_runtime()
service = DiscoveryService(storage=storage, runtime=runtime)

print("\nStep 1: 创建会话...")
session_result = service.create_session(
    requester_id=70001,
    profile_id=10001,
    now=datetime(2026, 6, 23, 10, 0, 0),
)
session_id = session_result["session"]["session_id"]
print(f"✅ 会话创建成功: session_id={session_id}")

print("\nStep 2: 测试一轮对话（简单意图）...")
print("用户消息: 我想找个温柔的女生")

try:
    turn_result = service.process_turn(
        session_id=session_id,
        user_message_text="我想找个温柔的女生",
        now=datetime(2026, 6, 23, 10, 1, 0),
    )
    print(f"✅ Agent决策成功")
    print(f"决策阶段: {turn_result.get('phase')}")
    print(f"助手消息: {turn_result.get('timeline', [{}])[0].get('body', 'N/A')[:50]}...")
    print(f"\n测试通过！Agent能正常工作")
except Exception as e:
    print(f"❌ Agent决策失败: {e}")

print("=" * 80)