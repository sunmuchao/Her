"""修复方案：统一 city/cities 处理逻辑

问题：merge_working_criteria 不清理被覆盖的 city 字段

实验验证：
- 用户传入 city="北京" → 结果：{cities: ["北京"], city: "北京"} ← city 没被清理
- 用户第二次传入 cities=["上海"] → 结果：{cities: ["上海"], city: "北京"} ← 旧的 city 还存在

修复思路：
1. 在合并时，如果用户传了 cities，就清理旧的 city
2. 在最终返回前，确保 city 字段被清理
3. 统一数据结构：只保留 cities（数组格式）

"""

from typing import Any, Mapping


def merge_working_criteria_fixed(
    session_state: Mapping[str, Any] | None,
    criteria: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """修复后的 merge_working_criteria"""

    from match_domain.profile_write_guard import is_search_criteria_key

    working = dict((session_state or {}).get("working_criteria") or {})
    incoming = dict(criteria or {})

    # ✅ 修复点1：如果用户传了 cities，就清理旧的 city
    if "cities" in incoming:
        working.pop("city", None)  # ← 清理旧的 city 字段

    for key, value in incoming.items():
        if is_search_criteria_key(key) and value not in (None, "", [], {}):
            if key == "city" and "cities" not in incoming:
                working["cities"] = [value] if not isinstance(value, list) else value
            else:
                working[key] = value

    merged = dict(working)
    merged.update(incoming)

    # ✅ 修复点2：在最终返回前，确保 city 字段被清理
    if "cities" in merged:
        merged.pop("city", None)  # ← 确保 city 被清理

    if "city" in merged and "cities" not in merged:
        city = merged.pop("city", None)
        if city not in (None, "", [], {}):
            merged["cities"] = [city] if not isinstance(city, list) else city

    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试验证修复效果
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_fixed_merge():
    """测试修复后的行为"""

    print("\n=== 测试修复后的 merge_working_criteria ===")

    # 场景1：用户第一次传入 city
    session_state = {}
    criteria1 = {"city": "北京"}
    result1 = merge_working_criteria_fixed(session_state, criteria1)

    print(f"\n场景1：用户第一次传入 city='北京'")
    print(f"  结果：{result1}")
    if "city" in result1:
        print(f"  ❌ 修复失败：city 还存在")
    else:
        print(f"  ✅ 修复成功：city 已清理，只有 cities")

    # 场景2：用户第二次传入 cities（不同的值）
    session_state2 = {"working_criteria": result1}
    criteria2 = {"cities": ["上海"]}
    result2 = merge_working_criteria_fixed(session_state2, criteria2)

    print(f"\n场景2：用户第二次传入 cities=['上海']")
    print(f"  结果：{result2}")
    if "city" in result2:
        print(f"  ❌ 修复失败：旧的 city 还存在")
    else:
        print(f"  ✅ 修复成功：city 已清理，只有 cities")

    # 场景3：用户同时传入 city 和 cities
    session_state = {}
    criteria = {"city": "北京", "cities": ["上海"]}
    result = merge_working_criteria_fixed(session_state, criteria)

    print(f"\n场景3：用户同时传入 city='北京' 和 cities=['上海']")
    print(f"  结果：{result}")
    if "city" in result:
        print(f"  ❌ 修复失败：city 还存在")
    else:
        print(f"  ✅ 修复成功：city 已清理，只有 cities")

    # 场景4：真实对话场景
    print(f"\n场景4：真实对话")
    session_state = {}
    result1 = merge_working_criteria_fixed(session_state, {"city": "北京"})
    print(f"  第1轮：用户说'帮我搜北京的'")
    print(f"    结果：{result1}")

    session_state2 = {"working_criteria": result1}
    result2 = merge_working_criteria_fixed(session_state2, {"age_min": 26, "age_max": 30})
    print(f"  第2轮：用户说'26-30岁'")
    print(f"    结果：{result2}")

    session_state3 = {"working_criteria": result2}
    result3 = merge_working_criteria_fixed(session_state3, {"cities": ["上海"]})
    print(f"  第3轮：用户说'改成上海的'")
    print(f"    结果：{result3}")

    if "city" in result3:
        print(f"    ❌ 修复失败：旧的 city 还存在")
    else:
        print(f"    ✅ 修复成功：city 已清理")


if __name__ == "__main__":
    test_fixed_merge()