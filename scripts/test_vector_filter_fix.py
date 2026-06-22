"""测试向量筛选修复效果

验证修复的两个缺陷：
1. 返回值结构一致性（修复了 return [], 0.0 → return [], [], 0.0）
2. 路由规则补充（补充了"稳定经营"、"家庭责任"、"真诚沟通"等关键词）
"""

import sys
import asyncio

sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

from match_domain.retrieval_text_normalizer import normalize_query_text, route_query_vector_types


def test_route_query_vector_types():
    """测试路由规则修复效果"""
    print("=" * 80)
    print("测试路由规则修复效果")
    print("=" * 80)

    # 测试案例
    test_cases = [
        ("稳定经营、家庭责任、真诚沟通", "之前报错的文本"),
        ("稳定经营", "新增关键词1"),
        ("家庭责任", "新增关键词2"),
        ("真诚沟通", "新增关键词3"),
        ("温和", "已有关键词"),
        ("目标感强", "已有关键词"),
        ("及时回复", "已有关键词"),
        ("生活规律", "已有关键词"),
    ]

    for text, desc in test_cases:
        normalized = normalize_query_text(text)
        routes = route_query_vector_types(text)

        print(f"\n测试: {desc}")
        print(f"  输入: {text}")
        print(f"  标准化: {normalized.normalized_text}")
        print(f"  路由结果: {routes}")
        print(f"  是否包含 personality_traits: {'personality_traits' in routes}")
        print(f"  是否包含 values: {'values' in routes}")


async def test_search_similar_users_return_values():
    """测试返回值结构一致性"""
    print("\n" + "=" * 80)
    print("测试返回值结构一致性")
    print("=" * 80)

    from match_domain.vector_filter import _search_similar_users

    # 测试案例：路由跳过的情况
    print("\n场景1: 路由跳过（之前会报错的场景）")
    print("-" * 80)

    # 使用修复后的路由规则，"稳定经营"现在应该有路由了
    text = "稳定经营、家庭责任、真诚沟通"
    normalized = normalize_query_text(text)
    print(f"文本: {text}")
    print(f"标准化: {normalized.normalized_text}")
    print(f"路由结果: {normalized.route_vector_types}")

    # 检查 personality_traits 是否在路由中
    if "personality_traits" in normalized.route_vector_types:
        print("✅ personality_traits 在路由中，不会被跳过")
    else:
        print("❌ personality_traits 不在路由中，会被跳过（但修复后不会报错）")

        # 模拟调用 _search_similar_users（路由跳过场景）
        try:
            similar_ids, candidate_ids_with_data, avg_similarity = await _search_similar_users(
                text=text,
                vector_type="personality_traits",
                candidate_ids=[6092, 2379],
                user_id=10015,
                similarity_threshold=0.7,
            )
            print("✅ 返回值解包成功（修复生效）")
            print(f"  similar_ids: {similar_ids}")
            print(f"  candidate_ids_with_data: {candidate_ids_with_data}")
            print(f"  avg_similarity: {avg_similarity}")
        except Exception as e:
            print(f"❌ 返回值解包失败: {e}")


if __name__ == "__main__":
    # 测试1：路由规则修复
    test_route_query_vector_types()

    # 测试2：返回值结构一致性
    asyncio.run(test_search_similar_users_return_values())