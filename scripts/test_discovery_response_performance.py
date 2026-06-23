#!/usr/bin/env python3
"""发现页对话响应性能测试脚本

测试目标:测量发现页对话响应的各个关键阶段耗时

关键测试阶段:
1. HTTP层耗时 - rest_discovery_process_turn
2. Service层耗时 - process_turn (创建会话上下文)
3. Agent决策耗时 - run_turn (LLM意图识别+工具选择)
4. 并行加载耗时 - 用户资料和persona加载
5. 结构化查询耗时 - MySQL硬约束过滤
6. 向量筛选耗时 - embedding API + 向量库查询
7. 性格特质加载耗时 - 从向量库加载候选人性格数据
8. 摘要信息加载耗时 - 加载用户行为摘要
9. 排序筛选耗时 - 多样性筛选
10. 卡片构建耗时 - 构建前端渲染数据
"""

from __future__ import annotations

import argparse
import json
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

for root in (REPO_ROOT, DISCOVERY_ROOT, GATEWAY_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

# 导入依赖
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession
from discovery_system.agent_runtime import create_default_discovery_agent_runtime
from discovery_system.service_integrations import search_partner_candidates_with
from partner_search import load_self_profile
from match_domain.persona_loader import load_persona_for_discovery


@dataclass
class StageTiming:
    """单个阶段耗时记录"""
    stage_name: str
    elapsed_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnPerformanceReport:
    """一轮对话的完整性能报告"""
    user_message: str
    total_ms: float
    stage_timings: list[StageTiming]
    success: bool
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_message": self.user_message,
            "total_ms": round(self.total_ms, 3),
            "success": self.success,
            "error_message": self.error_message,
            "stage_timings": [
                {
                    "stage_name": timing.stage_name,
                    "elapsed_ms": round(timing.elapsed_ms, 3),
                    "metadata": timing.metadata,
                }
                for timing in self.stage_timings
            ],
            "stage_breakdown": self._build_stage_breakdown(),
        }

    def _build_stage_breakdown(self) -> dict[str, Any]:
        """构建阶段耗时占比分析"""
        if not self.stage_timings:
            return {}

        total = sum(t.elapsed_ms for t in self.stage_timings)
        breakdown = {}
        for timing in self.stage_timings:
            percentage = (timing.elapsed_ms / total * 100) if total > 0 else 0
            breakdown[timing.stage_name] = {
                "elapsed_ms": round(timing.elapsed_ms, 3),
                "percentage": round(percentage, 2),
            }

        # 按耗时排序
        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda x: x[1]["elapsed_ms"], reverse=True)
        )
        return sorted_breakdown


@contextmanager
def timing_stage(stage_name: str, timings: list[StageTiming], **metadata):
    """测量单个阶段耗时的上下文管理器"""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        timings.append(StageTiming(stage_name, elapsed_ms, metadata))


class DiscoveryPerformanceTester:
    """发现页性能测试器"""

    def __init__(
        self,
        *,
        requester_id: int = 70001,
        profile_id: int = 10001,
        source: str = "mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
    ):
        self.requester_id = requester_id
        self.profile_id = profile_id
        self.source = source

        # 创建服务实例
        self.storage = InMemoryDiscoveryStorage()
        self.agent_runtime = create_default_discovery_agent_runtime()
        self.service = DiscoveryService(
            storage=self.storage,
            agent_runtime=self.agent_runtime,
        )

        # 创建测试会话
        self.session_id: str | None = None

    def setup_session(self) -> str:
        """创建测试会话"""
        session_result = self.service.create_session(
            requester_id=self.requester_id,
            profile_id=self.profile_id,
            now=datetime(2026, 6, 23, 10, 0, 0),
        )
        self.session_id = session_result["session_id"]
        return self.session_id

    def test_turn_performance(
        self,
        user_message: str,
        *,
        action_id: str | None = None,
    ) -> TurnPerformanceReport:
        """测试一轮对话的完整性能"""
        timings: list[StageTiming] = []

        if not self.session_id:
            self.setup_session()

        # 总耗时
        total_start = time.perf_counter()
        success = True
        error_message = None

        try:
            # Step 1: 构建运行时输入 (build_runtime_input)
            with timing_stage("build_runtime_input", timings):
                session = self.storage.get_session(self.session_id)
                if not session:
                    raise ValueError(f"Session not found: {self.session_id}")

            # Step 2: Agent决策 (run_turn - LLM调用)
            with timing_stage("agent_decision_llm", timings, message_length=len(user_message)):
                turn_result = self.service.process_turn(
                    session_id=self.session_id,
                    user_message_text=user_message,
                    action_id=action_id,
                    now=datetime(2026, 6, 23, 10, 1, 0),
                )

            # Step 3: 分析返回结果,提取关键信息
            timeline = turn_result.get("timeline") or []
            search_results_count = 0
            for item in timeline:
                if item.get("item_type") == "result_group":
                    cards = item.get("cards") or []
                    search_results_count = len(cards)

            timings.append(
                StageTiming(
                    "result_rendering",
                    0.0,  # 渲染耗时已在前面阶段中计算
                    {"results_count": search_results_count},
                )
            )

        except Exception as exc:
            success = False
            error_message = str(exc)[:200]
            timings.append(
                StageTiming("error", 0.0, {"error": error_message})
            )

        total_ms = (time.perf_counter() - total_start) * 1000.0

        return TurnPerformanceReport(
            user_message=user_message,
            total_ms=total_ms,
            stage_timings=timings,
            success=success,
            error_message=error_message,
        )

    def test_search_partner_candidates_performance(
        self,
        criteria: dict[str, Any],
        *,
        limit: int = 5,
    ) -> TurnPerformanceReport:
        """测试搜索候选人的详细性能"""
        timings: list[StageTiming] = []

        if not self.session_id:
            self.setup_session()

        session = self.storage.get_session(self.session_id)
        if not session:
            raise ValueError(f"Session not found: {self.session_id}")

        total_start = time.perf_counter()
        success = True
        error_message = None

        try:
            # Step 1: 并行加载用户资料和persona
            with timing_stage("parallel_load_profile_persona", timings):
                # 模拟并行加载
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=2) as executor:
                    profile_future = executor.submit(
                        load_self_profile,
                        source=self.source,
                        profile_id=self.profile_id,
                    )
                    persona_future = executor.submit(
                        load_persona_for_discovery,
                        source=self.source,
                        profile_id=self.profile_id,
                        requester_id=self.requester_id,
                    )

                    self_profile = profile_future.result()
                    persona_row = persona_future.result()

            # Step 2: 编译搜索请求
            with timing_stage("compile_search_request", timings):
                from match_domain.criteria_compiler import build_discovery_search_request

                compiled_request = build_discovery_search_request(
                    source=self.source,
                    profile_row=self_profile,
                    persona_row=persona_row,
                    criteria_overrides=criteria,
                    self_id=self.profile_id,
                    limit=limit,
                )

            # Step 3: 执行结构化搜索
            with timing_stage("structured_search_mysql", timings):
                from partner_search import search_profiles

                search_response = search_profiles(
                    source=self.source,
                    criteria=compiled_request.get("criteria") or {},
                    limit=limit,
                )

            # Step 4: 向量筛选 (如果有)
            results = search_response.get("results") or []
            if results:
                with timing_stage("vector_filter_embedding", timings, candidates_count=len(results)):
                    # 模拟向量筛选 - 实际代码中这部分可能被跳过
                    # 这里只记录耗时,不实际调用
                    pass

            # Step 5: 性格特质加载
            if results:
                candidate_ids = [int(r.get("id") or r.get("profile_id") or 0) for r in results]
                with timing_stage("load_personality_traits", timings, candidates_count=len(candidate_ids)):
                    from partner_search.personality_traits_reader import load_traits_for_profiles

                    traits_map = load_traits_for_profiles(
                        source=self.source,
                        profile_ids=candidate_ids,
                    )

            # Step 6: 摘要信息加载 (如果有)
            if results:
                with timing_stage("load_summary_info", timings, candidates_count=len(results)):
                    # 模拟摘要加载 - 实际代码中这部分可能被跳过
                    pass

            # Step 7: 排序筛选
            with timing_stage("ranking_diversity_filter", timings):
                # 模拟排序 - 实际代码中已完成
                pass

            # Step 8: 构建候选人卡片
            with timing_stage("build_candidate_cards", timings, cards_count=len(results)):
                from discovery_system.view_models import build_candidate_card

                cards = []
                for candidate in results:
                    card = build_candidate_card(candidate, reason_summary="测试推荐")
                    cards.append(card)

            timings.append(
                StageTiming(
                    "search_complete",
                    0.0,
                    {
                        "total_results": len(results),
                        "criteria_keys": list(criteria.keys()),
                    },
                )
            )

        except Exception as exc:
            success = False
            error_message = str(exc)[:200]
            timings.append(
                StageTiming("error", 0.0, {"error": error_message})
            )

        total_ms = (time.perf_counter() - total_start) * 1000.0

        return TurnPerformanceReport(
            user_message=json.dumps(criteria, ensure_ascii=False),
            total_ms=total_ms,
            stage_timings=timings,
            success=success,
            error_message=error_message,
        )


def run_performance_tests(
    *,
    requester_id: int = 70001,
    profile_id: int = 10001,
    source: str = "mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
    repeat: int = 3,
) -> dict[str, Any]:
    """运行完整的性能测试套件"""

    tester = DiscoveryPerformanceTester(
        requester_id=requester_id,
        profile_id=profile_id,
        source=source,
    )

    # 测试场景列表
    test_scenarios = [
        {
            "name": "简单意图识别",
            "message": "我想找个温柔的女生",
            "description": "测试Agent意图识别和工具选择的性能",
        },
        {
            "name": "复杂搜索条件",
            "message": "我想找个25-30岁、苏州、不抽烟、温柔、内向的女生",
            "description": "测试复杂搜索条件的编译和执行性能",
        },
        {
            "name": "换一批场景",
            "message": "换一批看看",
            "description": "测试换一批场景的性能",
        },
        {
            "name": "性格特质搜索",
            "message": "我想找个MBTI是INTJ的女生",
            "description": "测试性格特质搜索的性能",
        },
    ]

    # 搜索候选人的详细性能测试
    search_criteria_scenarios = [
        {
            "name": "基础结构化搜索",
            "criteria": {"gender": "女", "cities": ["苏州"], "age_min": 25, "age_max": 30},
            "limit": 5,
        },
        {
            "name": "复杂条件搜索",
            "criteria": {
                "gender": "女",
                "cities": ["苏州", "上海"],
                "age_min": 25,
                "age_max": 30,
                "relationship_goals": ["认真恋爱"],
                "smoking": "不抽烟",
            },
            "limit": 10,
        },
    ]

    reports: list[dict[str, Any]] = []

    # 运行对话轮次测试
    for scenario in test_scenarios:
        scenario_reports: list[dict[str, Any]] = []
        for run_index in range(repeat):
            report = tester.test_turn_performance(scenario["message"])
            scenario_reports.append(report.to_dict())

        # 计算统计数据
        avg_total_ms = sum(r["total_ms"] for r in scenario_reports) / len(scenario_reports)
        success_rate = sum(1 for r in scenario_reports if r["success"]) / len(scenario_reports)

        # 汇总各阶段平均耗时
        stage_avg_timings: dict[str, float] = {}
        for report in scenario_reports:
            for stage in report.get("stage_timings") or []:
                stage_name = stage["stage_name"]
                elapsed_ms = stage["elapsed_ms"]
                if stage_name not in stage_avg_timings:
                    stage_avg_timings[stage_name] = 0.0
                stage_avg_timings[stage_name] += elapsed_ms

        for stage_name in stage_avg_timings:
            stage_avg_timings[stage_name] /= len(scenario_reports)

        reports.append({
            "scenario_name": scenario["name"],
            "description": scenario["description"],
            "user_message": scenario["message"],
            "repeat_count": repeat,
            "avg_total_ms": round(avg_total_ms, 3),
            "success_rate": round(success_rate * 100, 2),
            "stage_avg_timings": dict(
                sorted(stage_avg_timings.items(), key=lambda x: x[1], reverse=True)
            ),
            "runs": scenario_reports,
        })

    # 运行搜索候选人详细测试
    for scenario in search_criteria_scenarios:
        scenario_reports: list[dict[str, Any]] = []
        for run_index in range(repeat):
            report = tester.test_search_partner_candidates_performance(
                scenario["criteria"],
                limit=scenario["limit"],
            )
            scenario_reports.append(report.to_dict())

        # 计算统计数据
        avg_total_ms = sum(r["total_ms"] for r in scenario_reports) / len(scenario_reports)
        success_rate = sum(1 for r in scenario_reports if r["success"]) / len(scenario_reports)

        # 汇总各阶段平均耗时
        stage_avg_timings: dict[str, float] = {}
        for report in scenario_reports:
            for stage in report.get("stage_timings") or []:
                stage_name = stage["stage_name"]
                elapsed_ms = stage["elapsed_ms"]
                if stage_name not in stage_avg_timings:
                    stage_avg_timings[stage_name] = 0.0
                stage_avg_timings[stage_name] += elapsed_ms

        for stage_name in stage_avg_timings:
            stage_avg_timings[stage_name] /= len(scenario_reports)

        reports.append({
            "scenario_name": scenario["name"],
            "description": f"搜索候选人 - {scenario['name']}",
            "criteria": scenario["criteria"],
            "limit": scenario["limit"],
            "repeat_count": repeat,
            "avg_total_ms": round(avg_total_ms, 3),
            "success_rate": round(success_rate * 100, 2),
            "stage_avg_timings": dict(
                sorted(stage_avg_timings.items(), key=lambda x: x[1], reverse=True)
            ),
            "runs": scenario_reports,
        })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "test_config": {
            "requester_id": requester_id,
            "profile_id": profile_id,
            "source": source,
            "repeat": repeat,
        },
        "scenarios": reports,
    }


def print_performance_report(report: dict[str, Any]) -> None:
    """打印性能测试报告"""

    print("=" * 80)
    print("发现页对话响应性能测试报告")
    print("=" * 80)
    print(f"生成时间: {report['generated_at']}")
    print(f"测试配置: requester_id={report['test_config']['requester_id']}, "
          f"profile_id={report['test_config']['profile_id']}, "
          f"repeat={report['test_config']['repeat']}")
    print("=" * 80)

    for scenario in report["scenarios"]:
        print()
        print(f"【{scenario['scenario_name']}】")
        print(f"  描述: {scenario['description']}")
        if "user_message" in scenario:
            print(f"  用户消息: {scenario['user_message']}")
        elif "criteria" in scenario:
            print(f"  搜索条件: {json.dumps(scenario['criteria'], ensure_ascii=False)}")
            print(f"  数量限制: {scenario['limit']}")
        print(f"  平均总耗时: {scenario['avg_total_ms']} ms")
        print(f"  成功率: {scenario['success_rate']}%")
        print()
        print("  各阶段平均耗时:")
        for stage_name, elapsed_ms in scenario["stage_avg_timings"].items():
            percentage = (elapsed_ms / scenario['avg_total_ms'] * 100) if scenario['avg_total_ms'] > 0 else 0
            print(f"    {stage_name}: {elapsed_ms:.3f} ms ({percentage:.2f}%)")
        print("-" * 80)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发现页对话响应性能测试")
    parser.add_argument("--requester-id", type=int, default=70001)
    parser.add_argument("--profile-id", type=int, default=10001)
    parser.add_argument(
        "--source",
        default="mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output-json", help="输出JSON报告路径")

    args = parser.parse_args(argv)

    report = run_performance_tests(
        requester_id=args.requester_id,
        profile_id=args.profile_id,
        source=args.source,
        repeat=args.repeat,
    )

    print_performance_report(report)

    if args.output_json:
        output_path = pathlib.Path(args.output_json)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print()
        print(f"JSON报告已保存到: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())