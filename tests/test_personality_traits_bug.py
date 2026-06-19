"""验证 personality_traits 的分流行为"""

from match_domain.profile_write_guard import is_search_criteria_key, split_persona_patch


def test_personality_traits_is_search_criteria():
    """验证 personality_traits 是否被认为是搜索条件"""

    print(f"\n=== 测试1：is_search_criteria_key('personality_traits') ===")

    result = is_search_criteria_key("personality_traits")
    print(f"  返回值：{result}")

    if result:
        print(f"  ✅ personality_traits 被认为是搜索条件（不在黑名单）")
        print(f"  ✅ 应该进入 search_part")
    else:
        print(f"  ❌ personality_traits 不被认为是搜索条件（在黑名单）")
        print(f"  ❌ 应该进入 persona_part")


def test_personality_traits_split_behavior():
    """验证 personality_traits 在 split_persona_patch 中的分流行为"""

    print(f"\n=== 测试2：split_persona_patch 对 personality_traits 的分流 ===")

    # 场景：用户说"帮我找内向的人"
    patch = {"personality_traits": ["内向", "温和"]}
    profile_part, persona_part, search_part = split_persona_patch(patch)

    print(f"  输入：{patch}")
    print(f"  profile_part：{profile_part}")
    print(f"  persona_part：{persona_part}")
    print(f"  search_part：{search_part}")

    if "personality_traits" in search_part:
        print(f"  ✅ personality_traits 进入 search_part")
        print(f"  ✅ 可以参与搜索筛选")
    elif "personality_traits" in persona_part:
        print(f"  ❌ BUG：personality_traits 进入 persona_part")
        print(f"  ❌ 不能直接参与搜索，只能记到长期记忆")
    else:
        print(f"  ❌ 异常：personality_traits 没被分流")


def test_personality_traits_with_other_fields():
    """验证 personality_traits 和其他字段一起传入的情况"""

    print(f"\n=== 测试3：personality_traits 和其他字段一起传入 ===")

    # 场景：用户说"帮我找北京的、26-30岁、内向的人"
    patch = {
        "cities": ["北京"],
        "age_min": 26,
        "age_max": 30,
        "personality_traits": ["内向", "温和"]
    }
    profile_part, persona_part, search_part = split_persona_patch(patch)

    print(f"  输入：{patch}")
    print(f"  profile_part：{profile_part}")
    print(f"  persona_part：{persona_part}")
    print(f"  search_part：{search_part}")

    print(f"\n  分析：")
    print(f"    cities → search_part: {'✅' if 'cities' in search_part else '❌'}")
    print(f"    age_min → search_part: {'✅' if 'age_min' in search_part else '❌'}")
    print(f"    age_max → search_part: {'✅' if 'age_max' in search_part else '❌'}")
    print(f"    personality_traits → search_part: {'✅' if 'personality_traits' in search_part else '❌'}")

    if "personality_traits" in search_part:
        print(f"\n  ✅ 所有字段都进入 search_part，可以一起参与搜索")
    else:
        print(f"\n  ❌ BUG：personality_traits 被分流到 persona_part")
        print(f"  ❌ 用户期望的性格筛选条件不能直接搜索")


if __name__ == "__main__":
    test_personality_traits_is_search_criteria()
    test_personality_traits_split_behavior()
    test_personality_traits_with_other_fields()