#!/usr/bin/env python3
"""P1-3 问题复现测试 - 多意图理解失败

测试目标：验证 Agent 是否能同时理解多个意图
测试场景：
1. 多意图叠加："我想找个温柔的，但也不要太内向"
2. 意图反转："刚才说找个温柔的，但我又想想，还是找个活泼的吧"
3. 意图否定："不要苏州的，也不要上海的"

预期结果：
- Agent 应该同时理解两个意图，并在回复中提及两个意图关键词
- Agent 应该正确更新条件，从"温柔"改为"活泼"
- Agent 应该正确排除苏州和上海

如果失败，说明 Agent 只理解了部分意图，符合 P1-3 问题描述
"""

from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from datetime import datetime

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

GATEWAY_URL = "http://127.0.0.1:8765"


def create_session():
    """创建新会话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-p1-3-test-001",
    }

    data = {
        "session_type": "discovery",
        "requester_id": 10030,  # 使用新用户ID避免冲突
    }

    try:
        print("\n【创建新会话】")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            result = response.json()
            session_id = result.get("session", {}).get("session_id")
            print(f"✅ 会话创建成功: {session_id}")
            return session_id
        else:
            print(f"❌ 会话创建失败: {response.status_code}")
            print(f"   错误: {response.text[:300]}")
            return None
    except Exception as e:
        print(f"❌ 会话创建异常: {e}")
        return None


def send_turn(session_id: str, user_message: str) -> dict | None:
    """发送单轮对话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-p1-3-test-001",
    }

    data = {"user_message": user_message}

    try:
        print(f"\n【用户说】'{user_message}'")
        print("【等待响应】...")
        response = requests.post(url, headers=headers, json=data, timeout=120)

        if response.status_code == 200:
            result = response.json()
            print("✅ 响应成功")

            # 提取关键信息
            view = result.get("view", {})
            timeline = view.get("timeline", [])

            # 提取assistant消息
            assistant_message = ""
            for item in timeline:
                if item.get("item_type") == "assistant_message":
                    assistant_message = item.get("body", "")
                    break

            # 提取候选人
            candidates = []
            for item in timeline:
                if item.get("item_type") == "result_group":
                    cards = item.get("cards", [])
                    for card in cards:
                        candidates.append({
                            "profile_id": card.get("profile_id"),
                            "title": card.get("title", ""),
                            "reason": card.get("reason", ""),
                        })

            print(f"\n【Agent完整回复】")
            print("-" * 80)
            print(assistant_message)
            print("-" * 80)

            if candidates:
                print(f"\n【候选人】找到 {len(candidates)} 位:")
                for i, c in enumerate(candidates[:5], 1):
                    print(f"   {i}. {c['title']} (ID: {c['profile_id']})")
                    if c['reason']:
                        print(f"      推荐理由: {c['reason']}")

            return {
                "assistant_message": assistant_message,
                "candidates": candidates,
                "raw_response": result,
            }
        else:
            print(f"❌ 响应失败: {response.status_code}")
            print(f"   错误: {response.text[:500]}")
            return None
    except requests.Timeout:
        print("❌ 响应超时（120秒）")
        return None
    except Exception as e:
        print(f"❌ 响应异常: {e}")
        return None


def check_keywords(msg: str, keywords: list[str]) -> dict:
    """检查消息中是否包含关键词"""
    found = []
    missing = []

    for kw in keywords:
        if kw in msg:
            found.append(kw)
        else:
            missing.append(kw)

    return {
        "found": found,
        "missing": missing,
        "found_ratio": len(found) / len(keywords) if keywords else 0,
    }


def test_multi_intent(session_id: str):
    """测试1：多意图叠加"""
    print("\n" + "=" * 80)
    print("【测试1】多意图叠加")
    print("=" * 80)
    print("场景：用户说'我想找个温柔的，但也不要太内向'")
    print("预期：Agent回复中同时提及'温柔'和'内向/活泼/开朗'")
    print("=" * 80)

    user_message = "我想找个温柔的，但也不要太内向"
    response = send_turn(session_id, user_message)

    if not response:
        print("❌ 测试失败：无法获取响应")
        return False

    msg = response["assistant_message"]

    # 检查关键词
    # 应该出现的关键词：温柔 + (内向 或 活泼 或 开朗)
    keywords_positive = ["温柔"]
    keywords_negative = ["内向", "活泼", "开朗"]

    positive_check = check_keywords(msg, keywords_positive)
    negative_check = check_keywords(msg, keywords_negative)

    print("\n【关键词检查】")
    print(f"   正向意图关键词（温柔）: {positive_check}")
    print(f"   负向意图关键词（内向/活泼/开朗）: {negative_check}")

    # 判断是否成功
    if positive_check["found"] and negative_check["found"]:
        print("\n✅ 测试通过：Agent同时理解了两个意图")
        print(f"   找到关键词：{positive_check['found']} + {negative_check['found']}")
        return True
    else:
        print("\n❌ 测试失败：Agent只理解了部分意图")
        print(f"   正向意图关键词：找到 {positive_check['found']}, 缺失 {positive_check['missing']}")
        print(f"   负向意图关键词：找到 {negative_check['found']}, 缺失 {negative_check['missing']}")
        print("   这符合 P1-3 问题描述：多意图理解失败")
        return False


def test_intent_reversal(session_id: str):
    """测试2：意图反转"""
    print("\n" + "=" * 80)
    print("【测试2】意图反转")
    print("=" * 80)
    print("场景：用户先说要'温柔'，后改口要'活泼'")
    print("预期：Agent回复中提及'活泼'，不再强调'温柔'")
    print("=" * 80)

    # 先说要温柔
    print("\n【第1步】先说要温柔")
    user_message_1 = "我想找个温柔的"
    response_1 = send_turn(session_id, user_message_1)

    if not response_1:
        print("❌ 测试失败：无法获取响应")
        return False

    time.sleep(3)

    # 改口要活泼
    print("\n【第2步】改口要活泼")
    user_message_2 = "刚才说找个温柔的，但我又想想，还是找个活泼的吧"
    response_2 = send_turn(session_id, user_message_2)

    if not response_2:
        print("❌ 测试失败：无法获取响应")
        return False

    msg_2 = response_2["assistant_message"]

    # 检查关键词
    keywords_new = ["活泼", "开朗"]
    keywords_old = ["温柔"]

    new_check = check_keywords(msg_2, keywords_new)
    old_check = check_keywords(msg_2, keywords_old)

    print("\n【关键词检查】")
    print(f"   新意图关键词（活泼/开朗）: {new_check}")
    print(f"   旧意图关键词（温柔）: {old_check}")

    # 判断是否成功
    if new_check["found"]:
        print("\n✅ 测试通过：Agent正确更新了意图")
        print(f"   找到新意图关键词：{new_check['found']}")
        return True
    else:
        print("\n❌ 测试失败：Agent没有正确更新意图")
        print(f"   新意图关键词缺失：{new_check['missing']}")
        print("   这符合 P1-3 问题描述：意图反转失败")
        return False


def test_intent_negation(session_id: str):
    """测试3：意图否定"""
    print("\n" + "=" * 80)
    print("【测试3】意图否定")
    print("=" * 80)
    print("场景：用户说'不要苏州的，也不要上海的'")
    print("预期：Agent回复中提及排除苏州和上海")
    print("=" * 80)

    user_message = "不要苏州的，也不要上海的"
    response = send_turn(session_id, user_message)

    if not response:
        print("❌ 测试失败：无法获取响应")
        return False

    msg = response["assistant_message"]

    # 检查关键词
    keywords = ["苏州", "上海"]

    check_result = check_keywords(msg, keywords)

    print("\n【关键词检查】")
    print(f"   应排除的城市关键词: {check_result}")

    # 判断是否成功
    # 如果Agent理解了否定意图，应该会提及这两个城市（说明理解了要排除）
    if check_result["found"]:
        print("\n✅ 测试通过：Agent理解了否定意图")
        print(f"   找到关键词：{check_result['found']}（说明Agent理解了要排除这些城市）")
        return True
    else:
        print("\n❌ 测试失败：Agent没有理解否定意图")
        print(f"   缺失关键词：{check_result['missing']}")
        print("   这符合 P1-3 问题描述：否定意图理解失败")
        return False


def main():
    print("\n" + "=" * 80)
    print("P1-3 问题复现测试 - 多意图理解失败")
    print("=" * 80)
    print("测试时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    # 运行测试
    results = []

    # 测试1：多意图叠加
    result_1 = test_multi_intent(session_id)
    results.append(("多意图叠加", result_1))

    time.sleep(5)

    # 测试2：意图反转（需要新会话）
    print("\n【创建新会话】用于测试2")
    session_id_2 = create_session()
    if session_id_2:
        result_2 = test_intent_reversal(session_id_2)
        results.append(("意图反转", result_2))

    time.sleep(5)

    # 测试3：意图否定（需要新会话）
    print("\n【创建新会话】用于测试3")
    session_id_3 = create_session()
    if session_id_3:
        result_3 = test_intent_negation(session_id_3)
        results.append(("意图否定", result_3))

    # 打印测试总结
    print("\n" + "=" * 80)
    print("【测试总结】")
    print("=" * 80)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {name}: {status}")

    # 计算通过率
    passed = sum(1 for _, r in results if r)
    total = len(results)
    pass_rate = passed / total if total > 0 else 0

    print(f"\n   通过率: {passed}/{total} ({pass_rate * 100:.1f}%)")

    # 结论
    print("\n" + "=" * 80)
    print("【结论】")
    print("=" * 80)

    if pass_rate < 0.5:
        print("❌ P1-3 问题已复现：Agent多意图理解能力不足")
        print("   建议：增强意图识别逻辑，支持复合意图理解")
    elif pass_rate < 1.0:
        print("⚠️  P1-3 问题部分复现：Agent在某些场景下多意图理解失败")
        print("   建议：分析失败场景，针对性优化")
    else:
        print("✅ P1-3 问题未复现：Agent多意图理解正常")
        print("   可能原因：问题已修复，或测试场景不够典型")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()