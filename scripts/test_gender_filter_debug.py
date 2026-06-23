#!/usr/bin/env python3
"""定位性别过滤失效问题 - 详细日志版本

测试流程：
1. 创建新会话
2. 发送"找个苏州的25-30岁的温柔女生"
3. 打印Agent提取的criteria_json参数
4. 打印criteria字典内容
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
        "requester_id": 10035,  # 新测试用户
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
        print(f"\n【发送消息】'{user_message}'")
        print("【等待响应】（可能需要120秒）...")
        response = requests.post(url, headers=headers, json=data, timeout=120)

        if response.status_code == 200:
            result = response.json()
            print("✅ 响应成功")
            return result
        else:
            print(f"❌ 响应失败: {response.status_code}")
            print(f"   错误: {response.text[:300]}")
            return None
    except Exception as e:
        print(f"❌ 响应异常: {e}")
        return None

def main():
    print("\n" + "=" * 80)
    print("定位性别过滤失效问题 - 详细日志版本")
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    print("\n开始测试...")
    print("=" * 80)

    # 发送测试消息
    response = send_turn(session_id, "找个苏州的25-30岁的温柔女生")

    if response:
        print("\n【响应内容】")
        print("=" * 80)

        # 提取关键信息
        view = response.get("view", {})
        timeline = view.get("timeline", [])

        # 提取assistant消息
        assistant_message = ""
        for item in timeline:
            if item.get("item_type") == "assistant_message":
                assistant_message = item.get("body", "")
                break

        print(f"\n【Agent回复】\n{assistant_message}\n")

        # 提取候选人
        candidates = []
        for item in timeline:
            if item.get("item_type") == "result_group":
                cards = item.get("cards", [])
                for card in cards:
                    candidates.append({
                        "profile_id": card.get("profile_id"),
                        "title": card.get("title", ""),
                        "subtitle": card.get("subtitle", ""),
                        "reason_summary": card.get("reason_summary", ""),
                    })

        if candidates:
            print(f"\n【候选人列表】找到 {len(candidates)} 位:")
            for i, c in enumerate(candidates[:5], 1):
                print(f"   {i}. {c['title']}")
                print(f"      {c['subtitle']}")
                print(f"      推荐理由: {c['reason_summary']}")
                print(f"      ID: {c['profile_id']}")
        else:
            print("\n❌ 未找到候选人")

        # 提取phase
        phase = response.get("phase", "")
        print(f"\n【Phase】{phase}")

        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)

        print("\n【检查日志文件】")
        print(f"日志路径: /Users/sunmuchao/Downloads/Her/.run/logs/gateway.log")
        print(f"Session ID: {session_id}")
        print("\n【关键日志】请查找以下内容：")
        print("1. Agent调用search_partner_candidates工具时的参数:")
        print("   grep -A 20 'session_id={session_id}' gateway.log | grep criteria_json")
        print("2. criteria字典内容:")
        print("   grep '【搜索开始】session_id={session_id}' gateway.log")
        print("3. 搜索SQL查询:")
        print("   grep -A 10 'search_profiles_with_visibility_gate' gateway.log")

        print("\n【预期问题】")
        print("如果criteria={}（空字典），说明：")
        print("- Agent没有正确提取用户消息中的条件（性别、年龄、城市）")
        print("- 或者Agent传递的criteria_json参数是空字符串")

    print("\n测试完成！请查看日志文件定位具体问题。")

if __name__ == "__main__":
    main()