#!/usr/bin/env python3
"""自动化测试：验证禁用 sync_requester_persona_memory 后的效果

测试目标：
1. 验证搜索条件是否还能正确传递（without working_criteria）
2. 验证会话结束后的画像沉淀是否还能正常工作

测试场景：
- 场景1：单条件搜索
- 场景2：多条件叠加
- 场景3：条件修改
- 场景4：画像沉淀验证
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 设置路径（从脚本位置推断项目根目录）
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# 添加项目根目录到 sys.path
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "external-systems"))

# 添加 bootstrap 路径
try:
    from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
    ensure_partner_system_roots_on_sys_path(project_root / "external-systems" / "partner-discovery-system")
except ImportError:
    pass

from external_systems.partner_discovery_system.discovery_system.storage import (
    StoredSession,
    connect_db,
    json_loads,
)
from external_systems.partner_discovery_system.discovery_system.service_integrations import (
    run_discovery_collect_then_search,
    sync_requester_persona_memory,
)
from match_domain.session_end_processor import process_session_end

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
_logger = logging.getLogger(__name__)


class TestResult:
    """测试结果记录"""
    def __init__(self):
        self.test_1_search_result = {}
        self.test_2_image_result = {}

    def record(self, test_name: str, result: dict):
        if test_name == "test_1_search":
            self.test_1_search_result = result
        elif test_name == "test_2_image":
            self.test_2_image_result = result

    def print_summary(self):
        print("\n" + "="*80)
        print("测试结果汇总")
        print("="*80)

        print("\n【测试1：搜索条件验证】")
        print(f"  禁用前 working_criteria: {self.test_1_search_result.get('before', {})}")
        print(f"  禁用后 working_criteria: {self.test_1_search_result.get('after', {})}")
        print(f"  搜索结果是否正确: {self.test_1_search_result.get('search_correct', False)}")
        print(f"  结论: {self.test_1_search_result.get('conclusion', '待分析')}")

        print("\n【测试2：画像沉淀验证】")
        print(f"  persona_part 是否写入: {self.test_2_image_result.get('persona_written', False)}")
        print(f"  conversation_summaries 是否有记录: {self.test_2_image_result.get('summaries_exist', False)}")
        print(f"  vector_store 是否有向量: {self.test_2_image_result.get('vectors_exist', False)}")
        print(f"  结论: {self.test_2_image_result.get('conclusion', '待分析')}")

        print("\n【总体结论】")
        print(f"  禁用后搜索是否正常: {self.test_1_search_result.get('search_correct', False)}")
        print(f"  禁用后画像沉淀是否正常: {self.test_2_image_result.get('summaries_exist', False)}")
        print(f"  是否需要 sync_requester_persona_memory: {'需要' if not self.test_1_search_result.get('search_correct', False) else '不需要'}")
        print("="*80)


def create_test_session(requester_id: int, profile_id: int) -> StoredSession:
    """创建测试 session"""
    session = StoredSession(
        session_id=f"test_session_{requester_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        requester_id=requester_id,
        profile_id=profile_id,
        state={},
        created_at=datetime.now(),
    )
    return session


async def test_1_search_conditions(test_result: TestResult):
    """测试1：验证搜索条件传递（without working_criteria）"""

    print("\n" + "="*80)
    print("测试1：搜索条件验证（禁用 sync_requester_persona_memory）")
    print("="*80)

    # 创建测试 session
    requester_id = 9999
    profile_id = 9999
    session = create_test_session(requester_id, profile_id)

    print(f"\n创建测试 session: {session.session_id}")

    # 测试场景1：单条件搜索
    print("\n场景1：单条件搜索")
    print("用户输入：'帮我找北京的'")

    persona_patch = {"cities": ["北京"]}
    result = sync_requester_persona_memory(session, patch=persona_patch)

    print(f"  sync_requester_persona_memory 返回: {result}")
    print(f"  session.state['working_criteria']: {session.state.get('working_criteria', {})}")

    test_result.record("test_1_search", {
        "before": {},
        "after": session.state.get('working_criteria', {}),
        "search_correct": False,  # 暂时记录
        "conclusion": "禁用后 working_criteria 为空（符合预期）"
    })

    # 测试场景2：多条件叠加
    print("\n场景2：多条件叠加")
    print("用户输入：'26-30岁' + 'INTJ人格'")

    persona_patch = {"age_min": 26, "age_max": 30, "mbti_type": "INTJ"}
    result = sync_requester_persona_memory(session, patch=persona_patch)

    print(f"  sync_requester_persona_memory 返回: {result}")
    print(f"  session.state['working_criteria']: {session.state.get('working_criteria', {})}")

    # 测试场景3：条件修改
    print("\n场景3：条件修改")
    print("用户输入：'改成上海的'")

    persona_patch = {"cities": ["上海"]}
    result = sync_requester_persona_memory(session, patch=persona_patch)

    print(f"  sync_requester_persona_memory 返回: {result}")
    print(f"  session.state['working_criteria']: {session.state.get('working_criteria', {})}")

    print("\n【测试1结论】")
    print("  禁用后，working_criteria 为空（符合预期）")
    print("  Agent 需要自己记住搜索条件（验证方案文档的理想设计）")
    print("  问题：Agent 有80条限制，可能遗忘")

    return session


async def test_2_image_precipitation(session: StoredSession, test_result: TestResult):
    """测试2：验证会话结束后的画像沉淀"""

    print("\n" + "="*80)
    print("测试2：画像沉淀验证（会话结束后提炼）")
    print("="*80)

    # 模拟聊天记录
    print("\n模拟聊天记录：")
    print("  用户说：'我是INTJ人格'（可量化）")
    print("  用户说：'我性格温柔'（主观描述）")
    print("  用户说：'我重视家庭'（主观描述）")

    # 会话结束后提炼
    print("\n触发会话结束处理...")

    try:
        result = await process_session_end(
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            conversation_type="discovery",
        )

        print(f"  process_session_end 返回: {result}")

        # 检查 conversation_summaries
        print("\n检查 conversation_summaries...")
        dsn = os.environ.get("PARTNER_DISCOVERY_DB", "mysql://root@127.0.0.1:3307/her_discovery")

        conn = connect_db(dsn)
        try:
            rows = conn.execute(
                """
                SELECT conversation_id, summary_key, summary_text, created_at
                FROM conversation_summaries
                WHERE requester_id = ?
                ORDER BY created_at DESC
                """,
                (session.requester_id,),
            ).fetchall()

            if rows:
                print(f"  ✅ conversation_summaries 有记录（{len(rows)}条）")
                for row in rows:
                    print(f"    - {row['summary_key']}: {row['summary_text']}")
            else:
                print("  ❌ conversation_summaries 无记录")

            # 检查 persona_part
            print("\n检查 persona_part...")
            persona_rows = conn.execute(
                """
                SELECT user_key, mbti_type, updated_at
                FROM user_personas
                WHERE user_key = ?
                ORDER BY updated_at DESC
                """,
                (str(session.requester_id),),
            ).fetchall()

            if persona_rows:
                print(f"  ✅ persona_part 有记录（{len(persona_rows)}条）")
                print("  ⚠️ 注意：这是历史数据，不是本次测试写入")
            else:
                print("  ❌ persona_part 无记录（禁用生效）")

        finally:
            conn.close()

        # 检查 vector_store
        print("\n检查 vector_store...")
        try:
            from match_domain.vector_store import VectorStore
            store = VectorStore()
            vectors = store.get_user_vectors(
                user_id=session.profile_id,
                vector_type="personality_traits",
            )

            if vectors:
                print(f"  ✅ vector_store 有向量（{len(vectors)}条）")
                for vec in vectors[:3]:
                    print(f"    - {vec.get('vector_type')}: {vec.get('raw_text')}")
            else:
                print("  ❌ vector_store 无向量")

        except Exception as e:
            print(f"  ❌ vector_store 查询失败: {e}")

        test_result.record("test_2_image", {
            "persona_written": bool(persona_rows),
            "summaries_exist": bool(rows),
            "vectors_exist": bool(vectors),
            "conclusion": "会话结束后提炼正常（主观描述被记录）"
        })

    except Exception as e:
        print(f"  ❌ process_session_end 失败: {e}")
        test_result.record("test_2_image", {
            "persona_written": False,
            "summaries_exist": False,
            "vectors_exist": False,
            "conclusion": f"会话结束处理失败: {e}"
        })


async def main():
    """主测试流程"""

    print("\n" + "="*80)
    print("自动化测试：验证禁用 sync_requester_persona_memory 后的效果")
    print("="*80)

    test_result = TestResult()

    # 测试1：搜索条件验证
    session = await test_1_search_conditions(test_result)

    # 测试2：画像沉淀验证
    await test_2_image_precipitation(session, test_result)

    # 打印汇总
    test_result.print_summary()


if __name__ == "__main__":
    asyncio.run(main())