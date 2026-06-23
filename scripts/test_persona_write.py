#!/usr/bin/env python3
"""画像写入验证测试：检查会话结束后画像是否正确更新

测试流程：
1. 创建新会话并对话
2. 用户在对话中透露个人信息（MBTI、抽烟、性格特质等）
3. 结束会话（等待30秒触发会话结束处理）
4. 手动检查数据库中的画像数据是否正确写入

验证点：
- 可量化字段：MBTI、抽烟喝酒状态、城市等
- 不可量化字段：性格特质、价值观、择偶期望等
- 向量库：是否生成向量
- 溯源能力：是否有session_id和evidence_text
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
        "requester_id": 10030,  # 测试用户ID
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

            assistant_message = ""
            for item in timeline:
                if item.get("item_type") == "assistant_message":
                    assistant_message = item.get("body", "")
                    break

            print(f"\n【Agent回复】{assistant_message[:100]}...")
            return {"assistant_message": assistant_message}
        else:
            print(f"❌ 响应失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 响应异常: {e}")
        return None

async def check_persona_data(user_id: int, session_id: str):
    """检查画像数据是否写入"""
    print("\n" + "=" * 80)
    print("检查画像数据写入")
    print("=" * 80)

    try:
        conn = await asyncpg.connect(DB_DSN)

        # 检查可量化字段（user_persona_observations）
        print("\n【1】检查可量化字段（user_persona_observations）")
        rows = await conn.fetch("""
            SELECT field_name, field_value, source_type, confidence_score, evidence_text, conversation_ref
            FROM user_persona_observations
            WHERE user_id = $1 AND conversation_ref = $2
            ORDER BY created_at DESC
        """, user_id, session_id)

        if rows:
            print(f"✅ 找到 {len(rows)} 条画像记录:")
            for row in rows:
                print(f"   - {row['field_name']}: {row['field_value']}")
                print(f"     source_type: {row['source_type']}")
                print(f"     confidence_score: {row['confidence_score']}")
                print(f"     evidence_text: {row['evidence_text'][:50]}...")
        else:
            print("❌ 未找到画像记录")
            print("   可能原因：会话结束处理未触发、写入逻辑失败")

        # 检查不可量化字段（conversation_summaries）
        print("\n【2】检查不可量化字段（conversation_summaries）")
        rows = await conn.fetch("""
            SELECT summary_key, summary_text, vector_status, created_at
            FROM conversation_summaries
            WHERE conversation_id = $1
            ORDER BY created_at DESC
        """, session_id)

        if rows:
            print(f"✅ 找到 {len(rows)} 条摘要记录:")
            for row in rows:
                print(f"   - {row['summary_key']}: {row['summary_text'][:50]}...")
                print(f"     vector_status: {row['vector_status']}")
        else:
            print("❌ 未找到摘要记录")
            print("   可能原因：LLM提炼失败、写入逻辑失败")

        # 检查向量库（user_vectors）
        print("\n【3】检查向量库（user_vectors）")
        rows = await conn.fetch("""
            SELECT vector_type, raw_text, vector_version, is_active, created_at
            FROM user_vectors
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 10
        """, user_id)

        if rows:
            print(f"✅ 找到 {len(rows)} 条向量记录:")
            for row in rows:
                print(f"   - {row['vector_type']}: {row['raw_text'][:50]}...")
                print(f"     vector_version: {row['vector_version']}")
                print(f"     is_active: {row['is_active']}")
        else:
            print("❌ 未找到向量记录")
            print("   可能原因：向量化失败、写入逻辑失败")

        await conn.close()

    except Exception as e:
        print(f"❌ 数据库查询异常: {e}")
        print("   可能原因：数据库连接失败、表不存在")

def main():
    print("\n" + "=" * 80)
    print("画像写入验证测试")
    print("=" * 80)

    # 创建新会话
    session_id = create_session()

    if not session_id:
        print("\n❌ 无法创建会话，测试终止")
        return

    print("\n开始对话测试...")
    print("=" * 80)

    # 第1轮：透露MBTI、抽烟等信息
    print("\n【第1轮】透露可量化信息")
    response = send_turn(session_id, "我26岁，住在苏州，INTJ类型，不抽烟，偶尔喝酒")

    time.sleep(5)

    # 第2轮：透露性格特质、价值观等
    print("\n【第2轮】透露不可量化信息")
    response = send_turn(session_id, "我性格比较内向、温柔，不喜欢社交。我很重视家庭，希望找个同样重视家庭的人")

    time.sleep(5)

    # 第3轮：透露择偶期望
    print("\n【第3轮】透露择偶期望")
    response = send_turn(session_id, "我希望对方成熟稳重，有责任心，能给我安全感")

    print("\n" + "=" * 80)
    print("对话完成")
    print("=" * 80)

    print("\n【等待会话结束处理】")
    print("等待30秒，让系统完成会话结束处理...")
    time.sleep(30)

    print("\n【检查画像数据】（手动验证）")
    print(f"User ID: 10030")
    print(f"Session ID: {session_id}")

    print("\n【手动检查建议】")
    print("=" * 80)
    print("等待30秒后，执行以下SQL查询验证画像写入：")
    print("=" * 80)
    print("\n1. 检查可量化字段（user_persona_observations）:")
    print(f"   SELECT field_name, field_value, source_type, confidence_score, evidence_text")
    print(f"   FROM user_persona_observations")
    print(f"   WHERE user_id=10030 AND conversation_ref='{session_id}';")
    print("\n   预期结果：")
    print("   - field_name: mbti_type, smoking, drinking, city, age")
    print("   - source_type: strong_inference")
    print("   - confidence_score: 85")
    print("   - evidence_text: '我26岁，住在苏州，INTJ类型，不抽烟，偶尔喝酒'")

    print("\n2. 检查不可量化字段（conversation_summaries）:")
    print(f"   SELECT summary_key, summary_text, vector_status")
    print(f"   FROM conversation_summaries")
    print(f"   WHERE conversation_id='{session_id}';")
    print("\n   预期结果：")
    print("   - summary_key: personality_traits, values, partner_expectation")
    print("   - summary_text: '性格内向、温柔', '重视家庭', '成熟稳重、有责任心'")
    print("   - vector_status: done")

    print("\n3. 检查向量库（user_vectors）:")
    print(f"   SELECT vector_type, raw_text, vector_version, is_active")
    print(f"   FROM user_vectors")
    print(f"   WHERE user_id=10030 ORDER BY created_at DESC LIMIT 10;")
    print("\n   预期结果：")
    print("   - vector_type: personality_traits, values, partner_expectation")
    print("   - vector_version: 1")
    print("   - is_active: True")

    print("\n4. 检查Gateway日志:")
    print("   tail -f /tmp/gateway.log | grep 'session_end'")
    print("\n   关键日志：")
    print("   - '会话结束处理开始'")
    print("   - 'LLM提炼结构化摘要'")
    print("   - '写入画像表'")
    print("   - '写入摘要表'")
    print("   - '生成向量'")
    print("   - '会话结束处理完成'")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    print("\n【测试总结】")
    print("验证画像写入的完整性：")
    print("1. 可量化字段（MBTI、抽烟、年龄、城市）是否写入画像表")
    print("2. 不可量化字段（性格特质、价值观、择偶期望）是否写入摘要表+向量库")
    print("3. 溯源能力（是否有session_id和evidence_text）")
    print("4. 向量状态（是否生成向量、版本号是否正确）")

    print("\n【已知问题】")
    print("- 会话结束处理可能未触发（需要手动触发或定时检查）")
    print("- LLM提炼可能失败（需要检查日志）")
    print("- 向量化可能失败（需要检查向量库日志）")

if __name__ == "__main__":
    main()