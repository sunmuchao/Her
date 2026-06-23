#!/usr/bin/env python3
"""问题3复现测试：意图理解失败

测试目标：
1. 用户说"找个温柔的女生"，验证Agent是否提取"温柔"关键词
2. 验证Agent是否传递 personality_match_json 参数
3. 验证向量筛选是否触发
4. 验证Agent回复是否提及"温柔"

预期问题：
- Agent没有提取"温柔"关键词
- Agent没有传递 personality_match_json 参数
- 向量筛选未触发
- Agent回复千篇一律，未提及"温柔"
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
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {
        "session_type": "discovery",
        "requester_id": 10030,  # 使用新用户ID避免冲突
    }

    try:
        print("\n" + "=" * 80)
        print("【创建新会话】")
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

def send_turn(session_id: str, user_message: str, turn_label: str) -> dict | None:
    """发送单轮对话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {"user_message": user_message}

    try:
        print(f"\n" + "=" * 80)
        print(f"【{turn_label}】")
        print(f"用户说：'{user_message}'")
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
                        candidate_info = {
                            "profile_id": card.get("profile_id"),
                            "title": card.get("title", ""),
                            "reason_summary": card.get("reason_summary", ""),
                        }
                        # 提取性格特质数据
                        personality_signals = card.get("personality_signals") or {}
                        candidate_info["personality_signals"] = personality_signals
                        candidates.append(candidate_info)

            print(f"\n【Agent回复】{assistant_message}")

            # 检查关键词
            keywords_to_check = ["温柔", "安全感", "家庭", "内向", "外向", "稳重", "成熟"]
            found_keywords = [kw for kw in keywords_to_check if kw in assistant_message]
            if found_keywords:
                print(f"✅ Agent提及了关键词: {found_keywords}")
            else:
                print(f"❌ Agent未提及任何关键词")
                print(f"   应提及的关键词: 温柔")

            if candidates:
                print(f"\n【候选人】找到 {len(candidates)} 位:")
                for i, c in enumerate(candidates[:3], 1):
                    print(f"   {i}. {c['title']} (ID: {c['profile_id']})")
                    if c['reason_summary']:
                        print(f"      推荐理由: {c['reason_summary']}")
                    # 检查推荐理由是否包含关键词
                    reason_keywords = [kw for kw in keywords_to_check if kw in c['reason_summary']]
                    if reason_keywords:
                        print(f"      ✅ 推荐理由包含关键词: {reason_keywords}")
                    else:
                        print(f"      ❌ 推荐理由未包含关键词")

            # 保存完整结果到文件（用于后续日志分析）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = repo_root / "scripts" / f"p0-3-test-log-{timestamp}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump({
                    "turn_label": turn_label,
                    "user_message": user_message,
                    "assistant_message": assistant_message,
                    "candidates": candidates,
                    "full_response": result,
                }, f, ensure_ascii=False, indent=2)
            print(f"\n【完整响应已保存】{log_file}")

            return {
                "assistant_message": assistant_message,
                "candidates": candidates,
                "log_file": str(log_file),
            }
        else:
            print(f"❌ 响应失败: {response.status_code}")
            print(f"   错误: {response.text[:300]}")
            return None
    except requests.Timeout:
        print("❌ 响应超时（120秒）")
        print("   可能原因：AI处理耗时过长、向量筛选慢、LLM调用慢")
        return None
    except Exception as e:
        print(f"❌ 响应异常: {e}")
        return None

def main():
    print("\n" + "=" * 80)
    print("问题3复现测试：意图理解失败")
    print("测试时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    print("\n开始测试...")
    print("=" * 80)

    # ===== 测试场景1：性格特质意图 =====
    send_turn(
        session_id,
        "找个温柔的女生",
        "测试1：性格特质意图"
    )

    time.sleep(10)  # 间隔10秒

    # ===== 测试场景2：情感需求意图 =====
    send_turn(
        session_id,
        "我之前受过伤，希望能找个给我安全感的人",
        "测试2：情感需求意图"
    )

    time.sleep(10)

    # ===== 测试场景3：价值观意图 =====
    send_turn(
        session_id,
        "我很重视家庭，希望找个同样重视家庭的人",
        "测试3：价值观意图"
    )

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
    print("\n【下一步】")
    print("1. 检查上述日志文件，查看 Agent 是否传递了 personality_match_json 参数")
    print("2. 检查向量筛选是否触发（查看 gateway 日志或 backend 日志）")
    print("3. 分析 Agent 回复是否提及关键词")

if __name__ == "__main__":
    main()