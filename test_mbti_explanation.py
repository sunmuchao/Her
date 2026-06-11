#!/usr/bin/env python
"""
测试 AI 是否能解释 MBTI 匹配逻辑。

场景：
- 用户 MBTI 为 ISFJ
- 用户点击"换一批" → 选择"性格气质不对"
- 检查 AI 是否能：
  1. 读出用户的 MBTI（ISFJ）
  2. 解释匹配的类型（ESFJ/ISFP）
  3. 解释匹配原因
"""

import json
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mbti_explanation():
    """测试 AI 对 MBTI 匹配的解释能力"""

    # 模拟用户的 profile（包含 MBTI 信息）
    user_profile = {
        "gender": "male",
        "age": 30,
        "city": "无锡",
        "personality_traits": {
            "mbti": {"type_code": "ISFJ"},
            "attachment": {"type_code": "secure"},
            "values": {"top_values": ["家庭", "稳定"]}
        }
    }

    # 模拟 runtime_context
    runtime_context = {
        "user_profile": user_profile,
        "session": {
            "session_id": "test-session-001",
            "phase": "results_shown",
            "status": "active",
        },
        "current_results": [
            {
                "profile_id": 123,
                "title": "张三",
                "personality_match_context": {
                    "mbti": {"type_code": "INTJ"},
                    "values": {"top_values": ["事业", "独立"]}
                }
            }
        ],
        "last_search": {
            "criteria": {"city": "无锡", "age_min": 26, "age_max": 30},
            "result_count": 3,
        },
    }

    # 模拟用户点击"性格气质不对"
    action_context = {
        "label": "性格气质不对",
        "semantic_payload": {
            "kind": "rejection_feedback",
            "feedback_type": "personality_mismatch",
            "feedback_text": "性格气质不对",
        }
    }

    # 构建 Agent 的输入 prompt
    agent_input = {
        "event": {
            "type": "action_click",
            "user_message": None,
            "clicked_action": {
                "label": "性格气质不对",
                "kind": "rejection_feedback",
                "hint": action_context["semantic_payload"],
            }
        },
        "state": {
            "session": runtime_context["session"],
            "user_profile": user_profile,
            "current_results": runtime_context["current_results"],
            "visible_actions": [],
            "last_search": runtime_context["last_search"],
        },
        "memory_summary": {},
    }

    print("=" * 60)
    print("测试输入:")
    print("=" * 60)
    print(json.dumps(agent_input, ensure_ascii=False, indent=2))
    print()

    print("=" * 60)
    print("期望 AI 能解释:")
    print("=" * 60)
    print("1. 用户 MBTI: ISFJ（内向、感性、稳定型）")
    print("2. 匹配类型: ESFJ 或 ISFP")
    print("3. 匹配原因: ESFJ 互补（外向带活力），ISFP 相似（都内向温和）")
    print()

    print("=" * 60)
    print("测试说明:")
    print("=" * 60)
    print("AI 作为大模型，应该知道 MBTI 匹配规则。")
    print("如果 AI 不知道，可能是因为：")
    print("- SOUL.md 缺少性格匹配指导")
    print("- runtime_context 缺少匹配规则信息")
    print("- AI 没有正确读取 user_profile.personality_traits")
    print()

    return agent_input


if __name__ == "__main__":
    test_mbti_explanation()