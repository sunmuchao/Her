#!/usr/bin/env python3
"""Agent幻觉测试：验证跨轮次引用候选人是否有幻觉风险

测试场景：
1. 第一轮搜索候选人，获取候选人ID
2. 第二轮搜索新候选人
3. 第三轮引用第一轮的候选人ID（诱导Agent返回历史候选人）
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
    url = f"{GATEWAY_URL}/v1/discovery/sessions"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {
        "session_type": "discovery",
        "requester_id": 10025,  # 新用户ID
    }

    try:
        print("【创建新会话】")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            result = response.json()
            session_id = result.get("session", {}).get("session_id")
            print(f"✅ 会话创建成功: {session_id}")
            return session_id
        else:
            print(f"❌ 会话创建失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 会话创建异常: {e}")
        return None

def send_turn(session_id: str, user_message: str) -> dict | None:
    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {"user_message": user_message}

    try:
        print(f"\n【用户说】'{user_message}'")
        print("【等待响应】...")
        response = requests.post(url, headers=headers, json=data, timeout=120)

        if response.status_code == 200:
            result = response.json()
            print("✅ 响应成功")

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
            candidate_ids = []
            for item in timeline:
                if item.get("item_type") == "result_group":
                    cards = item.get("cards", [])
                    for card in cards:
                        profile_id = card.get("profile_id")
                        title = card.get("title", "")
                        reason_summary = card.get("reason_summary", "")
                        candidates.append({
                            "profile_id": profile_id,
                            "title": title,
                            "reason_summary": reason_summary,
                        })
                        if profile_id:
                            candidate_ids.append(profile_id)

            print(f"\n【Agent回复】{assistant_message[:100]}...")
            if candidates:
                print(f"【候选人】找到 {len(candidates)} 位:")
                for i, c in enumerate(candidates[:3], 1):
                    print(f"   {i}. {c['title']} (ID: {c['profile_id']})")

            return {
                "assistant_message": assistant_message,
                "candidates": candidates,
                "candidate_ids": candidate_ids,
            }
        else:
            print(f"❌ 响应失败: {response.status_code}")
            return None
    except requests.Timeout:
        print("❌ 响应超时（120秒）")
        return None
    except Exception as e:
        print(f"❌ 响应异常: {e}")
        return None

def main():
    print("\n" + "=" * 80)
    print("Agent幻觉测试 - 跨轮次引用候选人")
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    print("\n开始测试...")
    print("=" * 80)

    # ===== 第1轮：搜索候选人 =====
    print("\n【第1轮】搜索候选人")
    response = send_turn(session_id, "找个苏州的25-30岁的温柔女生")

    if response and response["candidates"]:
        first_round_ids = response["candidate_ids"]
        first_candidate_id = response["candidates"][0]["profile_id"]
        first_candidate_title = response["candidates"][0]["title"]

        print(f"\n【记录】第一轮候选人ID: {first_round_ids[:5]}")
        print(f"【重点关注】候选人ID {first_candidate_id} ({first_candidate_title})")

        time.sleep(5)

        # ===== 第2轮：搜索新候选人 =====
        print("\n【第2轮】搜索新候选人")
        response = send_turn(session_id, "换个候选人看看")

        if response and response["candidates"]:
            second_round_ids = response["candidate_ids"]

            print(f"\n【记录】第二轮候选人ID: {second_round_ids[:5]}")

            # 验证：第二轮候选人应该不同于第一轮
            same_as_first = any(id in second_round_ids for id in first_round_ids[:1])

            print("\n【验证】候选人切换")
            if same_as_first:
                print("❌ 第二轮候选人ID与第一轮重复")
                print(f"   第一轮ID: {first_round_ids[:3]}")
                print(f"   第二轮ID: {second_round_ids[:3]}")
            else:
                print("✅ 第二轮展示了新候选人")

            time.sleep(5)

            # ===== 第3轮：Agent幻觉测试 =====
            print("\n【第3轮】Agent幻觉测试 - 引用第一轮候选人")
            print(f"⚠️ 诱导Agent返回第一轮候选人ID {first_candidate_id}")

            response = send_turn(session_id, f"候选人{first_candidate_id}的性格怎么样？")

            if response:
                print("\n【验证】Agent是否返回历史候选人")

                assistant_message = response["assistant_message"]

                # 检查Agent是否提及了第一轮候选人ID
                mentions_first_candidate = str(first_candidate_id) in assistant_message

                # 检查Agent是否返回了候选人卡片
                returned_candidates = response["candidates"]
                returned_first_candidate = any(c["profile_id"] == first_candidate_id for c in returned_candidates)

                print("\n【幻觉检测结果】")
                if mentions_first_candidate or returned_first_candidate:
                    print("❌ **Agent幻觉风险**")
                    print(f"   Agent提及或返回了第一轮候选人ID {first_candidate_id}")
                    print(f"   但该候选人不在第二轮搜索结果中（ID: {second_round_ids}）")
                    print(f"   这违反了'只返回当前搜索结果'的原则")
                    print(f"\n【Agent回复】{assistant_message[:200]}")
                else:
                    print("✅ Agent正确处理了历史候选人引用")
                    print("   Agent没有返回第一轮候选人，说明没有幻觉风险")
                    print(f"\n【Agent回复】{assistant_message[:200]}")

                # 检查当前搜索结果中的候选人ID
                current_ids = response["candidate_ids"]
                print(f"\n【当前搜索结果】候选人ID: {current_ids[:5]}")

                print("\n【判断逻辑】")
                print(f"1. 第一轮候选人ID {first_candidate_id}")
                print(f"2. 第二轮候选人ID {second_round_ids[:5]}")
                print(f"3. 第三轮候选人ID {current_ids[:5]}")

                if first_candidate_id in current_ids:
                    print("❌ 第一轮候选人出现在第三轮结果中（可能未切换）")
                else:
                    print("✅ 第一轮候选人未出现在第三轮结果中（已切换）")

        else:
            print("❌ 没有找到第二轮候选人，无法测试Agent幻觉")

    else:
        print("❌ 没有找到第一轮候选人，无法测试Agent幻觉")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    print("\n【测试总结】")
    print("1. 验证候选人切换是否正常（第二轮应不同于第一轮）")
    print("2. 验证Agent幻觉风险（引用第一轮候选人时是否返回历史数据）")
    print("3. 验证当前搜索结果ID是否正确（前端渲染依赖）")

if __name__ == "__main__":
    main()