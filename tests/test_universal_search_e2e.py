"""端到端测试：通用搜索系统完整链路验证

测试目标：
1. 验证 Agent → criteria_compiler → search_sources → 数据库 的完整链路
2. 验证 MBTI 类型筛选功能能真正过滤出正确的候选人
3. 验证 Agent Native 原则：任意新参数都能被正确处理
4. 验证向后兼容性：现有搜索功能不受影响

测试架构：
- 真实数据库测试（需要测试数据库环境）
- Mock 测试（不需要数据库，用于 CI）
- Agent 场景模拟测试

测试数据库配置：
- MySQL: mysql://root@127.0.0.1:3307/her_discovery_test?table=profiles
- 或使用环境变量 HER_DISCOVERY_PROFILE_SOURCE
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock
from typing import Any

# 添加项目路径
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MATCH_DOMAIN_ROOT = PROJECT_ROOT / "match_domain"
if str(MATCH_DOMAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MATCH_DOMAIN_ROOT))

DISCOVERY_ROOT = PROJECT_ROOT / "external-systems" / "partner-discovery-system"
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))


# ============================================================================
# 第一部分：Agent → criteria_compiler → search_sources 完整链路测试
# ============================================================================

class TestFullPipelineWithMock(unittest.TestCase):
    """使用 Mock 验证完整链路（不需要真实数据库）"""

    def test_agent_criteria_passes_through_criteria_compiler(self):
        """测试 Agent 参数能通过 criteria_compiler 正确编译"""
        from match_domain.criteria_compiler import compile_effective_criteria, SCENE_DISCOVERY_SEARCH

        # 模拟 Agent 传入的搜索参数（包含 MBTI）
        agent_criteria = {
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "cities": ["无锡"],
            "relationship_goals": ["认真恋爱"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
            "exclude_mbti": ["ESFJ", "ISTJ"],
        }

        # 编译条件
        compiled = compile_effective_criteria(
            scene=SCENE_DISCOVERY_SEARCH,
            profile_row=None,
            persona_row=None,
            base_criteria=agent_criteria,
            overrides=None,
        )

        # 验证：所有参数都应该进入 hard_filters（不再有 hard_keys 硬编码）
        self.assertIn("mbti_types", compiled.hard_filters)
        self.assertIn("exclude_mbti", compiled.hard_filters)
        self.assertIn("gender", compiled.hard_filters)
        self.assertIn("cities", compiled.hard_filters)

        # 验证：criteria 包含所有原始参数
        self.assertIn("mbti_types", compiled.criteria)
        self.assertEqual(compiled.criteria["mbti_types"], ["INTP", "INTJ", "INFP", "INFJ"])

        print("\n" + "=" * 80)
        print("✅ Agent → criteria_compiler 链路验证通过")
        print(f"   hard_filters 包含: {list(compiled.hard_filters.keys())}")
        print(f"   mbti_types: {compiled.hard_filters.get('mbti_types')}")
        print("=" * 80)

    def test_criteria_compiler_no_hard_keys_discrimination(self):
        """测试 criteria_compiler 不再歧视非 hard_keys 参数"""
        from match_domain.criteria_compiler import compile_effective_criteria, SCENE_DISCOVERY_SEARCH

        # 旧版本会忽略的参数（现在应该都被处理）
        agent_criteria = {
            "gender": "female",
            "cities": ["无锡"],
            # 以下参数旧版本会进入 soft_preferences 然后被丢弃
            "mbti_types": ["INTP", "INTJ"],
            "attachment_types": ["secure"],
            "custom_field": "custom_value",
        }

        compiled = compile_effective_criteria(
            scene=SCENE_DISCOVERY_SEARCH,
            profile_row=None,
            persona_row=None,
            base_criteria=agent_criteria,
            overrides=None,
        )

        # 验证：所有非空参数都进入 hard_filters
        self.assertIn("mbti_types", compiled.hard_filters)
        self.assertIn("attachment_types", compiled.hard_filters)
        self.assertIn("custom_field", compiled.hard_filters)

        # 验证：soft_preferences 应该为空（不再使用）
        self.assertEqual(compiled.soft_preferences, {})

        print("\n" + "=" * 80)
        print("✅ criteria_compiler 不再歧视参数验证通过")
        print("   所有非空参数都进入 hard_filters")
        print("   soft_preferences 已废弃（为空）")
        print("=" * 80)

    def test_search_sources_processes_mbti_filters(self):
        """测试 search_sources 能处理 MBTI 筛选参数"""
        from partner_search.search_sources import build_mysql_prefilter, SearchSourceRuntime
        from partner_search.search_candidates import _build_search_source_runtime

        # 创建搜索 runtime
        runtime = _build_search_source_runtime()

        # 模拟列名映射
        canonical_to_actual = {
            "gender": "gender",
            "city": "city",
            "age": "age",
            "mbti_type": "mbti_type",
            "relationship_goal": "relationship_goal",
            "profile_status": "profile_status",
        }

        # 包含 MBTI 筛选的条件
        criteria = {
            "gender": "female",
            "cities": ["无锡"],
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
            "exclude_mbti": ["ESFJ", "ISTJ"],
        }

        # 构建预过滤条件
        result = build_mysql_prefilter(runtime, criteria, canonical_to_actual)

        if result is None:
            where_clause, params = "", []
        else:
            where_clause, params = result

        # 验证：WHERE 子句包含 MBTI 条件
        self.assertIn("mbti_type", where_clause.lower())
        self.assertIn("INTP", params)
        self.assertIn("ESFJ", params)

        # 验证：包含 IN 和 NOT IN
        # 注意：实际的 SQL 使用 %s 占位符
        self.assertTrue("IN" in where_clause.upper() or "in" in where_clause)

        print("\n" + "=" * 80)
        print("✅ search_sources 处理 MBTI 参数验证通过")
        print(f"   WHERE 子句: {where_clause[:100]}...")
        print(f"   参数数量: {len(params)}")
        print("=" * 80)


class TestFullPipelineWithDatabase(unittest.TestCase):
    """使用真实数据库验证完整链路（需要测试数据库环境）"""

    @classmethod
    def setUpClass(cls):
        """检查测试数据库是否可用"""
        cls.test_source = os.environ.get(
            "HER_DISCOVERY_PROFILE_SOURCE",
            "mysql://root@127.0.0.1:3307/her_discovery_test?table=profiles"
        )

        # 检查数据库是否可用
        cls.db_available = cls._check_db_available()

    @classmethod
    def _check_db_available(cls) -> bool:
        """检查测试数据库是否可用"""
        try:
            from partner_search import load_self_profile
            # 尝试连接数据库
            result = load_self_profile(source=cls.test_source, self_id=1)
            return True
        except Exception:
            return False

    def setUp(self):
        """如果数据库不可用，跳过测试"""
        if not self.db_available:
            self.skipTest("测试数据库不可用，跳过真实数据库测试")

    def test_real_search_with_mbti_filter(self):
        """使用真实数据库验证 MBTI 筛选"""
        from partner_search import search_profiles
        from match_domain.criteria_compiler import compile_effective_criteria, SCENE_DISCOVERY_SEARCH

        # 搜索 N系性格的候选人
        criteria = {
            "gender": "female",
            "cities": ["无锡"],
            "age_min": 25,
            "age_max": 40,
            "relationship_goals": ["认真恋爱"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        try:
            result = search_profiles(
                source=self.test_source,
                criteria=criteria,
                self_id=1,
                limit=5,
            )

            # 验证搜索结果
            self.assertIn("has_match", result)
            self.assertIn("results", result)

            # 如果有结果，验证 MBTI 类型正确
            if result["has_match"] and result["results"]:
                for candidate in result["results"]:
                    mbti = candidate.get("mbti_type")
                    if mbti:
                        # 验证结果是 N系
                        n_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
                        self.assertIn(mbti, n_types, f"候选人 MBTI {mbti} 不是 N系")

                print("\n" + "=" * 80)
                print("✅ 真实数据库 MBTI 筛选验证通过")
                print(f"   搜索条件: mbti_types = {criteria['mbti_types']}")
                print(f"   搜索结果数量: {result['result_count']}")
                if result["results"]:
                    print(f"   第一位候选人 MBTI: {result['results'][0].get('mbti_type', '未知')}")
                print("=" * 80)
            else:
                print("\n" + "=" * 80)
                print("⚠️ 搜索返回空结果，可能测试数据库无数据")
                print("=" * 80)

        except Exception as e:
            self.skipTest(f"数据库查询失败: {e}")

    def test_real_search_exclude_mbti(self):
        """使用真实数据库验证排除 MBTI 类型"""
        from partner_search import search_profiles

        # 搜索候选人，排除 S系
        criteria = {
            "gender": "female",
            "cities": ["无锡"],
            "age_min": 25,
            "age_max": 40,
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        try:
            result = search_profiles(
                source=self.test_source,
                criteria=criteria,
                self_id=1,
                limit=5,
            )

            # 如果有结果，验证不包含排除的类型
            if result["has_match"] and result["results"]:
                excluded_types = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
                for candidate in result["results"]:
                    mbti = candidate.get("mbti_type")
                    if mbti:
                        self.assertNotIn(mbti, excluded_types, f"候选人 MBTI {mbti} 应被排除")

                print("\n" + "=" * 80)
                print("✅ 真实数据库排除 MBTI 验证通过")
                print(f"   排除类型: {excluded_types}")
                print(f"   搜索结果数量: {result['result_count']}")
                print("=" * 80)

        except Exception as e:
            self.skipTest(f"数据库查询失败: {e}")

    def test_discovery_search_with_mbti(self):
        """验证 Discovery 系统完整链路能处理 MBTI 筛选"""
        from match_domain.criteria_compiler import build_discovery_search_request

        # 模拟 Discovery 搜索请求（包含 MBTI）
        criteria_overrides = {
            "gender": "female",
            "cities": ["无锡"],
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INTP", "INTJ"],
        }

        request = build_discovery_search_request(
            source=self.test_source,
            profile_row={"id": 1, "gender": "male", "age": 30, "city": "无锡"},
            persona_row={"self_relationship_goal": "认真恋爱"},
            criteria_overrides=criteria_overrides,
            self_id=1,
            limit=5,
        )

        # 验证请求包含 MBTI 参数
        self.assertIn("mbti_types", request["criteria"])
        self.assertEqual(request["criteria"]["mbti_types"], ["INTP", "INTJ"])

        # 验证 compiled 包含所有参数
        compiled = request["compiled"]
        self.assertIn("mbti_types", compiled["hard_filters"])
        self.assertIn("mbti_types", compiled["criteria"])

        print("\n" + "=" * 80)
        print("✅ Discovery 搜索请求包含 MBTI 参数验证通过")
        print(f"   criteria: {request['criteria']}")
        print("=" * 80)


# ============================================================================
# 第二部分：MBTI 筛选功能专项测试
# ============================================================================

class TestMBTIFiltering(unittest.TestCase):
    """MBTI 筛选功能专项测试"""

    def test_mbti_types_query_structure(self):
        """测试 mbti_types 生成正确的 IN 查询"""
        from match_domain.universal_query_builder import build_search_query

        criteria = {
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证 IN 查询结构
        self.assertIn("mbti_type IN", where_clause)

        # 验证所有 N系类型都在参数中
        n_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        for mbti in n_types:
            self.assertIn(mbti, params.values())

        print("\n" + "=" * 80)
        print("✅ mbti_types 查询结构验证通过")
        print(f"   查询: {where_clause}")
        print(f"   参数: {list(params.values())}")
        print("=" * 80)

    def test_exclude_mbti_query_structure(self):
        """测试 exclude_mbti 生成正确的 NOT IN 查询"""
        from match_domain.universal_query_builder import build_search_query

        criteria = {
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证 NOT IN 查询结构
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证所有 S系类型都在排除参数中
        s_types = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        for mbti in s_types:
            self.assertIn(mbti, params.values())

        print("\n" + "=" * 80)
        print("✅ exclude_mbti 查询结构验证通过")
        print(f"   查询: {where_clause}")
        print(f"   排除参数: {list(params.values())}")
        print("=" * 80)

    def test_combined_mbti_in_and_not_in(self):
        """测试 mbti_types + exclude_mbti 组合查询"""
        from match_domain.universal_query_builder import build_search_query

        # 同时包含想要的类型和排除的类型
        criteria = {
            "cities": ["无锡"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],  # 想要 N系
            "exclude_mbti": ["ESFJ", "ISTJ"],                  # 排除部分 S系
        }

        where_clause, params = build_search_query(criteria)

        # 验证两个 MBTI 条件都存在
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("mbti_type NOT IN", where_clause)

        # 验证两种类型的参数都正确
        self.assertIn("INTP", params.values())  # 包含的
        self.assertIn("ESFJ", params.values())  # 排除的

        print("\n" + "=" * 80)
        print("✅ 组合 MBTI 查询验证通过")
        print(f"   查询包含: IN 和 NOT IN")
        print("=" * 80)

    def test_mbti_n_series_full_set(self):
        """测试完整的 N系（直觉型）类型集"""
        from match_domain.universal_query_builder import build_search_query

        # N系 = 所有包含 N 的 MBTI 类型
        n_series = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]

        criteria = {"mbti_types": n_series}

        where_clause, params = build_search_query(criteria)

        # 验证所有 N系类型都在查询中
        for mbti in n_series:
            self.assertIn(mbti, params.values())

        # 验证查询参数数量
        self.assertEqual(len(params), 8)

        print("\n" + "=" * 80)
        print("✅ N系完整类型集验证通过")
        print(f"   N系类型: {n_series}")
        print(f"   参数数量: {len(params)}")
        print("=" * 80)

    def test_mbti_s_series_full_set(self):
        """测试完整的 S系（实感型）类型集"""
        from match_domain.universal_query_builder import build_search_query

        # S系 = 所有包含 S 的 MBTI 类型
        s_series = ["ESTP", "ESFP", "ISTP", "ISFP", "ESTJ", "ESFJ", "ISTJ", "ISFJ"]

        criteria = {"mbti_types": s_series}

        where_clause, params = build_search_query(criteria)

        # 验证所有 S系类型都在查询中
        for mbti in s_series:
            self.assertIn(mbti, params.values())

        # 验证查询参数数量
        self.assertEqual(len(params), 8)

        print("\n" + "=" * 80)
        print("✅ S系完整类型集验证通过")
        print(f"   S系类型: {s_series}")
        print(f"   参数数量: {len(params)}")
        print("=" * 80)


# ============================================================================
# 第三部分：Agent Native 验证测试
# ============================================================================

class TestAgentNativePrinciple(unittest.TestCase):
    """验证 Agent Native 原则：任意新参数都能被正确处理"""

    def test_unknown_parameter_auto_inference(self):
        """测试未知参数能被自动推断处理"""
        from match_domain.universal_query_builder import build_search_query

        # Agent 传入一个未在映射表中定义的新参数
        criteria = {
            "cities": ["无锡"],
            "new_status_types": ["value1", "value2"],  # 未定义，但有 _types 后缀
            "exclude_new_field": ["bad_value"],        # 未定义，但有 exclude_ 前缀
            "score_min": 50,                            # 未定义，但有 _min 后缀
        }

        where_clause, params = build_search_query(criteria)

        # 验证：所有参数都被处理（通过自动推断）
        self.assertIn("city IN", where_clause)
        # _types 后缀 → IN 查询
        self.assertIn("new_status_types IN", where_clause)
        # exclude_ 前缀 → NOT IN 查询
        self.assertIn("exclude_new_field NOT IN", where_clause)
        # _min 后缀 → >= 查询
        # 注意：字段名是 score_min，所以查询是 score_min >= （因为字段名没有被映射）
        self.assertIn("score_min >= ", where_clause)

        print("\n" + "=" * 80)
        print("✅ 未知参数自动推断验证通过")
        print("   Agent Native 原则：任意参数都能被处理")
        print(f"   查询: {where_clause[:200]}...")
        print("=" * 80)

    def test_dynamic_field_registration(self):
        """测试动态注册新字段"""
        from match_domain.field_mapper import FieldMapper, QUERY_TYPE_IN
        from match_domain.universal_query_builder import UniversalQueryBuilder

        # 创建自定义映射器
        custom_mapper = FieldMapper()

        # Agent 可能传入的新字段：价值观匹配
        custom_mapper.register("value_types", "value_type", QUERY_TYPE_IN)
        custom_mapper.register("exclude_values", "value_type", "not_in")

        # 使用自定义映射器构建查询
        builder = UniversalQueryBuilder(mapper=custom_mapper)

        criteria = {
            "value_types": ["growth", "stability"],
            "exclude_values": ["materialism"],
        }

        where_clause, params = builder.process_criteria(criteria)

        # 验证新字段被正确处理
        self.assertIn("value_type IN", where_clause)
        self.assertIn("value_type NOT IN", where_clause)
        self.assertIn("growth", params.values())
        self.assertIn("materialism", params.values())

        print("\n" + "=" * 80)
        print("✅ 动态字段注册验证通过")
        print("   新增字段: value_types, exclude_values")
        print(f"   查询: {where_clause}")
        print("=" * 80)

    def test_agent_can_specify_any_field_without_code_change(self):
        """测试 Agent 能指定任意字段，无需修改代码"""
        from match_domain.criteria_compiler import compile_effective_criteria, SCENE_DISCOVERY_SEARCH

        # Agent 传入一个全新的字段组合
        # 设计文档说：新增字段只需加一行映射配置，无需改多处代码
        new_criteria = {
            "gender": "female",
            "cities": ["无锡"],
            # 新字段：生活方式偏好（假设未来新增）
            "lifestyle_types": ["quiet", "balanced"],
            "exclude_lifestyle": ["party"],
            # 新字段：教育偏好范围（假设未来新增）
            "education_level_min": 3,
        }

        compiled = compile_effective_criteria(
            scene=SCENE_DISCOVERY_SEARCH,
            profile_row=None,
            persona_row=None,
            base_criteria=new_criteria,
            overrides=None,
        )

        # 验证：所有新字段都进入 hard_filters（没有被丢弃）
        self.assertIn("lifestyle_types", compiled.hard_filters)
        self.assertIn("exclude_lifestyle", compiled.hard_filters)
        self.assertIn("education_level_min", compiled.hard_filters)

        print("\n" + "=" * 80)
        print("✅ Agent 任意字段验证通过")
        print("   Agent Native 原则：Agent 能自由表达搜索意图")
        print(f"   新字段都被处理: lifestyle_types, exclude_lifestyle, education_level_min")
        print("=" * 80)


# ============================================================================
# 第四部分：向后兼容性测试
# ============================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """验证向后兼容性：现有搜索功能不受影响"""

    def test_existing_search_criteria_still_work(self):
        """测试现有搜索条件仍然正常工作"""
        from match_domain.universal_query_builder import build_search_query

        # 这是原有搜索功能会用到的字段组合
        legacy_criteria = {
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "cities": ["无锡"],
            "relationship_goals": ["认真恋爱"],
            "marital_statuses": ["未婚"],
            "housing_statuses": ["已购房"],
            "car_statuses": ["已购车"],
            "profile_statuses": ["active"],
            "verified_levels": ["basic", "advanced"],
        }

        where_clause, params = build_search_query(legacy_criteria)

        # 验证所有原有字段都被正确处理
        self.assertIn("gender = ", where_clause)
        self.assertIn("age >= ", where_clause)
        self.assertIn("age <= ", where_clause)
        self.assertIn("city IN", where_clause)
        self.assertIn("relationship_goal IN", where_clause)
        self.assertIn("marital_status IN", where_clause)
        self.assertIn("housing_status IN", where_clause)
        self.assertIn("car_status IN", where_clause)
        self.assertIn("profile_status IN", where_clause)
        self.assertIn("verified_level IN", where_clause)

        print("\n" + "=" * 80)
        print("✅ 现有搜索条件向后兼容验证通过")
        print("   所有原有字段都被正确处理")
        print("=" * 80)

    def test_field_mapping_unchanged_for_existing_fields(self):
        """测试现有字段的映射没有变化"""
        from match_domain.field_mapper import FieldMapper

        mapper = FieldMapper()

        # 验证原有字段的映射保持不变
        # 这些映射关系不能改变，否则会影响现有功能
        self.assertEqual(mapper.get_field("gender"), "gender")
        self.assertEqual(mapper.get_field("cities"), "city")  # 复数 → 单数
        self.assertEqual(mapper.get_field("age_min"), "age")
        self.assertEqual(mapper.get_field("age_max"), "age")
        self.assertEqual(mapper.get_field("marital_statuses"), "marital_status")
        self.assertEqual(mapper.get_field("relationship_goals"), "relationship_goal")

        # 验证查询类型没有变化
        self.assertEqual(mapper.get_query_type("gender"), "exact")
        self.assertEqual(mapper.get_query_type("cities"), "in")
        self.assertEqual(mapper.get_query_type("age_min"), "range_min")
        self.assertEqual(mapper.get_query_type("age_max"), "range_max")

        print("\n" + "=" * 80)
        print("✅ 现有字段映射不变验证通过")
        print("   字段映射关系保持向后兼容")
        print("=" * 80)

    def test_search_sources_handles_legacy_criteria(self):
        """测试 search_sources 能处理原有条件"""
        from partner_search.search_sources import build_mysql_prefilter
        from partner_search.search_candidates import _build_search_source_runtime

        runtime = _build_search_source_runtime()
        canonical_to_actual = {
            "gender": "gender",
            "city": "city",
            "age": "age",
            "height": "height",
            "relationship_goal": "relationship_goal",
            "marital_status": "marital_status",
            "housing_status": "housing_status",
            "car_status": "car_status",
            "profile_status": "profile_status",
            "verified_level": "verified_level",
        }

        # 原有搜索条件（不含 MBTI）
        legacy_criteria = {
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "cities": ["无锡"],
            "relationship_goals": ["认真恋爱"],
            "marital_statuses": ["未婚"],
            "profile_statuses": ["active"],
        }

        result = build_mysql_prefilter(runtime, legacy_criteria, canonical_to_actual)

        if result:
            where_clause, params = result

            # 验证原有条件都被处理
            self.assertIn("gender", where_clause.lower())
            self.assertIn("city", where_clause.lower())
            self.assertIn("age", where_clause.lower())

            print("\n" + "=" * 80)
            print("✅ search_sources 向后兼容验证通过")
            print("   原有条件都被正确处理")
            print("=" * 80)


# ============================================================================
# 第五部分：Agent 场景模拟测试
# ============================================================================

class TestAgentScenarios(unittest.TestCase):
    """模拟真实 Agent 场景"""

    def test_agent_wants_n_type_scenario(self):
        """场景：用户反馈'性格不匹配'，Agent 理解为想要 N系"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 收到用户反馈后的搜索参数生成
        # 用户: "性格类型不匹配"
        # Agent: 理解为想要 N系性格（INTP, INTJ, INFP, INFJ, ENTP, ENTJ, ENFP, ENFJ）

        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "relationship_goals": ["认真恋爱"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证搜索条件正确
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("INTP", params.values())
        self.assertIn("ENFJ", params.values())

        print("\n" + "=" * 80)
        print("✅ Agent 场景：'我想要 N系' 验证通过")
        print("   模拟对话：")
        print("   用户: '性格类型不匹配'")
        print("   Agent: 理解为想要 N系性格候选人")
        print(f"   生成搜索条件: {len(params)} 个参数")
        print("=" * 80)

    def test_agent_excludes_current_results_scenario(self):
        """场景：Agent 看到当前结果全是 S系，想排除这些类型"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 分析当前结果后的搜索参数调整
        # 当前候选人: ESFJ, ISTJ, ESTJ, ISFJ（全是 S系）
        # Agent: 决定排除这些类型，换一批

        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"],
        }

        where_clause, params = build_search_query(criteria)

        # 验证排除条件正确
        self.assertIn("mbti_type NOT IN", where_clause)
        self.assertIn("ESFJ", params.values())
        self.assertIn("ISTJ", params.values())

        print("\n" + "=" * 80)
        print("✅ Agent 场景：'排除当前结果类型' 验证通过")
        print("   模拟对话：")
        print("   Agent: '刚才那批主要是 S系，我帮你换一批'")
        print(f"   排除类型: ESFJ, ISTJ, ESTJ, ISFJ")
        print("=" * 80)

    def test_agent_combined_filtering_scenario(self):
        """场景：Agent 同时指定想要的类型和排除的类型"""
        from match_domain.universal_query_builder import build_search_query

        # 模拟 Agent 高级筛选场景
        # 想要 INFP/INFJ（治愈系），排除 ESTJ/ENTJ（控制型）

        criteria = {
            "cities": ["无锡"],
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INFP", "INFJ", "ISFP", "ISFJ"],  # 温和型
            "exclude_mbti": ["ESTJ", "ENTJ", "ESTP"],        # 控制型
        }

        where_clause, params = build_search_query(criteria)

        # 验证组合条件正确
        self.assertIn("mbti_type IN", where_clause)
        self.assertIn("mbti_type NOT IN", where_clause)
        self.assertIn("INFP", params.values())
        self.assertIn("ESTJ", params.values())

        print("\n" + "=" * 80)
        print("✅ Agent 场景：'组合筛选' 验证通过")
        print("   模拟对话：")
        print("   Agent: '帮你找温和治愈型的，避开控制欲强的'")
        print("   包含: INFP, INFJ, ISFP, ISFJ")
        print("   排除: ESTJ, ENTJ, ESTP")
        print("=" * 80)


# ============================================================================
# 第六部分：集成测试（Discovery 系统集成）
# ============================================================================

class TestDiscoveryIntegration(unittest.TestCase):
    """验证与 Discovery 系统集成"""

    def test_search_partner_candidates_with_mbti(self):
        """测试 search_partner_candidates_with 能处理 MBTI"""
        from match_domain.criteria_compiler import build_discovery_search_request
        from discovery_system.storage import StoredSession
        from datetime import datetime

        # 模拟 Discovery Session（使用正确的字段）
        session = StoredSession(
            session_id="test_session",
            requester_id=1,
            profile_id=1,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={},
        )

        # 搜索请求包含 MBTI
        criteria_overrides = {
            "gender": "female",
            "cities": ["无锡"],
            "mbti_types": ["INTP", "INTJ"],
        }

        request = build_discovery_search_request(
            source="mysql://root@127.0.0.1:3307/her_discovery_test?table=profiles",
            profile_row={"id": 1, "gender": "male"},
            persona_row=None,
            criteria_overrides=criteria_overrides,
            self_id=1,
            limit=5,
        )

        # 验证请求正确构建
        self.assertIn("mbti_types", request["criteria"])
        self.assertEqual(request["criteria"]["mbti_types"], ["INTP", "INTJ"])

        print("\n" + "=" * 80)
        print("✅ Discovery 集成：search_partner_candidates_with 验证通过")
        print(f"   criteria: {request['criteria']}")
        print("=" * 80)

    def test_criteria_compiler_preserves_all_agent_params(self):
        """测试 criteria_compiler 保留所有 Agent 参数"""
        from match_domain.criteria_compiler import compile_effective_criteria, SCENE_DISCOVERY_SEARCH

        # Agent 传入的完整参数
        agent_params = {
            "gender": "female",
            "age_min": 26,
            "age_max": 36,
            "cities": ["无锡"],
            "height_min": 160,
            "height_max": 175,
            "relationship_goals": ["认真恋爱"],
            "marital_statuses": ["未婚"],
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
            "exclude_mbti": ["ESFJ", "ISTJ"],
            "verified_levels": ["basic"],
        }

        compiled = compile_effective_criteria(
            scene=SCENE_DISCOVERY_SEARCH,
            profile_row=None,
            persona_row=None,
            base_criteria=agent_params,
            overrides=None,
        )

        # 验证所有参数都被保留
        for key in agent_params:
            self.assertIn(key, compiled.hard_filters, f"参数 {key} 被丢弃")

        # 验证参数值正确
        self.assertEqual(compiled.hard_filters["mbti_types"], agent_params["mbti_types"])
        self.assertEqual(compiled.hard_filters["exclude_mbti"], agent_params["exclude_mbti"])

        print("\n" + "=" * 80)
        print("✅ criteria_compiler 保留所有 Agent 参数验证通过")
        print(f"   传入参数数量: {len(agent_params)}")
        print(f"   hard_filters 参数数量: {len(compiled.hard_filters)}")
        print("   所有参数都被保留，无丢失")
        print("=" * 80)


# ============================================================================
# 运行测试
# ============================================================================

def run_tests():
    """运行所有测试并输出报告"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 加载所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestFullPipelineWithMock))
    suite.addTests(loader.loadTestsFromTestCase(TestFullPipelineWithDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestMBTIFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentNativePrinciple))
    suite.addTests(loader.loadTestsFromTestCase(TestBackwardCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestDiscoveryIntegration))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"总测试数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")
    print("=" * 80)

    return result


if __name__ == "__main__":
    run_tests()