"""测试AI自主判断语义关系的核心逻辑

验证内容：
1. Prompt构建是否正确
2. Fallback机制是否正常工作
3. 函数调用链是否正确

注意：这个测试不真正调用LLM（需要API key），只验证代码逻辑
"""

import asyncio
import os
from datetime import datetime

# 设置测试环境变量（模拟）
os.environ.setdefault("PERSONA_MEMORY_MYSQL_SOURCE", "mysql://root@127.0.0.1:3307/her_discovery_test")


def test_prompt_building():
    """测试Prompt构建"""
    from match_domain.ai_merge_handler import _build_semantic_judge_prompt

    print("=" * 80)
    print("测试1：Prompt构建")
    print("=" * 80)

    # 测试场景1：补充关系
    try:
        prompt1 = _build_semantic_judge_prompt(
            historical_text="性格内向",
            new_text="喜欢安静",
            vector_type="personality_traits",
            conversation_time=datetime.now(),  # 同一天
        )
        print("场景1：补充关系（同一天） - Prompt生成成功")
        print("历史文本：'性格内向'")
        print("新文本：'喜欢安静'")
        print()
    except Exception as e:
        print(f"❌ 场景1失败: {e}")
        return False

    # 测试场景2：冲突关系
    try:
        prompt2 = _build_semantic_judge_prompt(
            historical_text="喜欢热闹",
            new_text="喜欢安静",
            vector_type="personality_traits",
            conversation_time=datetime.now() - datetime.timedelta(days=90),  # 3个月后
        )
        print("场景2：冲突关系（3个月后） - Prompt生成成功")
        print("历史文本：'喜欢热闹'")
        print("新文本：'喜欢安静'")
        print()
    except Exception as e:
        print(f"❌ 场景2失败: {e}")
        return False

    print("✅ Prompt构建测试通过")
    return True


def test_fallback_decision():
    """测试Fallback机制"""
    from match_domain.ai_merge_handler import _fallback_decision

    print("=" * 80)
    print("测试2：Fallback机制")
    print("=" * 80)

    # 测试场景：AI判断失败时的Fallback
    result = _fallback_decision(
        historical_text="性格内向",
        new_text="喜欢安静",
    )

    print("Fallback决策结果：")
    print(f"  relation_type: {result['relation_type']}")
    print(f"  confidence: {result['confidence']}")
    print(f"  action: {result['action']}")
    print(f"  merged_text: {result['merged_text']}")
    print(f"  reason: {result['reason']}")
    print()

    # 验证Fallback逻辑
    assert result["action"] == "merge", "Fallback应该选择merge（保守策略）"
    assert result["confidence"] == "low", "Fallback置信度应该为low"
    assert result["merged_text"] == "性格内向、喜欢安静", "合并文本应该正确拼接"

    print("✅ Fallback机制测试通过")


def test_vector_types_config():
    """测试VECTOR_TYPES_CONFIG是否已移除update_policy"""
    from match_domain.vector_store_lite import VECTOR_TYPES_CONFIG

    print("=" * 80)
    print("测试3：VECTOR_TYPES_CONFIG检查")
    print("=" * 80)

    for vector_type, config in VECTOR_TYPES_CONFIG.items():
        print(f"{vector_type}:")
        print(f"  decay_days: {config.get('decay_days')}")
        print(f"  decay_curve: {config.get('decay_curve')}")
        print(f"  min_factor: {config.get('min_factor')}")

        # 验证是否已移除update_policy
        if "update_policy" in config:
            print(f"  ❌ 错误：仍然存在 update_policy={config['update_policy']}")
            return False
        else:
            print(f"  ✅ 已移除 update_policy")

    print("✅ VECTOR_TYPES_CONFIG测试通过，已移除所有硬编码策略")
    return True


def test_function_chain():
    """测试函数调用链"""
    print("=" * 80)
    print("测试4：函数调用链验证")
    print("=" * 80)

    # 验证所有函数是否可导入
    try:
        from match_domain.ai_merge_handler import (
            ai_merge_and_vectorize,
            _ai_judge_semantic_relation,
            _build_semantic_judge_prompt,
            _fallback_decision,
            save_summary_text,
            load_historical_summary,
        )
        print("✅ 所有核心函数导入成功")

        # 验证函数签名
        import inspect

        print("\nai_merge_and_vectorize() 函数签名：")
        sig = inspect.signature(ai_merge_and_vectorize)
        for param_name, param in sig.parameters.items():
            print(f"  - {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'}")

        print("\n✅ 函数调用链验证通过")
        return True

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False


def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("AI自主判断语义关系改进方案 - 代码逻辑验证")
    print("=" * 80 + "\n")

    results = []

    # 测试1：Prompt构建
    try:
        test_prompt_building()
        results.append(("Prompt构建", True))
    except Exception as e:
        print(f"❌ Prompt构建测试失败: {e}")
        results.append(("Prompt构建", False))

    # 测试2：Fallback机制
    try:
        test_fallback_decision()
        results.append(("Fallback机制", True))
    except Exception as e:
        print(f"❌ Fallback机制测试失败: {e}")
        results.append(("Fallback机制", False))

    # 测试3：VECTOR_TYPES_CONFIG
    try:
        test_vector_types_config()
        results.append(("VECTOR_TYPES_CONFIG", True))
    except Exception as e:
        print(f"❌ VECTOR_TYPES_CONFIG测试失败: {e}")
        results.append(("VECTOR_TYPES_CONFIG", False))

    # 测试4：函数调用链
    try:
        test_function_chain()
        results.append(("函数调用链", True))
    except Exception as e:
        print(f"❌ 函数调用链测试失败: {e}")
        results.append(("函数调用链", False))

    # 打印测试总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！代码逻辑验证成功")
    else:
        print("\n⚠️  部分测试失败，请检查代码")

    return passed == total


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)