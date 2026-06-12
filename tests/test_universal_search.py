"""端到端测试：通用搜索系统验证

测试目标：
1. 验证 UniversalQueryBuilder 能正确处理所有参数类型
2. 验证 MBTI 类型筛选功能
3. 验证现有搜索功能不受影响
4. 验证 Agent 传入的任意参数都能被处理
"""

from __future__ import annotations

import pathlib
import sys
import unittest

MATCH_DOMAIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(MATCH_DOMAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MATCH_DOMAIN_ROOT))

from match_domain.field_mapper import (
    FieldMapper,
    FIELD_MAPPING,
    QUERY_TYPE_EXACT,
    QUERY_TYPE_IN,
    QUERY_TYPE_NOT_IN,
    QUERY_TYPE_RANGE_MIN,
    QUERY_TYPE_RANGE_MAX,
    QUERY_TYPE_LIKE,
)
from match_domain.universal_query_builder import (
    UniversalQueryBuilder,
    build_search_query,
)


class TestFieldMapper(unittest.TestCase):
    """测试字段映射器"""

    def test_get_field_basic(self):
        """测试基本字段映射"""
        mapper = FieldMapper()

        # 测试已知字段
        self.assertEqual(mapper.get_field("gender"), "gender")
        self.assertEqual(mapper.get_field("cities"), "city")
        self.assertEqual(mapper.get_field("age_min"), "age")

    def test_get_field_mbti(self):
        """测试 MBTI 字段映射"""
        mapper = FieldMapper()

        self.assertEqual(mapper.get_field("mbti_types"), "mbti_type")
        self.assertEqual(mapper.get_field("exclude_mbti"), "mbti_type")
        self.assertEqual(mapper.get_field("exclude_mbti_types"), "mbti_type")

    def test_get_query_type_exact(self):
        """测试精确匹配类型"""
        mapper = FieldMapper()

        self.assertEqual(mapper.get_query_type("gender"), QUERY_TYPE_EXACT)
        self.assertEqual(mapper.get_query_type("relationship_goal"), QUERY_TYPE_EXACT)

    def test_get_query_type_in(self):
        """测试列表查询类型"""
        mapper = FieldMapper()

        self.assertEqual(mapper.get_query_type("cities"), QUERY_TYPE_IN)
        self.assertEqual(mapper.get_query_type("mbti_types"), QUERY_TYPE_IN)
        self.assertEqual(mapper.get_query_type("marital_statuses"), QUERY_TYPE_IN)

    def test_get_query_type_not_in(self):
        """测试排除列表类型"""
        mapper = FieldMapper()

        self.assertEqual(mapper.get_query_type("exclude_mbti"), QUERY_TYPE_NOT_IN)
        self.assertEqual(mapper.get_query_type("exclude_mbti_types"), QUERY_TYPE_NOT_IN)
        self.assertEqual(mapper.get_query_type("exclude_source_channels"), QUERY_TYPE_NOT_IN)

    def test_get_query_type_range(self):
        """测试范围查询类型"""
        mapper = FieldMapper()

        self.assertEqual(mapper.get_query_type("age_min"), QUERY_TYPE_RANGE_MIN)
        self.assertEqual(mapper.get_query_type("age_max"), QUERY_TYPE_RANGE_MAX)
        self.assertEqual(mapper.get_query_type("height_min"), QUERY_TYPE_RANGE_MIN)

    def test_infer_query_type_unknown_field(self):
        """测试自动推断未知字段的查询类型"""
        mapper = FieldMapper()

        # _min 后缀 → range_min
        self.assertEqual(mapper.get_query_type("unknown_min"), QUERY_TYPE_RANGE_MIN)

        # _max 后缀 → range_max
        self.assertEqual(mapper.get_query_type("unknown_max"), QUERY_TYPE_RANGE_MAX)

        # exclude_ 前缀 → not_in
        self.assertEqual(mapper.get_query_type("exclude_unknown"), QUERY_TYPE_NOT_IN)

        # _types 后缀 → in
        self.assertEqual(mapper.get_query_type("unknown_types"), QUERY_TYPE_IN)

        # 默认 → exact
        self.assertEqual(mapper.get_query_type("unknown_field"), QUERY_TYPE_EXACT)

    def test_register_new_field(self):
        """测试注册新字段"""
        mapper = FieldMapper()

        # 注册新字段
        mapper.register("new_param", "new_field", QUERY_TYPE_EXACT)

        # 验证映射生效
        self.assertEqual(mapper.get_field("new_param"), "new_field")
        self.assertEqual(mapper.get_query_type("new_param"), QUERY_TYPE_EXACT)


class TestUniversalQueryBuilder(unittest.TestCase):
    """测试通用查询构建器"""

    def test_build_exact_condition(self):
        """测试精确匹配条件构建"""
        builder = UniversalQueryBuilder()

        builder.add_condition("gender", "female")

        where_clause, params = builder.build_where_clause(), builder.get_params()

        self.assertIn("gender = :param_0", where_clause)
        self.assertEqual(params["param_0"], "female")

    def test_build_in_condition(self):
        """测试列表查询条件构建"""
        builder = UniversalQueryBuilder()

        builder.add_condition("cities", ["无锡", "上海"])

        where_clause, params = builder.build_where_clause(), builder.get_params()

        self.assertIn("city IN", where_clause)
        self.assertIn("无锡", params.values())
        self.assertIn("上海", params.values())

    def test_build_mbti_types_condition(self):
        """测试 MBTI 类型筛选条件构建"""
        builder = UniversalQueryBuilder()

        mbti_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        builder.add_condition("mbti_types", mbti_types)

        where_clause, params = builder.build_where_clause(), builder.get_params()

        # 验证 WHERE 子句
        self.assertIn("mbti_type IN", where_clause)

        # 验证参数包含所有 MBTI 类型
        for mbti in mbti_types:
            self.assertIn(mbti, params.values())

    def test_build_exclude_mbti_condition(self):
        """测试排除 MBTI 类型条件构建"""
        builder = UniversalQueryBuilder()

        exclude_mbti = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        builder.add_condition("exclude_mbti", exclude_mbti)

        where_clause, params = builder.build_where_clause(), builder.get_params()

        # 验证 WHERE 子句
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证参数包含所有排除的类型
        for mbti in exclude_mbti:
            self.assertIn(mbti, params.values())

    def test_build_range_condition(self):
        """测试范围查询条件构建"""
        builder = UniversalQueryBuilder()

        builder.add_condition("age_min", 26)
        builder.add_condition("age_max", 36)

        where_clause, params = builder.build_where_clause(), builder.get_params()

        self.assertIn("age >= :param_0", where_clause)
        self.assertIn("age <= :param_1", where_clause)
        self.assertEqual(params["param_0"], 26)
        self.assertEqual(params["param_1"], 36)

    def test_process_full_criteria(self):
        """测试处理完整搜索条件"""
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "relationship_goals": ["dating"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
            "exclude_mbti": ["ESFJ", "ISTJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证所有条件都被包含
        self.assertIn("city IN", where_clause)
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("relationship_goal IN", where_clause)
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证参数数量正确
        self.assertEqual(len(params), 1 + 1 + 1 + 1 + 1 + 4 + 2)  # gender + city + age_min + age_max + goal + mbti_types + exclude

    def test_skip_empty_values(self):
        """测试跳过空值"""
        builder = UniversalQueryBuilder()

        # 空值应该被跳过
        self.assertFalse(builder.add_condition("gender", None))
        self.assertFalse(builder.add_condition("cities", []))
        self.assertFalse(builder.add_condition("age_min", ""))

        # WHERE 子句应该为空
        where_clause = builder.build_where_clause()
        self.assertEqual(where_clause, "")

    def test_skip_unknown_field(self):
        """测试跳过未知字段"""
        builder = UniversalQueryBuilder()

        # 使用一个没有映射且不存在于数据库的字段
        # 由于 get_field 会返回参数名本身，所以不会被跳过
        builder.add_condition("unknown_field_xyz", "value")

        # 验证：未知字段会被保留（假设数据库字段名相同）
        where_clause, params = builder.build_where_clause(), builder.get_params()
        self.assertIn("unknown_field_xyz", where_clause)

    def test_ignore_non_search_fields(self):
        """测试忽略非搜索字段"""
        criteria = {
            "cities": ["无锡"],
            "limit": 10,        # 应被忽略
            "offset": 0,        # 应被忽略
            "order_by": "score", # 应被忽略
            "source": "mysql",   # 应被忽略
        }

        where_clause, params = build_search_query(criteria)

        # 验证：只有 cities 被处理
        self.assertIn("city IN", where_clause)
        self.assertNotIn("limit", where_clause)
        self.assertNotIn("offset", where_clause)
        self.assertNotIn("order_by", where_clause)
        self.assertNotIn("source", where_clause)


class TestMBTISearchIntegration(unittest.TestCase):
    """测试 MBTI 搜索集成"""

    def test_n_type_filtering(self):
        """测试 N系（直觉型）筛选

        N系包括：INTP, INTJ, INFP, INFJ, ENTP, ENTJ, ENFP, ENFJ
        """
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证查询条件正确构建
        self.assertIn("mbti_type IN", where_clause)

        # 验证所有 N系类型都在参数中
        n_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        for mbti in n_types:
            self.assertIn(mbti, params.values())

    def test_s_type_exclusion(self):
        """测试排除 S系（实感型）

        S系包括：ESTJ, ESFJ, ISTJ, ISFJ, ESTP, ESFP, ISTP, ISFP
        """
        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证排除条件正确构建
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证所有 S系类型都在排除参数中
        s_types = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        for mbti in s_types:
            self.assertIn(mbti, params.values())

    def test_combined_mbti_filter(self):
        """测试组合 MBTI 筛选（包含 + 排除）"""
        criteria = {
            "cities": ["无锡"],
            "mbti_types": ["INTP", "INTJ", "ENFP"],  # 想要的类型
            "exclude_mbti": ["ESFJ", "ISTJ"],        # 排除的类型
        }

        where_clause, params = build_search_query(criteria)

        # 验证两个条件都存在
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证参数正确
        self.assertIn("INTP", params.values())
        self.assertIn("ESFJ", params.values())


class TestBackwardCompatibility(unittest.TestCase):
    """测试向后兼容性"""

    def test_existing_fields_still_work(self):
        """测试现有字段仍然正常工作"""
        # 这是原有搜索功能会用到的字段组合
        criteria = {
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "cities": ["无锡"],
            "relationship_goals": ["dating"],
            "marital_statuses": ["未婚"],
            "profile_statuses": ["active"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证所有原有字段都被正确处理
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("city IN", where_clause)
        self.assertIn("relationship_goal IN", where_clause)
        self.assertIn("marital_status IN", where_clause)
        self.assertIn("profile_status IN", where_clause)

    def test_field_names_correct(self):
        """测试字段名映射正确"""
        mapper = FieldMapper()

        # 验证原有字段的映射没有变化
        self.assertEqual(mapper.get_field("cities"), "city")  # 复数 → 单数
        self.assertEqual(mapper.get_field("marital_statuses"), "marital_status")
        self.assertEqual(mapper.get_field("relationship_goals"), "relationship_goal")


class TestEdgeCases(unittest.TestCase):
    """测试边缘情况"""

    def test_empty_criteria(self):
        """测试空条件"""
        where_clause, params = build_search_query({})

        self.assertEqual(where_clause, "")
        self.assertEqual(params, {})

    def test_single_value_in_list_field(self):
        """测试列表字段传入单个值"""
        builder = UniversalQueryBuilder()

        # cities 期望是列表，但传入单个字符串
        builder.add_condition("cities", "无锡")

        where_clause, params = builder.build_where_clause(), builder.get_params()

        # 验证：自动转换为列表查询
        self.assertIn("city IN", where_clause)
        self.assertIn("无锡", params.values())

    def test_mixed_value_types(self):
        """测试混合值类型"""
        criteria = {
            "gender": "female",           # 字符串
            "age_min": 26,                 # 整数
            "cities": ["无锡", "上海"],    # 列表
            "has_children": False,        # 布尔值
        }

        where_clause, params = build_search_query(criteria)

        # 验证所有类型都被正确处理
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("city IN", where_clause)
        self.assertIn("has_children", where_clause)


if __name__ == "__main__":
    unittest.main()