#!/usr/bin/env python3
"""自动化测试：验证禁用 sync_requester_persona_memory 后的效果

测试目标：
1. 测试搜索条件是否还能正确传递（Agent 自己记）
2. 测试会话结束后的画像沉淀是否还能正常工作

测试场景：
- 场景1：单条件搜索（"北京"）
- 场景2：多条件叠加（"北京" + "26-30岁" + "INTJ"）
- 场景3：主观描述（"性格温柔" + "重视家庭"）

运行方式：
python tests/test_disabled_sync_requester_persona_memory.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径（确保正确）
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Bootstrap paths
from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
ensure_partner_system_roots_on_sys_path(project_root)

# 设置环境变量
os.environ.setdefault("PARTNER_DISCOVERY_DB", "mysql://root@127.0.0.1:3307/her_discovery")
os.environ.setdefault("PERSONA_MEMORY_MYSQL_SOURCE", "mysql://root@127.0.0.1:3307/her_persona")

# 导入 discovery 模块（使用 bootstrap 后的路径）
from partner_discovery_system.discovery_system.storage import (
    InMemoryDiscoveryAgentSessionStore,
    StoredSession,
)
from partner_discovery_system.discovery_system.agent_runtime import (
    run_discovery_turn,
)


async def test_search_conditions():
    """测试1：搜索条件是否还能正确传递

    测试场景：
    - 第1轮：用户说"帮我找北京的"
    - 第5轮：用户说"26-30岁"
    - 第10轮：用户说"改成上海的"

    验证点：
    - Agent 是否记住了搜索条件？
    - working_criteria 是否为空？（应该为空，因为禁用了）
    - 搜索结果是否正确？
    """
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("测试1：搜索条件验证")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 创建测试账号
    test_requester_id = 999999
    test_profile_id = 999999

    # 创建 session
    session_store = InMemoryDiscoveryAgentSessionStore()
    session = session_store.create_session(
        requester_id=test_requester_id,
        profile_id=test_profile_id,
    )

    print(f"创建会话: session_id={session.session_id}")

    # 第1轮：用户说"帮我找北京的"
    print("\n第1轮：用户说'帮我找北京的'")
    try:
        result1 = await run_discovery_turn(
            session,
            user_message="帮我找北京的",
            persona_patch={"cities": ["北京"]},
        )
        print(f"Agent回复: {result1.get('assistant_message')[:100]}...")
        print(f"搜索结果: {len(result1.get('search_response', {}).get('results', []))} 个候选人")
    except Exception as e:
        print(f"第1轮失败: {e}")

    # 检查 working_criteria
    print(f"\n检查 working_criteria:")
    print(f"  session.state['working_criteria'] = {session.state.get('working_criteria', {})}")
    if session.state.get("working_criteria"):
        print("  ❌ working_criteria 有值（禁用没生效？）")
    else:
        print("  ✅ working_criteria 为空（禁用生效）")

    # 第5轮：用户说"26-30岁"
    print("\n第5轮：用户说'26-30岁'")
    try:
        result5 = await run_discovery_turn(
            session,
            user_message="26-30岁",
            persona_patch={"age_min": 26, "age_max": 30},
        )
        print(f"Agent回复: {result5.get('assistant_message')[:100]}...")
        print(f"搜索结果: {len(result5.get('search_response', {}).get('results', []))} 个候选人")
    except Exception as e:
        print(f"第5轮失败: {e}")

    # 再次检查 working_criteria
    print(f"\n检查 working_criteria（应该还是空）:")
    print(f"  session.state['working_criteria'] = {session.state.get('working_criteria', {})}")

    # 第10轮：用户说"改成上海的"
    print("\n第10轮：用户说'改成上海的'")
    try:
        result10 = await run_discovery_turn(
            session,
            user_message="改成上海的",
            persona_patch={"cities": ["上海"]},
        )
        print(f"Agent回复: {result10.get('assistant_message')[:100]}...")
        print(f"搜索结果: {len(result10.get('search_response', {}).get('results', []))} 个候选人")
    except Exception as e:
        print(f"第10轮失败: {e}")

    # 最终检查 working_criteria
    print(f"\n最终检查 working_criteria:")
    print(f"  session.state['working_criteria'] = {session.state.get('working_criteria', {})}")

    # 总结
    print("\n【测试1总结】")
    if session.state.get("working_criteria"):
        print("  ❌ 禁用失败：working_criteria 有值")
        print("  ⚠️  可能原因：")
        print("     - sync_requester_persona_memory 没被完全禁用")
        print("     - 或者其他地方也在写 working_criteria")
    else:
        print("  ✅ 禁用成功：working_criteria 为空")
        print("  ⚠️  验证点：")
        print("     - Agent 是否还能记住搜索条件？（看Agent回复）")
        print("     - 搜索结果是否正确？（看候选人数量）")


async def test_persona沉淀():
    """测试2：会话结束后的画像沉淀是否还能正常工作

    测试场景：
    - 聊天过程中说："我是INTJ人格"（可量化）
    - 聊天过程中说："我性格温柔"（主观描述）
    - 触发会话结束处理

    验证点：
    - persona_part 是否被写入？（应该没有，因为禁用了）
    - conversation_summaries 是否有记录？（应该有）
    - vector_store 是否有向量？（应该有）
    """
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("测试2：画像沉淀验证")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 创建测试账号
    test_requester_id = 999998
    test_profile_id = 999998

    # 创建 session
    session_store = InMemoryDiscoveryAgentSessionStore()
    session = session_store.create_session(
        requester_id=test_requester_id,
        profile_id=test_profile_id,
    )

    print(f"创建会话: session_id={session.session_id}")

    # 聊天过程中说："我是INTJ人格"（可量化）
    print("\n第1轮：用户说'我是INTJ人格'")
    try:
        result1 = await run_discovery_turn(
            session,
            user_message="我是INTJ人格",
            persona_patch={"mbti_type": "INTJ"},
        )
        print(f"Agent回复: {result1.get('assistant_message')[:100]}...")
    except Exception as e:
        print(f"第1轮失败: {e}")

    # 聊天过程中说："我性格温柔"（主观描述）
    print("\n第2轮：用户说'我性格温柔'")
    try:
        result2 = await run_discovery_turn(
            session,
            user_message="我性格温柔",
            persona_patch={},  # 主观描述不在实时 patch 中
        )
        print(f"Agent回复: {result2.get('assistant_message')[:100]}...")
    except Exception as e:
        print(f"第2轮失败: {e}")

    # 触发会话结束处理
    print("\n触发会话结束处理...")
    try:
        from match_domain.session_end_processor import process_session_end

        result = await process_session_end(
            session_id=session.session_id,
            requester_id=test_requester_id,
            profile_id=test_profile_id,
            conversation_type="discovery",
        )
        print(f"会话结束处理结果: {result}")
    except Exception as e:
        print(f"会话结束处理失败: {e}")

    # 检查 persona 数据
    print("\n检查 persona 数据（应该为空，因为禁用了）:")
    try:
        from persona_memory_sync.persona_memory_lib import mysql_connect

        conn = mysql_connect(os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""))
        rows = conn.execute(
            """
            SELECT user_key, mbti_type, updated_at
            FROM user_personas
            WHERE user_key = ?
            """,
            (str(test_requester_id),),
        ).fetchall()

        if rows:
            print(f"  ❌ persona 有数据（禁用没生效？）:")
            for row in rows:
                print(f"     {row}")
        else:
            print("  ✅ persona 为空（禁用生效）")
        conn.close()
    except Exception as e:
        print(f"  查询 persona 失败: {e}")

    # 检查 conversation_summaries
    print("\n检查 conversation_summaries（应该有记录）:")
    try:
        from persona_memory_sync.persona_memory_lib import mysql_connect

        conn = mysql_connect(os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""))
        rows = conn.execute(
            """
            SELECT conversation_id, summary_key, summary_text, created_at
            FROM conversation_summaries
            WHERE requester_id = ?
            ORDER BY created_at DESC
            """,
            (test_requester_id,),
        ).fetchall()

        if rows:
            print(f"  ✅ conversation_summaries 有数据:")
            for row in rows:
                print(f"     conversation_id={row.get('conversation_id')}")
                print(f"     summary_key={row.get('summary_key')}")
                print(f"     summary_text={row.get('summary_text')}")
                print(f"     created_at={row.get('created_at')}")
        else:
            print("  ❌ conversation_summaries 为空（会话结束处理没执行？）")
        conn.close()
    except Exception as e:
        print(f"  查询 conversation_summaries 失败: {e}")

    # 检查 vector_store
    print("\n检查 vector_store（应该有向量）:")
    try:
        from match_domain.vector_store_lite import VectorStoreLite

        store = VectorStoreLite()
        vectors = store.get_user_vectors(test_profile_id)

        if vectors:
            print(f"  ✅ vector_store 有数据:")
            for v in vectors:
                print(f"     vector_type={v.get('vector_type')}")
                print(f"     raw_text={v.get('raw_text')}")
                print(f"     is_active={v.get('is_active')}")
        else:
            print("  ❌ vector_store 为空（向量化流程没执行？）")
    except Exception as e:
        print(f"  查询 vector_store 失败: {e}")

    # 总结
    print("\n【测试2总结】")
    print("  预期结果：")
    print("     - persona 为空（禁用生效）")
    print("     - conversation_summaries 有数据（主观描述被提炼）")
    print("     - vector_store 有数据（向量化流程正常）")


async def main():
    """运行所有测试"""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("自动化测试：验证禁用 sync_requester_persona_memory 后的效果")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("\n测试背景：")
    print("  方案文档说'系统不插手实时对话'")
    print("  禁用 sync_requester_persona_memory 后验证效果")

    # 运行测试
    await test_search_conditions()
    await test_persona沉淀()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("测试完成")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    asyncio.run(main())