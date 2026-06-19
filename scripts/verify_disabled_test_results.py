#!/usr/bin/env python3
"""数据库验证脚本：查看禁用后的测试结果

运行方式：
python scripts/verify_disabled_test_results.py

注意：需要配置数据库连接环境变量
"""

import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def verify_session_state():
    """验证 session.state（working_criteria）"""
    print("\n" + "=" * 60)
    print("【验证1】session.state - working_criteria")
    print("=" * 60)

    # 检查环境变量
    db_dsn = os.environ.get("PARTNER_DISCOVERY_DB")
    if not db_dsn:
        print("⚠️ 没有配置 PARTNER_DISCOVERY_DB，无法查询数据库")
        print("请设置环境变量：export PARTNER_DISCOVERY_DB='mysql://user:pass@host:port/db'")
        return

    print(f"数据库连接: {db_dsn}")

    # 模拟查询（需要真实数据库连接）
    print("\nSQL 查询语句:")
    print("```sql")
    print("SELECT ")
    print("    session_id,")
    print("    requester_id,")
    print("    JSON_EXTRACT(session_state, '$.working_criteria') as working_criteria,")
    print("    created_at")
    print("FROM discovery_agent_sessions")
    print("WHERE requester_id = 你的测试账号ID")
    print("ORDER BY created_at DESC")
    print("LIMIT 5;")
    print("```")

    print("\n预期结果:")
    print("如果禁用生效:")
    print("  ❌ working_criteria 应该为 NULL 或 空对象 {}")
    print("  ❌ 没有搜索条件被记录")
    print("\n如果禁用未生效:")
    print("  ✅ working_criteria 有值（如 {\"cities\": [\"北京\"]}）")
    print("  ✅ 搜索条件被记录")


def verify_persona_data():
    """验证 persona 数据"""
    print("\n" + "=" * 60)
    print("【验证2】user_personas - persona_part")
    print("=" * 60)

    db_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("PARTNER_DISCOVERY_DB")
    if not db_dsn:
        print("⚠️ 没有配置 PERSONA_MEMORY_MYSQL_SOURCE 或 PARTNER_DISCOVERY_DB")
        return

    print(f"数据库连接: {db_dsn}")

    print("\nSQL 查询语句:")
    print("```sql")
    print("SELECT ")
    print("    user_key,")
    print("    mbti_type,")
    print("    smoking,")
    print("    marital_status,")
    print("    updated_at")
    print("FROM user_personas")
    print("WHERE user_key = 你的测试账号requester_id")
    print("ORDER BY updated_at DESC")
    print("LIMIT 5;")
    print("```")

    print("\n预期结果:")
    print("如果禁用生效:")
    print("  ❌ mbti_type 应该为 NULL 或 空值")
    print("  ❌ smoking 应该为 NULL 或 空值")
    print("  ❌ persona_part 没有被写入")
    print("\n如果禁用未生效:")
    print("  ✅ mbti_type 有值（如 'INTJ'）")
    print("  ✅ smoking 有值（如 False）")
    print("  ✅ persona_part 被写入")


def verify_conversation_summaries():
    """验证 conversation_summaries（主观描述提炼）"""
    print("\n" + "=" * 60)
    print("【验证3】conversation_summaries - 主观描述提炼")
    print("=" * 60)

    db_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("PARTNER_DISCOVERY_DB")
    if not db_dsn:
        print("⚠️ 档有配置数据库连接")
        return

    print("\nSQL 查询语句:")
    print("```sql")
    print("SELECT ")
    print("    conversation_id,")
    print("    summary_key,")
    print("    summary_text,")
    print("    created_at")
    print("FROM conversation_summaries")
    print("WHERE requester_id = 你的测试账号ID")
    print("ORDER BY created_at DESC")
    print("LIMIT 10;")
    print("```")

    print("\n预期结果:")
    print("✅ conversation_summaries 应该有记录")
    print("✅ summary_key 包含: personality_traits, values")
    print("✅ summary_text 包含: '性格温柔', '重视家庭'")
    print("✅ 主观描述被正确提炼（不受禁用影响）")


def verify_vector_store():
    """验证 vector_store（向量化存储）"""
    print("\n" + "=" * 60)
    print("【验证4】vector_store - 向量化存储")
    print("=" * 60)

    print("\nPython 查询代码:")
    print("```python")
    print("from match_domain.vector_store import VectorStore")
    print("")
    print("store = VectorStore()")
    print("results = store.get_user_vectors(")
    print("    user_id=你的测试账号profile_id,")
    print("    vector_type='personality_traits',")
    print(")")
    print("print(f'向量数据: {results}')")
    print("```")

    print("\n预期结果:")
    print("✅ vector_store 应该有向量数据")
    print("✅ raw_text 包含: '性格温柔'")
    print("✅ is_active = True")
    print("✅ 向量化流程正常（不受禁用影响）")


def verify_logs():
    """验证日志（禁用是否生效）"""
    print("\n" + "=" * 60)
    print("【验证5】日志 - 禁用是否生效")
    print("=" * 60)

    print("\n日志查询命令:")
    print("```bash")
    print("# 查看禁用日志")
    print("grep '临时禁用' /path/to/discovery_system.log")
    print("")
    print("# 查看最近日志")
    print("tail -100 /path/to/discovery_system.log | grep 'sync_requester_persona_memory'")
    print("")
    print("# 查看搜索日志")
    print("grep '搜索开始' /path/to/discovery_system.log")
    print("```")

    print("\n预期日志内容:")
    print("✅ 应该看到: '【临时禁用】sync_requester_persona_memory 被禁用'")
    print("✅ 应该看到: session_id, requester_id, patch_keys")
    print("✅ 禁用日志表明代码改动生效")


def run_all_verifications():
    """运行所有验证"""
    print("\n" + "=" * 60)
    print("数据库验证脚本 - 查看禁用后的测试结果")
    print("=" * 60)

    print("\n⚠️ 注意:")
    print("1. 需要配置数据库连接环境变量")
    print("2. 需要知道测试账号的 requester_id 和 profile_id")
    print("3. 需要前端测试后再验证数据库")

    verify_session_state()
    verify_persona_data()
    verify_conversation_summaries()
    verify_vector_store()
    verify_logs()

    print("\n" + "=" * 60)
    print("【下一步】")
    print("=" * 60)

    print("\n1. 前端测试:")
    print("   - 打开对话界面")
    print("   - 按照测试场景进行对话")
    print("   - 观察Agent行为和搜索结果")

    print("\n2. 数据库验证:")
    print("   - 配置数据库连接")
    print("   - 运行SQL查询脚本")
    print("   - 查看测试结果")

    print("\n3. 日志验证:")
    print("   - 查看禁用日志")
    print("   - 确认禁用生效")

    print("\n4. 对比结果:")
    print("   - 对比禁用前后的差异")
    print("   - 判断禁用是否影响功能")
    print("   - 记录测试结果")


if __name__ == "__main__":
    run_all_verifications()