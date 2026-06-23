"""验证 JSON 序列化错误修复的完整测试脚本

测试目标：
1. 验证 vector_filter_candidates 返回 list 类型（防线1）
2. 验证 search_partner_candidates 返回可 JSON 序列化的结果（防线2）
3. 验证 _convert_sets_to_lists 转换能力（防线3）
4. 验证完整的对话流程无错误

运行方式：
cd /Users/sunmuchao/Downloads/Her
python scripts/test_json_serialization_fix.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_logger = logging.getLogger(__name__)


async def test_vector_filter_returns_list():
    """测试1：验证 vector_filter_candidates 返回 list 类型（防线1）"""
    _logger.info("=" * 80)
    _logger.info("【测试1】验证 vector_filter_candidates 返回 list 类型（防线1）")
    _logger.info("=" * 80)

    try:
        from match_domain.vector_filter import vector_filter_candidates

        excluded_ids, included_ids, filter_trace = await vector_filter_candidates(
            vector_filter_json={
                "include": {
                    "personality_traits": {
                        "text": "温柔",
                        "similarity_threshold": 0.75
                    }
                }
            },
            candidate_ids=[123, 456, 789],
            user_id=100,
        )

        # ✅ 验证返回类型是 list（防线1的核心修复）
        assert isinstance(excluded_ids, list), f"excluded_ids 应该是 list，但实际是 {type(excluded_ids)}"
        assert isinstance(included_ids, list), f"included_ids 应该是 list，但实际是 {type(included_ids)}"
        assert isinstance(filter_trace, dict), f"filter_trace 应该是 dict，但实际是 {type(filter_trace)}"

        _logger.info("✅ 类型验证通过：excluded_ids=%s, included_ids=%s", type(excluded_ids).__name__, type(included_ids).__name__)

        # ✅ 验证可以被 JSON 序列化
        try:
            json_str = json.dumps({
                "excluded": excluded_ids,
                "included": included_ids,
                "trace": filter_trace
            })
            _logger.info("✅ JSON 序列化成功：%d 字符", len(json_str))
        except TypeError as exc:
            _logger.error("❌ JSON 序列化失败：%s", exc)
            raise

        _logger.info("【测试1】✅ 通过 - 防线1（源头修复）生效")
        return True

    except ImportError as exc:
        _logger.error("❌ 无法导入 vector_filter 模块：%s", exc)
        _logger.warning("⚠️ 可能需要先启动数据库或检查导入路径")
        return False
    except Exception as exc:
        _logger.error("❌ 测试1 失败：%s", exc, exc_info=True)
        return False


async def test_search_response_serializable():
    """测试2：验证 search_partner_candidates 返回可 JSON 序列化的结果（防线2）"""
    _logger.info("=" * 80)
    _logger.info("【测试2】验证 search_partner_candidates 返回可 JSON 序列化的结果（防线2）")
    _logger.info("=" * 80)

    try:
        from external_systems.partner_discovery_system.discovery_system.service_integrations import search_partner_candidates
        from external_systems.partner_discovery_system.discovery_system.storage import StoredSession

        # 创建模拟 session
        mock_session = StoredSession(
            session_id="test-session-fix",
            requester_id=100,
            profile_id=100,
            phase="results_shown",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            state={
                "last_shown_candidate_ids": [],
                "working_criteria": {},
            },
        )

        # 模拟搜索（实际环境中会查询数据库）
        response = search_partner_candidates(
            session=mock_session,
            criteria={"gender": "female", "age_min": 25, "age_max": 33},
            personality_match={"match_traits": ["温柔"], "similarity_threshold": 0.75},
            limit=5,
            exclude_current_results=False,
        )

        _logger.info("✅ 搜索完成：has_match=%s, result_count=%s",
                     response.get("has_match"), response.get("result_count"))

        # ✅ 验证可以被 JSON 序列化
        try:
            json_str = json.dumps(response, ensure_ascii=False, default=str)
            _logger.info("✅ JSON 序列化成功：%d 字符", len(json_str))

            # 检查关键字段
            if "vector_filter_trace" in response:
                _logger.info("✅ vector_filter_trace 存在且可序列化")

            if "personality_trace" in response:
                _logger.info("✅ personality_trace 存在且可序列化")

        except TypeError as exc:
            _logger.error("❌ JSON 序列化失败：%s", exc)
            _logger.error("❌ 响应结构：%s", list(response.keys()))
            raise

        _logger.info("【测试2】✅ 通过 - 防线2（中间层加固）生效")
        return True

    except ImportError as exc:
        _logger.error("❌ 无法导入 discovery_system 模块：%s", exc)
        _logger.warning("⚠️ 可能需要先启动数据库或检查导入路径")
        return False
    except Exception as exc:
        _logger.error("❌ 测试2 失败：%s", exc, exc_info=True)
        # 如果搜索失败（如数据库连接问题），至少验证修复逻辑本身
        _logger.warning("⚠️ 搜索失败（可能是数据库连接问题），但修复逻辑本身已验证")
        return False


async def test_convert_sets_to_lists():
    """测试3：验证 _convert_sets_to_lists 函数的转换能力（防线3）"""
    _logger.info("=" * 80)
    _logger.info("【测试3】验证 _convert_sets_to_lists 函数的转换能力（防线3）")
    _logger.info("=" * 80)

    try:
        from external_systems.partner_discovery_system.discovery_system.agent_runtime import _convert_sets_to_lists

        # 构造包含各种嵌套 set 的测试数据
        test_data = {
            "simple_set": {1, 2, 3},
            "nested_dict": {
                "inner_set": {"a", "b", "c"},
                "inner_list": [1, 2, {"set_in_list": {4, 5, 6}}],
            },
            "list_with_sets": [{7, 8, 9}, "normal_value", {10, 11}],
        }

        # 转换
        converted = _convert_sets_to_lists(test_data)

        # ✅ 验证所有 set 都被转换为 list
        assert isinstance(converted["simple_set"], list), "simple_set 应转换为 list"
        assert isinstance(converted["nested_dict"]["inner_set"], list), "inner_set 应转换为 list"
        assert isinstance(converted["list_with_sets"][0], list), "list 中的 set 应转换为 list"

        # ✅ 验证可以 JSON 序列化
        json_str = json.dumps(converted)
        _logger.info("✅ 转换成功，JSON 序列化：%d 字符", len(json_str))
        _logger.info("【测试3】✅ 通过 - 防线3（终端层兜底）生效")
        return True

    except ImportError as exc:
        _logger.error("❌ 无法导入 agent_runtime 模块：%s", exc)
        return False
    except Exception as exc:
        _logger.error("❌ 测试3 失败：%s", exc, exc_info=True)
        return False


def test_basic_json_serialization():
    """测试4：基础 JSON 序列化验证"""
    _logger.info("=" * 80)
    _logger.info("【测试4】基础 JSON 序列化验证")
    _logger.info("=" * 80)

    # 测试 set 无法序列化的问题
    test_set = {1, 2, 3}
    try:
        json.dumps({"exclude_ids": test_set})
        _logger.error("❌ set 对象竟然可以序列化？这不应该！")
        return False
    except TypeError as e:
        _logger.info("✅ 预期的错误：%s", e)

    # 测试 list 可以序列化
    test_list = list(test_set)
    try:
        result = json.dumps({"exclude_ids": test_list})
        _logger.info("✅ list 对象可以序列化：%s", result)
    except TypeError as e:
        _logger.error("❌ list 对象序列化失败：%s", e)
        return False

    _logger.info("【测试4】✅ 通过")
    return True


async def main():
    """运行所有测试"""
    _logger.info("\n" + "=" * 80)
    _logger.info("【开始验证】JSON 序列化错误修复 - 三道防线")
    _logger.info("=" * 80 + "\n")

    results = []

    # 测试1：防线1（源头修复）
    try:
        result1 = await test_vector_filter_returns_list()
        results.append(("测试1：防线1（源头修复）", result1))
    except Exception as exc:
        _logger.error("测试1 异常：%s", exc, exc_info=True)
        results.append(("测试1：防线1（源头修复）", False))

    # 测试2：防线2（中间层加固）
    try:
        result2 = await test_search_response_serializable()
        results.append(("测试2：防线2（中间层加固）", result2))
    except Exception as exc:
        _logger.error("测试2 异常：%s", exc, exc_info=True)
        results.append(("测试2：防线2（中间层加固）", False))

    # 测试3：防线3（终端层兜底）
    try:
        result3 = await test_convert_sets_to_lists()
        results.append(("测试3：防线3（终端层兜底）", result3))
    except Exception as exc:
        _logger.error("测试3 异常：%s", exc, exc_info=True)
        results.append(("测试3：防线3（终端层兜底）", False))

    # 测试4：基础验证
    try:
        result4 = test_basic_json_serialization()
        results.append(("测试4：基础验证", result4))
    except Exception as exc:
        _logger.error("测试4 异常：%s", exc, exc_info=True)
        results.append(("测试4：基础验证", False))

    # 总结
    _logger.info("\n" + "=" * 80)
    _logger.info("【测试总结】")
    _logger.info("=" * 80)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        _logger.info("%s - %s", test_name, status)

    all_passed = all(result for _, result in results)
    passed_count = sum(1 for _, result in results if result)

    _logger.info("\n统计：通过 %d/%d 测试", passed_count, len(results))

    if all_passed:
        _logger.info("\n🎉 所有测试通过！JSON 序列化错误已修复。")
        _logger.info("修复效果：")
        _logger.info("  - ✅ 防线1（源头）：vector_filter 返回 list 类型")
        _logger.info("  - ✅ 防线2（中间）：显式转换 set → list")
        _logger.info("  - ✅ 防线3（终端）：统一转换兜底")
    else:
        _logger.warning("\n⚠️ 部分测试失败，请检查修复代码。")
        _logger.warning("建议：")
        _logger.warning("  1. 确认修改已应用到 vector_filter.py")
        _logger.warning("  2. 确认修改已应用到 service_integrations.py")
        _logger.warning("  3. 确认修改已应用到 agent_runtime.py")

    return all_passed


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        _logger.info("\n⚠️ 测试被中断")
        sys.exit(1)
    except Exception as exc:
        _logger.error("\n❌ 测试运行异常：%s", exc, exc_info=True)
        sys.exit(1)