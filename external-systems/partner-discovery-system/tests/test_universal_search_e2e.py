"""端到端测试：通用搜索系统验证

测试目标：
1. FieldMapper 字段映射器验证
2. UniversalQueryBuilder 查询构建验证
3. MBTI 类型筛选功能验证
4. Agent 真实场景验证
"""

from __future__ import annotations

import pathlib
import sys
import unittest

# 添加 match_domain 到 sys.path
MATCH_DOMAIN_ROOT = pathlib.Path(__file__).resolve().parents[3] / "match_domain"
if str(MATCH_DOMAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MATCH_DOMAIN_ROOT))


class TestFieldMapper(unittest.TestCase):
    """验证 FieldMapper 字段映射器"""

    def setUp(self):
        from match_domain.field_mapper import FieldMapper, FIELD_MAPPING
        self.mapper = FieldMapper()
        self.mapping = FIELD_MAPPING

    def test_basic_field_mapping(self):
        """测试基础字段映射"""
        # cities → city
        field = self.mapper.get_field("cities")
        self.assertEqual(field, "city")

        # gender → gender
        field = self.mapper.get_field("gender")
        self.assertEqual(field, "gender")

    def test_mbti_field_mapping(self):
        """测试 MBTI 字段映射"""
        # mbti_types → mbti_type
        field = self.mapper.get_field("mbti_types")
        self.assertEqual(field, "mbti_type")

        # exclude_mbti → mbti_type
        field = self.mapper.get_field("exclude_mbti")
        self.assertEqual(field, "mbti_type")

    def test_range_field_mapping(self):
        """测试范围字段映射"""
        # age_min → age
        field = self.mapper.get_field("age_min")
        self.assertEqual(field, "age")

        # age_max → age
        field = self.mapper.get_field("age_max")
        self.assertEqual(field, "age")

    def test_query_type_inference(self):
        """测试查询类型自动推断"""
        # cities → IN
        query_type = self.mapper.get_query_type("cities")
        self.assertEqual(query_type, "in")

        # mbti_types → IN
        query_type = self.mapper.get_query_type("mbti_types")
        self.assertEqual(query_type, "in")

        # exclude_mbti → NOT IN
        query_type = self.mapper.get_query_type("exclude_mbti")
        self.assertEqual(query_type, "not_in")

        # age_min → RANGE_MIN
        query_type = self.mapper.get_query_type("age_min")
        self.assertEqual(query_type, "range_min")

        # age_max → RANGE_MAX
        query_type = self.mapper.get_query_type("age_max")
        self.assertEqual(query_type, "range_max")

    def test_unknown_field_auto_inference(self):
        """测试未知字段自动推断"""
        # 未映射的字段，应该自动推断
        # _types 后缀 → IN
        query_type = self.mapper.get_query_type("new_types")
        self.assertEqual(query_type, "in")

        # exclude_ 前缀 → NOT IN
        query_type = self.mapper.get_query_type("exclude_new")
        self.assertEqual(query_type, "not_in")

        # _min 后缀 → RANGE_MIN
        query_type = self.mapper.get_query_type("new_min")
        self.assertEqual(query_type, "range_min")

    def test_register_new_field(self):
        """测试注册新字段"""
        # 注册新字段
        self.mapper.register("new_field", "new_column", "exact")

        # 验证映射生效
        field = self.mapper.get_field("new_field")
        self.assertEqual(field, "new_column")

        query_type = self.mapper.get_query_type("new_field")
        self.assertEqual(query_type, "exact")


class TestUniversalQueryBuilder(unittest.TestCase):
    """验证 UniversalQueryBuilder 查询构建器"""

    def setUp(self):
        from match_domain.universal_query_builder import UniversalQueryBuilder
        self.builder = UniversalQueryBuilder()

    def test_exact_match(self):
        """测试精确匹配"""
        self.builder.add_condition("gender", "female")

        where_clause = self.builder.build_where_clause()
        params = self.builder.get_params()

        self.assertIn("gender = :param_0", where_clause)
        self.assertEqual(params["param_0"], "female")

    def test_in_query(self):
        """测试列表 IN 查询"""
        self.builder.add_condition("cities", ["无锡", "苏州"])

        where_clause = self.builder.build_where_clause()
        params = self.builder.get_params()

        self.assertIn("city IN", where_clause)
        self.assertIn("无锡", params.values())
        self.assertIn("苏州", params.values())

    def test_not_in_query(self):
        """测试排除 NOT IN 查询"""
        self.builder.add_condition("exclude_mbti", ["ESFJ", "ISTJ"])

        where_clause = self.builder.build_where_clause()
        params = self.builder.get_params()

        self.assertIn("mbti_type NOT IN", where_clause)
        self.assertIn("ESFJ", params.values())
        self.assertIn("ISTJ", params.values())

    def test_range_query(self):
        """测试范围查询"""
        self.builder.add_condition("age_min", 26)
        self.builder.add_condition("age_max", 36)

        where_clause = self.builder.build_where_clause()
        params = self.builder.get_params()

        self.assertIn("age >= :param_0", where_clause)
        self.assertIn("age <= :param_1", where_clause)
        self.assertEqual(params["param_0"], 26)
        self.assertEqual(params["param_1"], 36)

    def test_multiple_conditions(self):
        """测试多条件组合"""
        self.builder.add_condition("cities", ["无锡"])
        self.builder.add_condition("gender", "female")
        self.builder.add_condition("age_min", 26)
        self.builder.add_condition("age_max", 36)
        self.builder.add_condition("mbti_types", ["INTP", "INTJ"])

        where_clause = self.builder.build_where_clause()
        params = self.builder.get_params()

        # 验证所有条件都存在
        self.assertIn("city IN", where_clause)
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("mbti_type IN", where_clause)

        # 验证 AND 连接
        self.assertIn(" AND ", where_clause)

    def test_empty_value_skipped(self):
        """测试空值被跳过"""
        self.builder.add_condition("cities", None)
        self.builder.add_condition("gender", "")

        where_clause = self.builder.build_where_clause()

        # 空值不应该生成条件
        self.assertEqual(where_clause, "")

    def test_process_criteria(self):
        """测试处理完整 criteria"""
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
        }

        where_clause, params = self.builder.process_criteria(criteria)

        # 验证生成了正确的查询
        self.assertIn("city IN", where_clause)
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("mbti_type IN", where_clause)


class TestMBTISearch(unittest.TestCase):
    """验证 MBTI 类型搜索功能"""

    def test_n_type_search_criteria(self):
        """测试 N系性格搜索条件构建"""
        from match_domain.universal_query_builder import build_search_query

        # Agent 传的 N系 MBTI 类型
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证 MBTI 条件存在
        self.assertIn("mbti_type IN", where_clause)

        # 验证包含所有 N系类型
        n_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        for mbti_type in n_types:
            self.assertIn(mbti_type, params.values())

        print("\n" + "=" * 80)
        print("✅ N系性格搜索条件验证通过")
        print(f"WHERE 子句: {where_clause}")
        print(f"参数数量: {len(params)}")
        print("=" * 80)

    def test_exclude_s_type_criteria(self):
        """测试排除 S系性格条件构建"""
        from match_domain.universal_query_builder import build_search_query

        # Agent 传的排除 S系
        criteria = {
            "cities": ["无锡"],
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证 NOT IN 条件存在
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证包含所有 S系类型
        s_types = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        for mbti_type in s_types:
            self.assertIn(mbti_type, params.values())

        print("\n" + "=" * 80)
        print("✅ 排除 S系性格条件验证通过")
        print(f"WHERE 子句: {where_clause}")
        print(f"排除的类型: {s_types}")
        print("=" * 80)

    def test_combined_mbt_criteria(self):
        """测试组合 MBTI 条件（包含 + 排除）"""
        from match_domain.universal_query_builder import build_search_query

        # Agent 同时指定包含 N系和排除 S系
        criteria = {
            "cities": ["无锡"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
            "exclude_mbti": ["ESFJ", "ISTJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证两个条件都存在
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("mbti_type NOT IN", where_clause)

        print("\n" + "=" * 80)
        print("✅ 组合 MBTI 条件验证通过")
        print(f"WHERE 子句: {where_clause}")
        print("=" * 80)


class TestRealAgentScenario(unittest.TestCase):
    """验证真实 Agent 场景"""

    def test_agent_says_n_type_scenario(self):
        """测试 Agent 说"我想要N系的"场景"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 收到用户反馈后的搜索参数
        # 用户说"性格类型不匹配"，Agent 判断用户想要 N系
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "relationship_goals": ["dating"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证完整搜索条件
        self.assertIn("city IN", where_clause)
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("relationship_goal IN", where_clause)
        self.assertIn("mbti_type IN", where_clause)

        print("\n" + "=" * 80)
        print("✅ Agent '我想要N系' 场景验证通过")
        print("模拟对话：")
        print("  用户: '性格类型不匹配'")
        print("  Agent: 理解为想要 N系性格候选人")
        print(f"搜索条件: {criteria}")
        print(f"生成查询: {where_clause[:100]}...")
        print("=" * 80)

    def test_agent_excludes_current_types_scenario(self):
        """测试 Agent 排除当前候选人的 MBTI 类型"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 看到当前全是 S系候选人，想排除这些类型
        # 当前候选人: ESFJ, ISTJ, ESTJ, ISFJ
        criteria = {
            "cities": ["无锡"],
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证排除条件
        self.assertIn("mbti_type NOT IN", where_clause)

        excluded = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        for mbti_type in excluded:
            self.assertIn(mbti_type, params.values())

        print("\n" + "=" * 80)
        print("✅ Agent 排除当前候选人类型场景验证通过")
        print("模拟对话：")
        print("  Agent: '刚才那批主要是 S系，我帮你换一批'")
        print(f"排除类型: {excluded}")
        print(f"生成查询: {where_clause}")
        print("=" * 80)


class TestFieldMapperExtension(unittest.TestCase):
    """验证字段映射器扩展能力"""

    def test_add_custom_field_on_the_fly(self):
        """测试动态添加自定义字段"""
        from match_domain.field_mapper import FieldMapper, QUERY_TYPE_LIKE

        # 创建自定义映射器
        custom_mapper = FieldMapper()

        # 动态注册新字段：mbti_preference（模糊匹配）
        custom_mapper.register("mbti_preference", "mbti_type", QUERY_TYPE_LIKE)

        # 验证新字段可用
        field = custom_mapper.get_field("mbti_preference")
        self.assertEqual(field, "mbti_type")

        query_type = custom_mapper.get_query_type("mbti_preference")
        self.assertEqual(query_type, "like")

        print("\n" + "=" * 80)
        print("✅ 动态添加自定义字段验证通过")
        print("新增字段: mbti_preference → mbti_type LIKE")
        print("=" * 80)


class TestIntegrationWithDiscoverySystem(unittest.TestCase):
    """验证与 Discovery 系统集成"""

    def test_criteria_passed_from_agent_to_builder(self):
        """测试 Agent 参数能正确传递到查询构建器"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 通过 search_partner_candidates 传的参数
        agent_criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "relationship_goals": ["dating"],
            "mbti_types": ["INTP", "INTJ"],
        }

        # 构建查询
        where_clause, params = build_search_query(agent_criteria)

        # 验证所有 Agent 参数都被处理
        self.assertIn("city", where_clause.lower())
        self.assertIn("gender", where_clause.lower())
        self.assertIn("age", where_clause.lower())
        self.assertIn("relationship_goal", where_clause.lower())
        self.assertIn("mbti_type", where_clause.lower())

        print("\n" + "=" * 80)
        print("✅ Agent → 查询构建器集成验证通过")
        print("所有 Agent 参数都被正确处理")
        print("=" * 80)


if __name__ == "__main__":
    unittest.main()