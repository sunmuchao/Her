#!/usr/bin/env python3
"""测量工具定义Schema的实际大小"""

import json
import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = REPO_ROOT / "external-systems" / "partner-discovery-system"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DISCOVERY_ROOT))

from agents import function_tool
from discovery_system.agent_runtime import (
    _build_discovery_agent_instructions,
    _build_runtime_prompt,
    DiscoveryRunInput,
)
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage
from datetime import datetime

# 创建测试服务
storage = InMemoryDiscoveryStorage()
service = DiscoveryService(storage=storage, runtime=None)

# 创建测试会话
session_result = service.create_session(
    requester_id=70001,
    profile_id=10001,
    now=datetime(2026, 6, 23, 10, 0, 0),
)

session_id = session_result["session"]["session_id"]
session = storage.get_session(session_id)

# 构建runtime_input
run_input = service._build_runtime_input(session, now=datetime(2026, 6, 23, 10, 1, 0))

# 手动定义工具（模拟Agent Runtime中的工具定义）
@function_tool
def sync_requester_persona_memory(patch_json: str) -> dict:
    """同步用户的择偶偏好到长期记忆。当用户说出明确、稳定、适合落库的择偶偏好时调用。沉淀长期偏好，后续推荐更精准。"""
    return {"success": True}

@function_tool
def search_partner_candidates(
    criteria_json: str,
    personality_match_json: str = "",
    limit: int = 5,
    exclude_current_results: bool = False,
) -> dict:
    """搜索候选人。当用户想看推荐、调整搜索条件、表达不满后重新搜索时调用。

这是"重新搜人"的唯一工具。是否排除当前已展示候选人，必须由你显式决定并通过参数传入，
不要假设系统会自动理解"换一批"。

支持的筛选条件（硬约束）：
- gender: 性别（male/female）
- age_min/age_max: 年龄范围
- cities: 城市列表
- relationship_goals: 关系目标

性格匹配（向量筛选，可选）：
- personality_match_json: 性格特质匹配条件
  示例：{"match_traits": ["外向", "温柔"], "similarity_threshold": 0.75}
  - match_traits: 想要匹配的性格特质列表
  - similarity_threshold: 相似度阈值（0.0-1.0，默认0.75）
  - Agent可根据对话上下文自主调整阈值（高要求用0.8，宽松用0.6）

返回数据：
- 基础信息：姓名、年龄、城市、职业等
- 性格数据：personality_signals包含MBTI、依恋风格、价值观等原始数据
- candidate_context：数据完整度指示器，帮助Agent判断推荐理由的详细程度

参数：
- criteria_json: 筛选条件的JSON字符串（硬约束）
- personality_match_json: 性格匹配条件的JSON字符串（可选）
- limit: 最终返回数量（默认5，最大10）
- exclude_current_results: 是否排除当前已展示候选人（用于"换一批"）

返回：
- has_match: 是否找到候选人（True/False）
- result_count: 候选人数量
- results: 候选人列表（包含性格原始数据）
"""
    return {"has_match": True, "result_count": 5, "results": []}

@function_tool
def reply_to_user(
    message: str,
    phase: str = "collecting_preferences",
    criteria_labels: list[str] = [],
    suggested_actions: list[dict] = [],
) -> dict:
    """回复用户对话消息，不展示候选人卡片。适用场景：回答用户问题、解释推荐理由、收集用户反馈。

参数：
- message: 回复消息内容（口语化、自然）
- phase: 当前阶段（collecting_preferences/searching/results_shown/no_result）
- criteria_labels: 当前筛选条件标签（如"苏州"、"25-30岁"）
- suggested_actions: 建议操作按钮（label + style + semantic_payload）

返回：
- success: True
"""
    return {"success": True}

@function_tool
def show_candidates(
    candidate_ids: list[int],
    message: str = "",
    title: str = "",
    criteria: list[str] = [],
) -> dict:
    """展示候选人卡片列表，配合对话回复使用。

参数：
- candidate_ids: 候选人ID列表（从search_partner_candidates返回）
- message: 回复消息内容
- title: 候选人分组标题（如"这一轮先给你看这些候选人"）
- criteria: 筛选条件标签（如["苏州", "26-30岁", "温柔"]）

返回：
- success: True
"""
    return {"success": True}

@function_tool
def suggest_assessment(assessment_type: str) -> dict:
    """检查用户测评状态，返回引导卡片或性格信息。

参数：
- assessment_type: 测评类型（mbti_16/attachment_style）

返回：
- success: True
- card: 测评引导卡片或性格信息
"""
    return {"success": True}

@function_tool
def create_saved_search_subscription_from_last_search() -> dict:
    """创建订阅，按当前搜索条件持续留意新候选人。当用户想长期关注符合条件的候选人时推荐使用。"""
    return {"success": True}

# 构建工具列表
tools = [
    sync_requester_persona_memory,
    search_partner_candidates,
    create_saved_search_subscription_from_last_search,
    reply_to_user,
    show_candidates,
    suggest_assessment,
]

# 测量工具Schema大小
print("=" * 80)
print("工具定义Schema大小分析")
print("=" * 80)

total_schema_chars = 0
for tool in tools:
    schema = tool.params_json_schema
    schema_json = json.dumps(schema, ensure_ascii=False)
    tool_name = tool.name

    print(f"\n{tool_name}:")
    print(f"  Schema大小: {len(schema_json)} chars")

    # 统计参数数量
    properties = schema.get("properties") or {}
    print(f"  参数数量: {len(properties)}")
    print(f"  参数列表: {list(properties.keys())}")

    # 打印参数详情
    for param_name, param_schema in properties.items():
        param_type = param_schema.get("type", "unknown")
        param_desc = param_schema.get("description", "")
        print(f"    - {param_name} ({param_type}): {len(param_desc)} chars")

    total_schema_chars += len(schema_json)

print("\n" + "=" * 80)
print(f"工具Schema总大小: {total_schema_chars} chars, {round(total_schema_chars / 4)} tokens")
print("=" * 80)

# 构建完整的Agent输入
instructions = _build_discovery_agent_instructions(
    event="session_opened",
    user_message=None,
    action_context=None,
)

runtime_input = _build_runtime_prompt(
    run_input=run_input,
    event="session_opened",
    user_message=None,
    action_context=None,
)

# 计算总上下文大小
instructions_chars = len(instructions)
runtime_input_chars = len(runtime_input)
total_chars = instructions_chars + runtime_input_chars + total_schema_chars

print("\n" + "=" * 80)
print("Agent完整上下文大小汇总")
print("=" * 80)
print(f"Instructions (SOUL.md): {instructions_chars} chars")
print(f"Runtime Input (JSON): {runtime_input_chars} chars")
print(f"Tools Schema: {total_schema_chars} chars")
print(f"总计: {total_chars} chars, {round(total_chars / 4)} tokens")
print("=" * 80)

# 判断是否超过阈值
if total_chars > 32000:
    print("⚠️ ERROR: 超过32000字符阈值!")
elif total_chars > 16000:
    print("⚠️ WARNING: 超过16000字符阈值!")
else:
    print("✅ OK: 未超过阈值")

# 打印Schema示例
print("\n" + "=" * 80)
print("工具Schema示例（search_partner_candidates）")
print("=" * 80)
print(json.dumps(search_partner_candidates.params_json_schema, ensure_ascii=False, indent=2)[:1000] + "...")