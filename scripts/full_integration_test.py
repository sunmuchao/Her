#!/usr/bin/env python3
"""
完整模拟测试脚本
模拟真实用户在前端的所有操作场景
"""

import sys
import os
import json
import requests
from datetime import datetime

# 设置路径和环境变量
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system')

from dotenv import load_dotenv
load_dotenv('/Users/sunmuchao/Downloads/Her/.env', override=True)

# Gateway地址
GATEWAY_URL = "http://127.0.0.1:8765"

print("=" * 80)
print("完整模拟测试 - 学习闭环功能验证")
print("=" * 80)

# ========== 模拟用户登录和创建session ==========

def create_discovery_session():
    """创建Discovery Session"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions"

    # 模拟用户数据（使用测试用户）
    payload = {
        "requester_id": 12345,
        "profile_id": 67890,
        "mode": "agent"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            data = response.json()
            session_id = data.get("session", {}).get("session_id")
            print(f"✅ Session创建成功: {session_id}")
            return session_id
        else:
            print(f"❌ Session创建失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Session创建异常: {e}")
        return None

# ========== 第一轮：用户说"换一批" ==========

def test_round_1(session_id):
    """第一轮测试：用户说'换一批'"""
    print("\n" + "=" * 80)
    print("第一轮：用户说'换一批'")
    print("=" * 80)

    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    payload = {
        "user_message": "换一批"
    }

    print("\n[用户] 说：'换一批'")

    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()

            # 检查文案
            assistant_message = data.get("view", {}).get("timeline", [{}])[-1].get("body", "")
            print(f"\n[系统] 回复：")
            print(f"   {assistant_message[:100]}...")

            # 验证文案是否正确
            expected_message = "换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准"
            if expected_message in assistant_message:
                print("✅ 文案正确（包含'换之前能简单告诉我...'）")
            else:
                print("❌ 文案错误（应该是'换之前能简单告诉我...'）")
                print(f"   实际文案：{assistant_message}")

            # 检查suggested_actions
            suggested_actions = data.get("view", {}).get("suggested_actions", [])
            print(f"\n[系统] 展示选项：{len(suggested_actions)}个")

            if suggested_actions:
                for i, action in enumerate(suggested_actions[:6], 1):
                    label = action.get("label", "")
                    print(f"   {i}. {label}")

                    # 检查semantic_payload
                    payload = action.get("semantic_payload", {})
                    kind = payload.get("kind", "")
                    print(f"      semantic_payload.kind: {kind}")

                    if kind == "rejection_feedback":
                        print("      ✅ 正确的kind（rejection_feedback）")
                    else:
                        print(f"      ❌ 错误的kind（应该是rejection_feedback）")

            # 检查是否有候选人卡片
            result_cards = data.get("view", {}).get("timeline", [])
            has_candidates = any(card.get("item_type") == "result_group" for card in result_cards)

            if has_candidates:
                print("❌ 错误：第一轮不应该展示候选人卡片")
            else:
                print("✅ 正确：第一轮没有展示候选人卡片")

            return suggested_actions

        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return []

    except Exception as e:
        print(f"❌ 第一轮测试异常: {e}")
        return []

# ========== 第二轮：用户点击选项 ==========

def test_round_2(session_id, suggested_actions):
    """第二轮测试：用户点击选项"""
    print("\n" + "=" * 80)
    print("第二轮：用户点击选项（模拟点击'职业不太匹配'）")
    print("=" * 80)

    if not suggested_actions:
        print("❌ 没有可点击的选项")
        return

    # 选择第一个反馈选项（假设是"职业不太匹配"或类似）
    action = suggested_actions[0]
    action_id = action.get("action_id", "")
    action_label = action.get("label", "")

    print(f"\n[用户] 点击选项：'{action_label}'")

    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    payload = {
        "action_id": action_id
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()

            # 检查回复
            assistant_message = data.get("view", {}).get("timeline", [{}])[-1].get("body", "")
            print(f"\n[系统] 回复：")
            print(f"   {assistant_message[:100]}...")

            # 检查是否有候选人卡片
            result_cards = data.get("view", {}).get("timeline", [])
            has_candidates = any(card.get("item_type") == "result_group" for card in result_cards)

            if has_candidates:
                print("✅ 正确：第二轮展示了候选人卡片")

                # 统计候选人数量
                candidate_count = 0
                for card in result_cards:
                    if card.get("item_type") == "result_group":
                        candidates = card.get("cards", [])
                        candidate_count = len(candidates)
                        print(f"   展示了 {candidate_count} 位候选人")

                        # 列出候选人
                        for j, candidate in enumerate(candidates[:3], 1):
                            title = candidate.get("title", "")
                            print(f"      {j}. {title}")
            else:
                print("❌ 错误：第二轮没有展示候选人卡片")
                print("   只返回了文本回复，缺少候选人卡片")

            # 检查phase
            phase = data.get("phase", "")
            print(f"\n[系统] phase: {phase}")

            if phase == "results_shown":
                print("✅ 正确的phase（results_shown）")
            else:
                print(f"❌ 错误的phase（应该是results_shown）")

        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"   错误: {response.text}")

    except Exception as e:
        print(f"❌ 第二轮测试异常: {e}")

# ========== 主测试流程 ==========

def main():
    print("\n开始测试...\n")

    # 1. 创建session
    session_id = create_discovery_session()

    if not session_id:
        print("\n❌ 测试失败：无法创建session")
        print("   请检查Gateway是否正常运行")
        return

    # 2. 第一轮测试
    suggested_actions = test_round_1(session_id)

    # 3. 第二轮测试
    test_round_2(session_id, suggested_actions)

    # 4. 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print("\n如果所有检查项都显示 ✅，说明功能完全正常")
    print("如果有 ❌ 项，说明对应的功能还有问题")
    print("\n测试完成！")

if __name__ == "__main__":
    main()