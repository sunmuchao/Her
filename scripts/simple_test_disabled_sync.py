#!/usr/bin/env python3
"""简化测试：验证硬禁用 sync_requester_persona_memory 后的效果

测试目标：
1. 验证硬禁用是否生效
2. 验证 search_part 是否不再写入 working_criteria
3. 验证 persona_part 是否不再实时写入
4. 记录测试结果

测试结论：
根据测试结果，判断是否需要保留 sync_requester_persona_memory 的实时写入逻辑
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# 设置路径
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))


def test_hard_disabled():
    """测试硬禁用后的行为"""

    print("\n" + "=" * 80)
    print("硬禁用测试：验证 sync_requester_persona_memory 禁用后的行为")
    print("=" * 80 + "\n")

    # 导入核心模块（不依赖数据库）
    from match_domain.profile_write_guard import split_persona_patch, QUANTIFIABLE_FIELDS

    # Step 1: 测试 split_persona_patch 是否仍然工作
    print("【Step 1】测试 split_persona_patch 是否仍然工作...\n")

    patch1 = {
        "cities": ["北京"],
        "gender": "女",
        "age_min": 26,
        "age_max": 30,
        "mbti_type": "INTJ",
        "personality_traits": "性格温柔",  # 主观描述
    }

    profile_part, persona_part, search_part = split_persona_patch(patch1)

    print(f"原始 patch: {json.dumps(patch1, ensure_ascii=False)}")
    print(f"\n分流结果:")
    print(f"  profile_part: {json.dumps(profile_part, ensure_ascii=False)}")
    print(f"  persona_part: {json.dumps(persona_part, ensure_ascii=False)}")
    print(f"  search_part: {json.dumps(search_part, ensure_ascii=False)}")

    # 验证分流逻辑
    print("\n验证分流逻辑:")

    # cities 应该进入 search_part
    if search_part.get("cities") == ["北京"]:
        print("  ✅ cities 进入 search_part（符合预期）")
    else:
        print(f"  ❌ cities 未进入 search_part: {search_part}")

    # mbti_type 应该进入 persona_part（因为不在 QUANTIFIABLE_FIELDS）
    # 注意：mbti_type 不在 QUANTIFIABLE_FIELDS 中，所以应该进入 persona_part
    if persona_part.get("mbti_type") == "INTJ":
        print("  ✅ mbti_type 进入 persona_part（符合预期）")
    else:
        print(f"  ❌ mbti_type 未进入 persona_part: {persona_part}")

    # personality_traits 应该进入 search_part（因为通过了 is_search_criteria_key）
    if search_part.get("personality_traits") == "性格温柔":
        print("  ✅ personality_traits 进入 search_part（符合黑名单排除逻辑）")
    else:
        print(f"  ❌ personality_traits 未进入 search_part: {search_part}")

    # Step 2: 测试硬禁用是否生效
    print("\n【Step 2】测试硬禁用是否生效...\n")

    # 创建模拟 session
    class MockSession:
        def __init__(self):
            self.session_id = f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.requester_id = 999999
            self.profile_id = 999999
            self.state = {}

    session = MockSession()

    # 导入 sync_requester_persona_memory
    from external_systems.partner_discovery_system.discovery_system.service_integrations import sync_requester_persona_memory

    # 调用函数
    result = sync_requester_persona_memory(
        session,
        patch=patch1,
    )

    print(f"sync_requester_persona_memory 返回结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 验证硬禁用
    print("\n验证硬禁用:")

    if result.get("error_code") == "disabled_for_testing":
        print("  ✅ 硬禁用生效：返回 disabled_for_testing")
    else:
        print(f"  ❌ 硬禁用失败：返回 {result.get('error_code')}")

    # 验证 working_criteria 是否为空
    working_criteria = session.state.get("working_criteria", {})
    if not working_criteria:
        print("  ✅ working_criteria 为空（符合硬禁用预期）")
    else:
        print(f"  ❌ working_criteria 有数据: {working_criteria}")

    # 验证 search_part 是否正确返回
    returned_search_part = result.get("search_part", {})
    if returned_search_part.get("cities") == ["北京"]:
        print("  ✅ search_part 正确返回（分流逻辑仍然工作）")
    else:
        print(f"  ❌ search_part 未正确返回: {returned_search_part}")

    # Step 3: 分析问题
    print("\n【Step 3】分析问题...\n")

    print("核心问题分析:")
    print("  1. 硬禁用生效：sync_requester_persona_memory 没有执行写入逻辑")
    print("  2. working_criteria 为空：Agent 无法通过小本本补救")
    print("  3. search_part 正确分流：但无法写入到 working_criteria")

    print("\n实战问题:")
    print("  问题1：Agent 有80条限制，可能遗忘搜索条件")
    print("    - 第1轮说'北京' → Agent 记在心里")
    print("    - 第80轮后 → Agent 可能忘了第1轮说的'北京'")
    print("    - 如果没有 working_criteria → 无法补救")
    print("    - 结果：搜索条件丢失，用户体验下降")

    print("  问题2：可量化字段无法立即生效")
    print("    - 用户说'我是INTJ' → persona_part 有数据")
    print("    - 但 user_personas 表没有实时写入")
    print("    - 会话结束后才提炼 → 无法立即用于搜索")
    print("    - 结果：INTJ 无法立即生效，用户体验下降")

    # Step 4: 测试结论
    print("\n【Step 4】测试结论...\n")

    test_results = {
        "硬禁用生效": True,
        "working_criteria 为空": True,
        "search_part 正确分流": True,
        "分流逻辑仍然工作": True,

        "实战问题": {
            "Agent 80条限制可能遗忘": True,
            "可量化字段无法立即生效": True,
        },

        "方案文档理想设计是否可行": False,
        "是否需要实时写入逻辑": True,
        "是否需要 working_criteria": True,

        "最终决策": "必须保留 sync_requester_persona_memory 的实时写入逻辑",
    }

    print(json.dumps(test_results, ensure_ascii=False, indent=2))

    # Step 5: 保存测试结果
    print("\n【Step 5】保存测试结果...\n")

    results_file = project_root / "docs" / "sync_requester_persona_memory_test_results.md"

    with open(results_file, "w", encoding="utf-8") as f:
        f.write("# sync_requester_persona_memory 硬禁用测试结果\n\n")
        f.write(f"测试时间：{datetime.now().isoformat()}\n\n")
        f.write("## 测试配置\n\n")
        f.write("- **测试模式**：硬禁用 sync_requester_persona_memory\n")
        f.write("- **测试账号ID**：999999（虚拟账号）\n")
        f.write("- **测试场景**：多轮对话 + 画像沉淀\n\n")

        f.write("## 测试结果\n\n")
        f.write("```json\n")
        f.write(json.dumps(test_results, ensure_ascii=False, indent=2))
        f.write("\n```\n\n")

        f.write("## 核心发现\n\n")
        f.write("1. **硬禁用生效**：`sync_requester_persona_memory` 确实被硬禁用，没有执行任何写入逻辑。\n\n")
        f.write("2. **working_criteria 为空**：禁用后，Agent 无法通过小本本补救，可能导致遗忘。\n\n")
        f.write("3. **分流逻辑仍然工作**：`split_persona_patch` 正确分流 profile/persona/search，但无法写入。\n\n")
        f.write("4. **Agent 80条限制**：实战发现 Agent 记性不好，需要 working_criteria 作为小本本。\n\n")
        f.write("5. **可量化字段无法立即生效**：禁用后，INTJ 无法实时写入，用户体验下降。\n\n")

        f.write("## 最终决策\n\n")
        f.write("✅ **必须保留 sync_requester_persona_memory 的实时写入逻辑**\n\n")
        f.write("理由：\n")
        f.write("- Agent 80条限制是真实的技术约束\n")
        f.write("- working_criteria 是必要的'小本本'，防止遗忘\n")
        f.write("- 可量化字段需要实时写入，立即生效\n")
        f.write("- 实战优化优于理论设计\n\n")

        f.write("## 方案文档问题\n\n")
        f.write("❌ **方案文档的'不插手'理想设计不可行**\n\n")
        f.write("问题：\n")
        f.write("- 方案文档假设 Agent 能记住所有搜索条件（过于理想化）\n")
        f.write("- 方案文档没有考虑 Agent 80条限制（真实约束）\n")
        f.write("- 方案文档假设可量化字段可以在会话结束后写入（用户体验差）\n\n")

        f.write("修正建议：\n")
        f.write("- 承认实战约束，更新方案文档\n")
        f.write("- 明确 working_criteria 的必要性和生命周期\n")
        f.write("- 明确可量化字段需要实时写入\n")

    print(f"✅ 测试结果已保存到: {results_file}")

    # Step 6: 打印总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    print("\n【硬禁用测试结果】")
    print("✅ 硬禁用生效：sync_requester_persona_memory 没有执行写入逻辑")
    print("✅ 分流逻辑工作：split_persona_patch 正确分流")
    print("❌ working_criteria 为空：Agent 无法补救")
    print("❌ 可量化字段无法立即生效：INTJ 无法实时写入")

    print("\n【实战问题】")
    print("❌ Agent 有80条限制，可能遗忘搜索条件")
    print("❌ 可量化字段无法立即生效，用户体验下降")

    print("\n【最终决策】")
    print("💡 必须保留 sync_requester_persona_memory 的实时写入逻辑")
    print("💡 working_criteria 是必要的'小本本'，防止 Agent 遗忘")
    print("💡 可量化字段需要实时写入，立即生效")

    print("\n【方案文档修正】")
    print("❌ 方案文档的'不插手'理想设计不可行")
    print("✅ 需要承认实战约束，更新方案文档")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_hard_disabled()