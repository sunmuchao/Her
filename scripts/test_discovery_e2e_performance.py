#!/usr/bin/env python3
"""发现页端到端性能测试 - 实际测量各阶段耗时

测试目标：
1. 测量完整对话流程的各阶段实际耗时
2. 验证估算数据的准确性
3. 识别真实的性能瓶颈
4. 收集监控数据用于优化分析

关键测试阶段：
- HTTP层耗时
- Agent决策耗时(LLM调用)
- 并行加载耗时(用户资料+Persona)
- 结构化查询耗时(MySQL)
- 向量筛选耗时(Embedding+向量库)
- 性格特质加载耗时
- 排序筛选耗时
- 卡片构建耗时
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Sequence

# 设置路径
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = REPO_ROOT / "external-systems" / "partner-discovery-system"
GATEWAY_ROOT = REPO_ROOT / "external-systems" / "partner-http-gateway"
MATCH_DOMAIN_ROOT = REPO_ROOT / "match_domain"
PARTNER_SEARCH_ROOT = REPO_ROOT / "partner_search"

for root in (REPO_ROOT, DISCOVERY_ROOT, GATEWAY_ROOT, MATCH_DOMAIN_ROOT, PARTNER_SEARCH_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_logger = logging.getLogger(__name__)

# 导入依赖
try:
    from discovery_system.service import DiscoveryService
    from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession
    from discovery_system.agent_runtime import create_default_discovery_agent_runtime
    from discovery_system.service_integrations import (
        search_partner_candidates_with,
        load_requester_profile_with,
        load_persona_memory_bindings,
    )
    from partner_search import load_self_profile, search_profiles
    from partner_search.personality_traits_reader import (
        load_traits_for_discovery,
        load_traits_for_profiles,
    )
    from match_domain.criteria_compiler import build_discovery_search_request
    from match_domain.vector_filter import vector_filter_candidates
    from match_domain.persona_loader import load_persona_for_discovery
    from match_domain.vector_store_lite import VectorStoreLite
    from match_domain.embedding_service import EmbeddingService
    from outer_mysql_compat import MySQLCompatConnection
    from her_runtime_context import get_trace_id
except ImportError as e:
    _logger.error(f"导入依赖失败: {e}")
    _logger.error("请确保在正确的环境中运行此脚本")
    sys.exit(1)


@dataclass
class StageTiming:
    """单个阶段耗时记录"""
    stage_name: str
    elapsed_ms: float
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "success": self.success,
            "metadata": self.metadata,
        }


@dataclass
class TurnPerformanceResult:
    """一轮对话的性能测试结果"""
    test_name: str
    user_message: str
    total_ms: float
    stage_timings: list[StageTiming]
    success: bool
    error_message: str | None = None
    result_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "user_message": self.user_message,
            "total_ms": round(self.total_ms, 3),
            "success": self.success,
            "error_message": self.error_message,
            "result_count": self.result_count,
            "stage_timings": [timing.to_dict() for timing in self.stage_timings],
            "stage_breakdown": self._build_breakdown(),
        }

    def _build_breakdown(self) -> dict[str, Any]:
        """构建耗时占比分析"""
        if not self.stage_timings:
            return {}

        breakdown = {}
        for timing in self.stage_timings:
            percentage = (timing.elapsed_ms / self.total_ms * 100) if self.total_ms > 0 else 0
            breakdown[timing.stage_name] = {
                "elapsed_ms": round(timing.elapsed_ms, 3),
                "percentage": round(percentage, 2),
                "success": timing.success,
            }

        # 按耗时排序
        return dict(sorted(breakdown.items(), key=lambda x: x[1]["elapsed_ms"], reverse=True))


@contextmanager
def timing_context(stage_name: str, timings: list[StageTiming], **metadata):
    """测量阶段耗时的上下文管理器"""
    start_time = time.perf_counter()
    success = True
    try:
        yield
    except Exception as e:
        success = False
        metadata["error"] = str(e)[:200]
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        timings.append(StageTiming(stage_name, elapsed_ms, success, metadata))


class DiscoveryEndToEndPerformanceTester:
    """发现页端到端性能测试器"""

    def __init__(
        self,
        *,
        requester_id: int = 70001,
        profile_id: int = 10001,
        source: str = "mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
        persona_source: str | None = None,
    ):
        self.requester_id = requester_id
        self.profile_id = profile_id
        self.source = source
        self.persona_source = persona_source or source

        # 创建服务实例
        self.storage = InMemoryDiscoveryStorage()
        self.runtime = create_default_discovery_agent_runtime()
        self.service = DiscoveryService(
            storage=self.storage,
            runtime=self.runtime,
        )

        self.session_id: str | None = None

        _logger.info(f"性能测试器初始化完成: requester_id={requester_id}, profile_id={profile_id}")

    def setup_test_session(self) -> str:
        """创建测试会话"""
        with timing_context("create_session", []) as timings:
            session_result = self.service.create_session(
                requester_id=self.requester_id,
                profile_id=self.profile_id,
                now=datetime(2026, 6, 23, 10, 0, 0),
            )
            # 修正: session_id在session字典中
            self.session_id = session_result["session"]["session_id"]
            _logger.info(f"测试会话创建成功: session_id={self.session_id}")
        return self.session_id

    def test_full_turn_performance(
        self,
        user_message: str,
        *,
        test_name: str = "full_turn",
    ) -> TurnPerformanceResult:
        """测试完整对话轮次的性能"""

        if not self.session_id:
            self.setup_test_session()

        timings: list[StageTiming] = []
        success = True
        error_message = None
        result_count = 0

        _logger.info(f"开始完整对话测试: test_name={test_name}, message={user_message}")

        total_start = time.perf_counter()

        try:
            # Step 1: 会话上下文构建
            with timing_context("session_context_build", timings):
                session = self.storage.get_session(self.session_id)
                if not session:
                    raise ValueError(f"Session not found: {self.session_id}")
                _logger.info(f"会话上下文构建完成: phase={session.phase}")

            # Step 2: Agent决策(包含LLM调用)
            _logger.info("开始Agent决策...")
            with timing_context("agent_decision_llm", timings, message_length=len(user_message)):
                turn_result = self.service.process_turn(
                    session_id=self.session_id,
                    user_message_text=user_message,
                    now=datetime(2026, 6, 23, 10, 1, 0),
                )
                _logger.info("Agent决策完成")

            # Step 3: 分析返回结果
            timeline = turn_result.get("timeline") or []
            for item in timeline:
                if item.get("item_type") == "result_group":
                    cards = item.get("cards") or []
                    result_count = len(cards)

            _logger.info(f"返回结果数量: {result_count}")

        except Exception as e:
            success = False
            error_message = str(e)[:500]
            _logger.error(f"对话测试失败: {e}")
            timings.append(StageTiming("error", 0.0, False, {"error": error_message}))

        total_ms = (time.perf_counter() - total_start) * 1000.0

        return TurnPerformanceResult(
            test_name=test_name,
            user_message=user_message,
            total_ms=total_ms,
            stage_timings=timings,
            success=success,
            error_message=error_message,
            result_count=result_count,
        )

    def test_search_candidates_detailed_performance(
        self,
        criteria: dict[str, Any],
        *,
        limit: int = 5,
        test_name: str = "search_candidates_detailed",
    ) -> TurnPerformanceResult:
        """测试搜索候选人的详细性能(分阶段测量)"""

        if not self.session_id:
            self.setup_test_session()

        session = self.storage.get_session(self.session_id)
        if not session:
            raise ValueError(f"Session not found: {self.session_id}")

        timings: list[StageTiming] = []
        success = True
        error_message = None
        result_count = 0

        _logger.info(f"开始搜索候选人详细测试: test_name={test_name}")
        _logger.info(f"搜索条件: {json.dumps(criteria, ensure_ascii=False)}")

        total_start = time.perf_counter()

        try:
            # Step 1: 并行加载用户资料和Persona
            _logger.info("Step 1: 并行加载用户资料和Persona...")
            with timing_context("parallel_load_profile_persona", timings):
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    profile_future = executor.submit(
                        load_self_profile,
                        source=self.source,
                        profile_id=self.profile_id,
                    )
                    persona_future = executor.submit(
                        load_persona_for_discovery,
                        source=self.persona_source,
                        profile_id=self.profile_id,
                        requester_id=self.requester_id,
                    )

                    self_profile = profile_future.result()
                    persona_row = persona_future.result()

                _logger.info(f"用户资料加载完成: {self_profile.get('city', 'N/A')}")
                _logger.info(f"Persona加载完成: {persona_row.get('profile_id', 'N/A')}")

            # Step 2: 编译搜索请求
            _logger.info("Step 2: 编译搜索请求...")
            with timing_context("compile_search_request", timings):
                compiled_request = build_discovery_search_request(
                    source=self.source,
                    profile_row=self_profile,
                    persona_row=persona_row,
                    criteria_overrides=criteria,
                    self_id=self.profile_id,
                    limit=limit,
                )
                _logger.info(f"搜索请求编译完成: criteria_keys={list(compiled_request.get('criteria', {}).keys())}")

            # Step 3: 执行结构化搜索(MySQL)
            _logger.info("Step 3: 执行结构化搜索(MySQL)...")
            with timing_context("structured_search_mysql", timings):
                search_response = search_profiles(
                    source=self.source,
                    criteria=compiled_request.get("criteria") or {},
                    limit=limit,
                )
                _logger.info(f"MySQL搜索完成: result_count={search_response.get('result_count', 0)}")

            # Step 4: 向量筛选(如果有)
            results = search_response.get("results") or []
            if results and criteria.get("personality_match_json"):
                _logger.info("Step 4: 向量筛选...")
                personality_match = criteria.get("personality_match_json")
                with timing_context("vector_filter_embedding", timings, candidates_count=len(results)):
                    # 测量Embedding API调用耗时
                    embedding_start = time.perf_counter()

                    embedding_service = EmbeddingService()
                    query_text = personality_match.get("match_traits", [""])[0]

                    try:
                        # 使用asyncio调用embedding服务
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        query_vector = loop.run_until_complete(
                            embedding_service.generate_embedding(query_text)
                        )
                        loop.close()
                    except Exception as e:
                        _logger.warning(f"Embedding调用失败(可能未配置): {e}")
                        query_vector = None

                    embedding_elapsed = (time.perf_counter() - embedding_start) * 1000.0
                    _logger.info(f"Embedding API耗时: {embedding_elapsed:.3f}ms")

                    if query_vector:
                        # 测量向量库查询耗时
                        vector_store_start = time.perf_counter()

                        try:
                            vector_store = VectorStoreLite()
                            # 模拟向量查询
                            similar_users = vector_store.search_similar_users(
                                query_vector=query_vector,
                                top_k=len(results),
                            )
                        except Exception as e:
                            _logger.warning(f"向量库查询失败(可能未配置): {e}")
                            similar_users = []

                        vector_store_elapsed = (time.perf_counter() - vector_store_start) * 1000.0
                        _logger.info(f"向量库查询耗时: {vector_store_elapsed:.3f}ms")

                        # 添加向量库查询作为单独的timing
                        timings.append(
                            StageTiming(
                                "vector_store_query",
                                vector_store_elapsed,
                                True,
                                {"similar_users_count": len(similar_users)},
                            )
                        )

            # Step 5: 性格特质加载
            if results:
                candidate_ids = [int(r.get("id") or r.get("profile_id") or 0) for r in results]
                _logger.info("Step 5: 加载性格特质...")
                with timing_context("load_personality_traits", timings, candidates_count=len(candidate_ids)):
                    try:
                        traits_map = load_traits_for_profiles(
                            source=self.persona_source,
                            profile_ids=candidate_ids,
                        )
                        _logger.info(f"性格特质加载完成: traits_count={len(traits_map)}")
                    except Exception as e:
                        _logger.warning(f"性格特质加载失败: {e}")
                        traits_map = {}

            # Step 6: 排序筛选(多样性)
            _logger.info("Step 6: 排序筛选...")
            with timing_context("ranking_sort", timings, results_count=len(results)):
                # 模拟排序
                sorted_results = sorted(
                    results,
                    key=lambda r: float(r.get("score") or r.get("fit_score") or 0),
                    reverse=True,
                )
                _logger.info(f"排序完成: sorted_count={len(sorted_results)}")

            # Step 7: 构建候选人卡片
            _logger.info("Step 7: 构建候选人卡片...")
            with timing_context("build_candidate_cards", timings, cards_count=len(results)):
                from discovery_system.view_models import build_candidate_card

                cards = []
                for candidate in sorted_results[:limit]:
                    try:
                        card = build_candidate_card(candidate, reason_summary="测试推荐")
                        cards.append(card)
                    except Exception as e:
                        _logger.warning(f"卡片构建失败: {e}")

                result_count = len(cards)
                _logger.info(f"卡片构建完成: cards_count={result_count}")

            _logger.info(f"搜索候选人测试完成: total_results={result_count}")

        except Exception as e:
            success = False
            error_message = str(e)[:500]
            _logger.error(f"搜索候选人测试失败: {e}")
            timings.append(StageTiming("error", 0.0, False, {"error": error_message}))

        total_ms = (time.perf_counter() - total_start) * 1000.0

        return TurnPerformanceResult(
            test_name=test_name,
            user_message=json.dumps(criteria, ensure_ascii=False),
            total_ms=total_ms,
            stage_timings=timings,
            success=success,
            error_message=error_message,
            result_count=result_count,
        )


def run_end_to_end_performance_tests(
    *,
    requester_id: int = 70001,
    profile_id: int = 10001,
    source: str = "mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
    repeat: int = 3,
    output_json: str | None = None,
) -> dict[str, Any]:
    """运行端到端性能测试套件"""

    _logger.info("=" * 80)
    _logger.info("开始发现页端到端性能测试")
    _logger.info("=" * 80)
    _logger.info(f"测试配置: requester_id={requester_id}, profile_id={profile_id}, repeat={repeat}")
    _logger.info(f"数据源: {source}")

    tester = DiscoveryEndToEndPerformanceTester(
        requester_id=requester_id,
        profile_id=profile_id,
        source=source,
    )

    # 测试场景列表
    test_scenarios = [
        {
            "test_name": "simple_intent",
            "description": "简单意图识别",
            "message": "我想找个温柔的女生",
        },
        {
            "test_name": "complex_criteria",
            "description": "复杂搜索条件",
            "message": "我想找个25-30岁、苏州、不抽烟、温柔、内向的女生",
        },
        {
            "test_name": "refresh_batch",
            "description": "换一批场景",
            "message": "换一批看看",
        },
    ]

    # 详细搜索测试场景
    search_scenarios = [
        {
            "test_name": "basic_search",
            "description": "基础结构化搜索",
            "criteria": {
                "gender": "女",
                "cities": ["苏州"],
                "age_min": 25,
                "age_max": 30,
            },
            "limit": 5,
        },
        {
            "test_name": "complex_search",
            "description": "复杂条件搜索",
            "criteria": {
                "gender": "女",
                "cities": ["苏州", "上海"],
                "age_min": 25,
                "age_max": 30,
                "relationship_goals": ["认真恋爱"],
            },
            "limit": 10,
        },
    ]

    all_results: list[dict[str, Any]] = []

    # 运行完整对话测试
    _logger.info("=" * 80)
    _logger.info("Part 1: 完整对话轮次性能测试")
    _logger.info("=" * 80)

    for scenario in test_scenarios:
        scenario_results: list[dict[str, Any]] = []

        _logger.info(f"测试场景: {scenario['test_name']} - {scenario['description']}")

        for run_index in range(repeat):
            _logger.info(f"第 {run_index + 1}/{repeat} 次运行")

            # 每次运行前重置会话
            tester = DiscoveryEndToEndPerformanceTester(
                requester_id=requester_id,
                profile_id=profile_id,
                source=source,
            )

            result = tester.test_full_turn_performance(
                scenario["message"],
                test_name=scenario["test_name"],
            )
            scenario_results.append(result.to_dict())

        # 计算统计数据
        avg_total_ms = sum(r["total_ms"] for r in scenario_results) / len(scenario_results)
        success_rate = sum(1 for r in scenario_results if r["success"]) / len(scenario_results)

        # 汇总各阶段平均耗时
        stage_avg_timings: dict[str, dict[str, float]] = {}
        for report in scenario_results:
            for stage in report.get("stage_timings") or []:
                stage_name = stage["stage_name"]
                elapsed_ms = stage["elapsed_ms"]
                if stage_name not in stage_avg_timings:
                    stage_avg_timings[stage_name] = {"elapsed_ms": 0.0, "count": 0}
                stage_avg_timings[stage_name]["elapsed_ms"] += elapsed_ms
                stage_avg_timings[stage_name]["count"] += 1

        for stage_name in stage_avg_timings:
            count = stage_avg_timings[stage_name]["count"]
            stage_avg_timings[stage_name]["elapsed_ms"] /= count
            stage_avg_timings[stage_name]["avg_ms"] = round(
                stage_avg_timings[stage_name]["elapsed_ms"], 3
            )

        all_results.append({
            "test_name": scenario["test_name"],
            "description": scenario["description"],
            "user_message": scenario["message"],
            "repeat_count": repeat,
            "avg_total_ms": round(avg_total_ms, 3),
            "success_rate": round(success_rate * 100, 2),
            "stage_avg_timings": dict(
                sorted(
                    stage_avg_timings.items(),
                    key=lambda x: x[1]["elapsed_ms"],
                    reverse=True,
                )
            ),
            "runs": scenario_results,
        })

    # 运行详细搜索测试
    _logger.info("=" * 80)
    _logger.info("Part 2: 搜索候选人详细性能测试")
    _logger.info("=" * 80)

    for scenario in search_scenarios:
        scenario_results: list[dict[str, Any]] = []

        _logger.info(f"测试场景: {scenario['test_name']} - {scenario['description']}")

        for run_index in range(repeat):
            _logger.info(f"第 {run_index + 1}/{repeat} 次运行")

            # 每次运行前重置会话
            tester = DiscoveryEndToEndPerformanceTester(
                requester_id=requester_id,
                profile_id=profile_id,
                source=source,
            )

            result = tester.test_search_candidates_detailed_performance(
                scenario["criteria"],
                limit=scenario["limit"],
                test_name=scenario["test_name"],
            )
            scenario_results.append(result.to_dict())

        # 计算统计数据
        avg_total_ms = sum(r["total_ms"] for r in scenario_results) / len(scenario_results)
        success_rate = sum(1 for r in scenario_results if r["success"]) / len(scenario_results)

        # 汇总各阶段平均耗时
        stage_avg_timings: dict[str, dict[str, float]] = {}
        for report in scenario_results:
            for stage in report.get("stage_timings") or []:
                stage_name = stage["stage_name"]
                elapsed_ms = stage["elapsed_ms"]
                if stage_name not in stage_avg_timings:
                    stage_avg_timings[stage_name] = {"elapsed_ms": 0.0, "count": 0}
                stage_avg_timings[stage_name]["elapsed_ms"] += elapsed_ms
                stage_avg_timings[stage_name]["count"] += 1

        for stage_name in stage_avg_timings:
            count = stage_avg_timings[stage_name]["count"]
            stage_avg_timings[stage_name]["elapsed_ms"] /= count
            stage_avg_timings[stage_name]["avg_ms"] = round(
                stage_avg_timings[stage_name]["elapsed_ms"], 3
            )

        all_results.append({
            "test_name": scenario["test_name"],
            "description": scenario["description"],
            "criteria": scenario["criteria"],
            "limit": scenario["limit"],
            "repeat_count": repeat,
            "avg_total_ms": round(avg_total_ms, 3),
            "success_rate": round(success_rate * 100, 2),
            "stage_avg_timings": dict(
                sorted(
                    stage_avg_timings.items(),
                    key=lambda x: x[1]["elapsed_ms"],
                    reverse=True,
                )
            ),
            "runs": scenario_results,
        })

    # 构建完整报告
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "test_config": {
            "requester_id": requester_id,
            "profile_id": profile_id,
            "source": source,
            "repeat": repeat,
        },
        "scenarios": all_results,
        "performance_summary": _build_performance_summary(all_results),
    }

    # 输出JSON报告
    if output_json:
        output_path = pathlib.Path(output_json)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _logger.info(f"JSON报告已保存: {output_path}")

    return report


def _build_performance_summary(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """构建性能摘要"""

    # 收集所有阶段耗时
    all_stage_timings: dict[str, list[float]] = {}
    total_elapsed_list: list[float] = []

    for scenario in scenarios:
        total_elapsed_list.append(scenario["avg_total_ms"])

        for stage_name, stage_data in scenario.get("stage_avg_timings") or {}.items():
            if stage_name not in all_stage_timings:
                all_stage_timings[stage_name] = []
            all_stage_timings[stage_name].append(stage_data["elapsed_ms"])

    # 计算各阶段平均耗时
    stage_avg_summary: dict[str, dict[str, float]] = {}
    for stage_name, timings_list in all_stage_timings.items():
        avg_ms = sum(timings_list) / len(timings_list)
        stage_avg_summary[stage_name] = {
            "avg_ms": round(avg_ms, 3),
            "occurrence_rate": round(len(timings_list) / len(scenarios) * 100, 2),
        }

    # 按耗时排序
    sorted_stage_summary = dict(
        sorted(stage_avg_summary.items(), key=lambda x: x[1]["avg_ms"], reverse=True)
    )

    # 计算总体平均耗时
    overall_avg_ms = sum(total_elapsed_list) / len(total_elapsed_list) if total_elapsed_list else 0

    # 计算各阶段占比
    stage_percentage: dict[str, float] = {}
    for stage_name, stage_data in sorted_stage_summary.items():
        percentage = (stage_data["avg_ms"] / overall_avg_ms * 100) if overall_avg_ms > 0 else 0
        stage_percentage[stage_name] = round(percentage, 2)

    return {
        "overall_avg_ms": round(overall_avg_ms, 3),
        "stage_avg_summary": sorted_stage_summary,
        "stage_percentage": stage_percentage,
        "top_bottlenecks": list(sorted_stage_summary.keys())[:5],
    }


def print_performance_report(report: dict[str, Any]) -> None:
    """打印性能测试报告"""

    print("=" * 80)
    print("发现页端到端性能测试报告")
    print("=" * 80)
    print(f"生成时间: {report['generated_at']}")
    print(f"测试配置: requester_id={report['test_config']['requester_id']}, "
          f"profile_id={report['test_config']['profile_id']}, "
          f"repeat={report['test_config']['repeat']}")
    print("=" * 80)

    # 打印性能摘要
    summary = report.get("performance_summary") or {}
    print()
    print("【性能摘要】")
    print(f"  总体平均耗时: {summary.get('overall_avg_ms', 0)} ms")
    print()
    print("  各阶段平均耗时(按耗时排序):")
    for stage_name, stage_data in summary.get("stage_avg_summary") or {}.items():
        percentage = summary.get("stage_percentage") or {}
        pct = percentage.get(stage_name, 0)
        occurrence = stage_data.get("occurrence_rate", 0)
        print(f"    {stage_name}: {stage_data['avg_ms']} ms ({pct}% 总耗时, 出现率{occurrence}%)")

    print()
    print(f"  主要瓶颈(top 5): {summary.get('top_bottlenecks', [])}")
    print("=" * 80)

    # 打印各测试场景详情
    for scenario in report.get("scenarios") or []:
        print()
        print(f"【{scenario['test_name']}】{scenario['description']}")
        if "user_message" in scenario:
            print(f"  用户消息: {scenario['user_message']}")
        elif "criteria" in scenario:
            print(f"  搜索条件: {json.dumps(scenario['criteria'], ensure_ascii=False)}")
            print(f"  数量限制: {scenario['limit']}")

        print(f"  平均总耗时: {scenario['avg_total_ms']} ms")
        print(f"  成功率: {scenario['success_rate']}%")
        print()
        print("  各阶段详细耗时:")
        for stage_name, stage_data in scenario.get("stage_avg_timings") or {}.items():
            avg_ms = stage_data.get("avg_ms", stage_data.get("elapsed_ms", 0))
            print(f"    {stage_name}: {avg_ms} ms")
        print("-" * 80)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发现页端到端性能测试")
    parser.add_argument("--requester-id", type=int, default=70001)
    parser.add_argument("--profile-id", type=int, default=10001)
    parser.add_argument(
        "--source",
        default="mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output-json", default="/tmp/discovery_e2e_perf_report.json")

    args = parser.parse_args(argv)

    report = run_end_to_end_performance_tests(
        requester_id=args.requester_id,
        profile_id=args.profile_id,
        source=args.source,
        repeat=args.repeat,
        output_json=args.output_json,
    )

    print_performance_report(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())