"""验证 merge_working_criteria 对 city/cities 处理的问题"""

import pytest
from match_domain.profile_write_guard import merge_working_criteria


def test_merge_working_criteria_city_vs_cities_conflict():
    """验证问题：city 和 cities 同时存在的情况"""

    # 场景1：用户第一次传入 city
    session_state = {}
    criteria1 = {"city": "北京"}
    result1 = merge_working_criteria(session_state, criteria1)

    print(f"\n场景1：用户第一次传入 city='北京'")
    print(f"  结果：{result1}")
    # 预期：{cities: ["北京"]}（city 被转换为 cities）
    assert "cities" in result1
    # ❌ 问题验证：city 字段是否还存在？
    if "city" in result1:
        print(f"  ❌ BUG 确认：city='北京' 还存在！与 cities=['北京'] 冲突")
        print(f"  ❌ 数据结构：{result1}")
        print(f"  ❌ 问题：两个字段都存在，可能导致下游查询构建器混淆")
    else:
        print(f"  ✅ 正确：city 已被清理，只有 cities")


def test_merge_working_criteria_city_then_cities():
    """验证问题：用户先传 city，再传 cities"""

    # 场景2：用户第一次传入 city
    session_state = {}
    criteria1 = {"city": "北京"}
    result1 = merge_working_criteria(session_state, criteria1)

    # 场景2：用户第二次传入 cities（不同的值）
    session_state2 = {"working_criteria": result1}
    criteria2 = {"cities": ["上海"]}
    result2 = merge_working_criteria(session_state2, criteria2)

    print(f"\n场景2：用户第二次传入 cities=['上海']")
    print(f"  第一次结果：{result1}")
    print(f"  第二次结果：{result2}")

    # ❌ 问题验证：city 字段是否还存在？
    if "city" in result2:
        print(f"  ❌ BUG：city='北京' 还存在！与 cities=['上海'] 冲突")
        print(f"  ❌ 数据结构：{result2}")
    else:
        print(f"  ✅ 正确：city 已被清理，只有 cities")


def test_merge_working_criteria_both_city_and_cities():
    """验证问题：用户同时传入 city 和 cities"""

    # 场景3：用户同时传入 city 和 cities（可能是 Agent 错误传入）
    session_state = {}
    criteria = {"city": "北京", "cities": ["上海"]}
    result = merge_working_criteria(session_state, criteria)

    print(f"\n场景3：用户同时传入 city='北京' 和 cities=['上海']")
    print(f"  结果：{result}")

    # ❌ 问题验证：两个字段是否都存在？
    if "city" in result and "cities" in result:
        print(f"  ❌ BUG：两个字段都存在！")
        print(f"  ❌ city='北京', cities=['上海'] → 搜索会用哪个？")
        print(f"  ❌ 数据结构：{result}")
    else:
        print(f"  ✅ 正确：只有一个字段存在")


def test_merge_working_criteria_real_scenario():
    """真实场景：用户逐步调整搜索条件"""

    # 场景4：真实对话场景
    # 用户："帮我搜北京的"
    session_state = {}
    result1 = merge_working_criteria(session_state, {"city": "北京"})
    print(f"\n场景4：真实对话")
    print(f"  第1轮：用户说'帮我搜北京的'")
    print(f"  结果：{result1}")

    # 用户："26-30岁"
    session_state2 = {"working_criteria": result1}
    result2 = merge_working_criteria(session_state2, {"age_min": 26, "age_max": 30})
    print(f"  第2轮：用户说'26-30岁'")
    print(f"  结果：{result2}")

    # 用户："改成上海的"
    session_state3 = {"working_criteria": result2}
    result3 = merge_working_criteria(session_state3, {"cities": ["上海"]})
    print(f"  第3轮：用户说'改成上海的'")
    print(f"  结果：{result3}")

    # ❌ 关键验证：第3轮后，旧的 city/cities 是否正确更新？
    if "city" in result3:
        print(f"  ❌ BUG：旧的 city 还存在！")
        print(f"  ❌ 数据结构：{result3}")
    else:
        print(f"  ✅ 正确：city 已清理")

    # 验证 cities 是否正确更新为上海
    if result3.get("cities") == ["上海"]:
        print(f"  ✅ 正确：cities 已更新为上海")
    else:
        print(f"  ❌ BUG：cities 未正确更新")
        print(f"  ❌ 期望：['上海'], 实际：{result3.get('cities')}")


if __name__ == "__main__":
    # 运行所有测试
    test_merge_working_criteria_city_vs_cities_conflict()
    test_merge_working_criteria_city_then_cities()
    test_merge_working_criteria_both_city_and_cities()
    test_merge_working_criteria_real_scenario()