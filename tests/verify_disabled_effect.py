"""简单验证：直接查询数据库验证禁用效果

验证目标：
1. 查看最近一次对话后的 persona 数据（应该为空，因为禁用了）
2. 查看最近一次对话后的 conversation_summaries 数据（应该有）
3. 查看最近一次对话后的 session.state 数据（working_criteria 应该为空）

运行方式：
python tests/verify_disabled_effect.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ.setdefault("PARTNER_DISCOVERY_DB", "mysql://root@127.0.0.1:3307/her_discovery")
os.environ.setdefault("PERSONA_MEMORY_MYSQL_SOURCE", "mysql://root@127.0.0.1:3307/her_persona")


def verify_database_state():
    """查询数据库验证禁用效果"""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("数据库验证：sync_requester_persona_memory 禁用后的效果")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 1. 查询最近的 persona 数据
    print("\n【验证1】查询最近写入的 persona 数据")
    print("预期：应该为空（因为 sync_requester_persona_memory 禁用了）")
    try:
        from persona_memory_sync.persona_memory_lib import mysql_connect

        conn = mysql_connect(os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""))
        rows = conn.execute(
            """
            SELECT user_key, mbti_type, smoking, updated_at
            FROM user_personas
            ORDER BY updated_at DESC
            LIMIT 5
            """
        ).fetchall()

        if rows:
            print(f"\n❌ 发现 persona 数据（最近5条）:")
            for row in rows:
                print(f"  user_key={row.get('user_key')}, mbti_type={row.get('mbti_type')}, updated_at={row.get('updated_at')}")
            print("\n结论：禁用可能没生效，或者这些是历史数据")
        else:
            print("\n✅ persona 数据为空")
            print("结论：禁用生效，没有新的 persona 数据写入")
        conn.close()
    except Exception as e:
        print(f"\n查询失败: {e}")

    # 2. 查询最近的 conversation_summaries 数据
    print("\n【验证2】查询最近写入的 conversation_summaries 数据")
    print("预期：应该有数据（会话结束后的提炼流程应该正常）")
    try:
        from persona_memory_sync.persona_memory_lib import mysql_connect

        conn = mysql_connect(os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""))
        rows = conn.execute(
            """
            SELECT conversation_id, summary_key, summary_text, created_at
            FROM conversation_summaries
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()

        if rows:
            print(f"\n✅ 发现 conversation_summaries 数据（最近10条）:")
            for row in rows:
                print(f"  conversation_id={row.get('conversation_id')}, summary_key={row.get('summary_key')}, summary_text={row.get('summary_text')[:50]}")
            print("\n结论：会话结束后的提炼流程正常")
        else:
            print("\n❌ conversation_summaries 数据为空")
            print("结论：会话结束后的提炼流程没执行，或者表不存在")
        conn.close()
    except Exception as e:
        print(f"\n查询失败: {e}")

    # 3. 查询最近的 session.state 数据（working_criteria）
    print("\n【验证3】查询最近写入的 session.state 数据")
    print("预期：working_criteria 应该为空（因为 sync_requester_persona_memory 禁用了）")
    try:
        from partner_discovery_system.discovery_system.storage import connect_db

        conn = connect_db(os.environ.get("PARTNER_DISCOVERY_DB", ""))
        rows = conn.execute(
            """
            SELECT session_id, session_state, created_at
            FROM discovery_agent_sessions
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()

        if rows:
            print(f"\n发现 session 数据（最近5条）:")
            import json
            for row in rows:
                session_state = json.loads(row.get('session_state') or '{}')
                working_criteria = session_state.get('working_criteria', {})
                print(f"  session_id={row.get('session_id')}")
                print(f"  working_criteria={working_criteria}")
                print(f"  created_at={row.get('created_at')}")

                if working_criteria:
                    print("  ❌ working_criteria 有值（禁用没生效？）")
                else:
                    print("  ✅ working_criteria 为空（禁用生效）")
        else:
            print("\n❌ session 数据为空")
            print("结论：没有对话数据，无法验证")
        conn.close()
    except Exception as e:
        print(f"\n查询失败: {e}")

    # 4. 查询最近的 vector_store 数据
    print("\n【验证4】查询最近写入的 vector_store 数据")
    print("预期：应该有数据（向量化流程应该正常）")
    try:
        from match_domain.vector_store_lite import VectorStoreLite

        store = VectorStoreLite()
        # 查询最近的向量数据（通过所有用户）
        # 由于 Milvus Lite 的限制，我们只能查询特定用户
        print("\n尝试查询 vector_store...")
        print("（由于 Milvus Lite 的限制，无法查询所有用户，需要指定 user_id）")
        print("结论：需要在有实际数据后再验证")

    except Exception as e:
        print(f"\n查询失败: {e}")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("验证完成")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    verify_database_state()