#!/usr/bin/env python3
"""测量runtime_context的实际大小"""

import json
import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = REPO_ROOT / "external-systems" / "partner-discovery-system"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage
from discovery_system.agent_runtime import create_default_discovery_agent_runtime
from datetime import datetime

# 创建测试服务
storage = InMemoryDiscoveryStorage()
runtime = create_default_discovery_agent_runtime()
service = DiscoveryService(storage=storage, runtime=runtime)

# 创建测试会话
session_result = service.create_session(
    requester_id=70001,
    profile_id=10001,
    now=datetime(2026, 6, 23, 10, 0, 0),
)

# _session_payload返回 {"session": {...}, "view": {...}}
session_id = session_result["session"]["session_id"]
print(f"会话创建成功: session_id={session_id}")

# 获取session
session = storage.get_session(session_id)
print(f"session.phase={session.phase}")

# 构建runtime_input
run_input = service._build_runtime_input(session, now=datetime(2026, 6, 23, 10, 1, 0))

# 测量各字段大小
print("\n" + "=" * 80)
print("runtime_input各字段大小分析")
print("=" * 80)

# 1. recent_timeline大小
recent_timeline_json = json.dumps(run_input.recent_timeline, ensure_ascii=False)
print(f"recent_timeline: {len(recent_timeline_json)} chars, {len(run_input.recent_timeline)} items")

# 2. runtime_context各字段大小
runtime_context = run_input.runtime_context
print(f"\nruntime_context总大小: {len(json.dumps(runtime_context, ensure_ascii=False))} chars")

for key, value in runtime_context.items():
    value_json = json.dumps(value, ensure_ascii=False)
    print(f"  {key}: {len(value_json)} chars")

    # 如果是嵌套dict，进一步分析
    if isinstance(value, dict) and len(value) > 0:
        for sub_key, sub_value in value.items():
            if isinstance(sub_value, (dict, list)):
                sub_json = json.dumps(sub_value, ensure_ascii=False)
                print(f"    {sub_key}: {len(sub_json)} chars")

# 3. 测量完整input大小
input_json = json.dumps({
    "session_id": run_input.session_id,
    "requester_id": run_input.requester_id,
    "profile_id": run_input.profile_id,
    "phase": run_input.phase,
    "criteria_labels": run_input.criteria_labels,
    "recent_timeline": run_input.recent_timeline,
    "runtime_context": run_input.runtime_context,
}, ensure_ascii=False)

print(f"\n完整input大小: {len(input_json)} chars, {round(len(input_json) / 4)} tokens (rough estimate)")

# 判断是否超过阈值
if len(input_json) > 32000:
    print("⚠️ ERROR: 超过32000字符阈值!")
elif len(input_json) > 16000:
    print("⚠️ WARNING: 超过16000字符阈值!")
else:
    print("✅ OK: 未超过阈值")

print("\n" + "=" * 80)
print("详细内容示例")
print("=" * 80)

# 打印runtime_context示例
print("\nruntime_context内容:")
print(json.dumps(runtime_context, ensure_ascii=False, indent=2)[:500] + "...")