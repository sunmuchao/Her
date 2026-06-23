#!/usr/bin/env python3
"""真实用户模拟测试 - 轻量版

逐步测试，每轮间隔较长，避免系统过载
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

# 创建新会话
def create_session():
    url = f"{GATEWAY_URL}/v1/discovery/sessions"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {
        "session_type": "discovery",
        "requester_id": 10020,  # 使用新用户ID避免冲突
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

# 发送单轮对话
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
        response = requests.post(url, headers=headers, json=data, timeout=120)  # 增加超时到120秒

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
                        })

            print(f"\n【Agent回复】{assistant_message[:100]}...")
            if candidates:
                print(f"【候选人】找到 {len(candidates)} 位:")
                for i, c in enumerate(candidates[:3], 1):
                    print(f"   {i}. {c['title']} (ID: {c['profile_id']})")

            return {
                "assistant_message": assistant_message,
                "candidates": candidates,
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

# 主测试流程
def main():
    print("\n" + "=" * 80)
    print("真实用户模拟测试 - 轻量版")
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    print("\n开始测试...")
    print("=" * 80)

    # ===== 第1轮：模糊意图 =====
    print("\n【测试1】模糊意图 - 极简表达")
    response = send_turn(session_id, "找个对象")

    if response:
        print("\n【观察】")
        msg = response["assistant_message"]

        # 检查是否追问必要条件
        if any(keyword in msg for keyword in ["性别", "年龄", "城市", "什么样的", "具体", "要求"]):
            print("✅ Agent正确追问了必要条件")
        else:
            print("❌ Agent没有追问必要条件")
            print(f"   实际回复：{msg[:100]}")

    time.sleep(5)  # 间隔5秒避免系统过载

    # ===== 第2轮：口语化表达 =====
    print("\n【测试2】口语化表达 - '靠谱'")
    response = send_turn(session_id, "找个靠谱的女生")

    if response:
        print("\n【观察】")
        msg = response["assistant_message"]

        # 检查是否理解"靠谱"
        print(f"   Agent回复：{msg[:100]}")
        print("   备注：口语化特质'靠谱'是否被正确理解")

    time.sleep(5)

    # ===== 第3轮：多意图叠加 =====
    print("\n【测试3】多意图叠加")
    response = send_turn(session_id, "我想找个温柔的，但也不要太内向")

    if response:
        print("\n【观察】")
        msg = response["assistant_message"]

        # 检查是否同时理解两个意图
        if "温柔" in msg and ("内向" in msg or "活泼" in msg or "开朗" in msg):
            print("✅ Agent同时理解了两个意图")
        else:
            print("❌ Agent可能只理解了部分意图")
            print(f"   实际回复：{msg[:100]}")

    time.sleep(5)

    # ===== 第4轮：情感需求 =====
    print("\n【测试4】深层次需求 - 情感需求")
    response = send_turn(session_id, "我之前受过伤，希望能找个给我安全感的人")

    if response:
        print("\n【观察】")
        msg = response["assistant_message"]

        # 检查是否理解情感需求
        if any(keyword in msg for keyword in ["安全感", "稳定", "可靠", "成熟", "受过伤"]):
            print("✅ Agent理解了情感需求")
        else:
            print("❌ Agent可能没有理解情感需求")
            print(f"   实际回复：{msg[:100]}")

    time.sleep(5)

    # ===== 第5轮：条件缺失 =====
    print("\n【测试5】条件缺失")
    response = send_turn(session_id, "找个温柔的女生")  # 缺少城市、年龄

    if response:
        print("\n【观察】")
        msg = response["assistant_message"]

        # 检查是否追问缺失条件
        if any(keyword in msg for keyword in ["城市", "年龄", "地区", "多大", "范围", "哪里"]):
            print("✅ Agent追问了缺失的条件")
        else:
            print("❌ Agent没有追问缺失条件")
            print(f"   实际回复：{msg[:100]}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    print("\n【测试总结】")
    print("1. 模糊意图：是否追问必要条件")
    print("2. 口语化表达：是否能理解口语化特质")
    print("3. 多意图叠加：是否能同时理解多个意图")
    print("4. 情感需求：是否能理解深层情感需求")
    print("5. 条件缺失：是否能识别缺失条件并追问")

    print("\n【后续测试建议】")
    print("- Agent幻觉测试：跨轮次引用候选人")
    print("- 极端条件测试：极窄年龄范围、条件矛盾")
    print("- 画像写入验证：会话结束后检查画像数据")
    print("- 推荐理由验证：检查推荐理由是否基于实际数据")

if __name__ == "__main__":
    main()