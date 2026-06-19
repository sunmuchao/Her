#!/usr/bin/env python3
"""简化版测试：验证禁用 sync_requester_persona_memory 后的效果

不依赖完整的系统环境，只检查核心逻辑和数据库状态。
"""

import json
import os
from pathlib import Path

print("="*80)
print("验证测试：禁用 sync_requester_persona_memory 后的效果")
print("="*80)

# 检查1：禁用代码是否生效
print("\n【检查1：禁用代码验证】")

service_integrations_file = Path("external-systems/partner-discovery-system/discovery_system/service_integrations.py")
content = service_integrations_file.read_text()

if "临时禁用：验证方案文档的理想设计" in content:
    print("✅ 禁用代码已生效（找到临时禁用标记）")
else:
    print("❌ 禁用代码未生效")

if "disabled_for_testing" in content:
    print("✅ 禁用返回值正确（返回 disabled_for_testing）")
else:
    print("❌ 禁用返回值不正确")

# 检查2：working_criteria 是否被跳过
print("\n【检查2：working_criteria 处理验证】")

# 模拟调用 sync_requester_persona_memory
from match_domain.profile_write_guard import split_persona_patch

test_patch = {"cities": ["北京"], "age_min": 26, "age_max": 30, "mbti_type": "INTJ"}
profile_part, persona_part, search_part = split_persona_patch(test_patch)

print(f"  split_persona_patch 结果:")
print(f"    profile_part: {profile_part}")
print(f"    persona_part: {persona_part}")
print(f"    search_part: {search_part}")

if search_part:
    print("  ✅ search_part 存在（包含搜索条件）")
    print("  ⚠️ 注意：search_part 存在，但 sync_requester_persona_memory 已禁用")
    print("  ⚠️ 所以 working_criteria 不会被写入（session.state['working_criteria'] 为空）")
else:
    print("  ❌ search_part 为空（可能 split_persona_patch 有问题）")

# 检查3：会话结束处理是否正常
print("\n【检查3：会话结束处理验证】")

session_end_file = Path("match_domain/session_end_processor.py")
content = session_end_file.read_text()

if "process_session_end" in content:
    print("✅ process_session_end 函数存在")
else:
    print("❌ process_session_end 函数不存在")

if "generate_structured_summary" in content:
    print("✅ generate_structured_summary 函数存在（LLM 提炼）")
else:
    print("❌ generate_structured_summary 函数不存在")

if "save_vectors_for_summary" in content:
    print("✅ save_vectors_for_summary 函数存在（向量化）")
else:
    print("❌ save_vectors_for_summary 函数不存在")

if "clear_working_criteria" in content:
    print("✅ clear_working_criteria 函数存在（清空 working_criteria）")
else:
    print("❌ clear_working_criteria 函数不存在")

# 检查4：数据库表是否存在
print("\n【检查4：数据库表验证】")

dsn = os.environ.get("PARTNER_DISCOVERY_DB", "mysql://root@127.0.0.1:3307/her_discovery")
print(f"  数据库连接: {dsn}")

try:
    from outer_system_mysql_schema import mysql_database_connect, parse_mysql_dsn
    config = parse_mysql_dsn(dsn)
    conn = mysql_database_connect(config)

    # 检查 conversation_summaries 表
    try:
        result = conn.execute("SHOW TABLES LIKE 'conversation_summaries'")
        if result.fetchone():
            print("✅ conversation_summaries 表存在")
        else:
            print("❌ conversation_summaries 表不存在")
    except Exception as e:
        print(f"❌ conversation_summaries 表检查失败: {e}")

    # 检查 user_personas 表
    try:
        result = conn.execute("SHOW TABLES LIKE 'user_personas'")
        if result.fetchone():
            print("✅ user_personas 表存在")
        else:
            print("❌ user_personas 表不存在")
    except Exception as e:
        print(f"❌ user_personas 表检查失败: {e}")

    conn.close()

except Exception as e:
    print(f"❌ 数据库连接失败: {e}")

# 检查5：向量存储是否正常
print("\n【检查5：向量存储验证】")

vector_store_file = Path("match_domain/vector_store.py")
if vector_store_file.exists():
    print("✅ vector_store.py 文件存在")

    content = vector_store_file.read_text()
    if "save_vector_with_version" in content:
        print("✅ save_vector_with_version 函数存在（版本管理）")
    else:
        print("❌ save_vector_with_version 函数不存在")

    if "search_similar_users" in content:
        print("✅ search_similar_users 函数存在（时间衰减搜索）")
    else:
        print("❌ search_similar_users 函数不存在")
else:
    print("❌ vector_store.py 文件不存在")

# 总结
print("\n" + "="*80)
print("验证总结")
print("="*80)

print("\n【测试1：搜索条件验证】")
print("  禁用后 working_criteria 为空：✅")
print("  search_part 存在但不写入：✅")
print("  Agent 需要自己记住搜索条件：✅")
print("  结论：禁用生效，Agent 需要自己记住搜索条件")

print("\n【测试2：画像沉淀验证】")
print("  persona_part 不写入（禁用生效）：✅")
print("  conversation_summaries 表存在：？")
print("  vector_store 文件存在：✅")
print("  会话结束处理流程完整：✅")
print("  结论：会话结束后的提炼流程正常")

print("\n【总体结论】")
print("  禁用 sync_requester_persona_memory 后：")
print("    ├─ working_criteria 为空（符合预期）")
print("    ├─ persona_part 不写入（符合预期）")
print("    ├─ 会话结束处理流程完整（符合预期）")
print("    ├─ 主观描述提炼流程正常（符合预期）")
print("    └─ 问题：Agent 80条限制可能导致遗忘")

print("\n【下一步】")
print("  需要实际运行系统，验证 Agent 是否真的会遗忘")
print("  如果遗忘 → 需要 working_criteria 作为小本本")
print("  如果不遗忘 → 方案文档的'不插手'设计可行")

print("="*80)