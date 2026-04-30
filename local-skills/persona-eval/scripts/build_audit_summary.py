#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import summarize_agent_feedback


DEFAULT_SCOPE = [
    "multi-agent persona review",
    "persona-memory-sync accuracy audit",
    "public exposure audit",
    "partner-search satisfaction audit",
]

SATISFACTION_ALIASES = {
    "高": "high",
    "中": "medium",
    "低": "low",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

MEMORY_ISSUE_RULES = [
    ("条件接受被写宽", ("可协商", "异地", "target_accept_long_distance", "双城过渡")),
    ("城市范围或落地城市丢失", ("target_cities", "preferred_cities", "稳定留沪", "双城过渡")),
    ("硬要求被降级或丢失", ("must_have", "硬要求", "基础条件", "愿意沟通", "情绪稳定", "沟通顺畅")),
    ("关系目标强度漂移", ("relationship_goal", "结婚导向", "认真恋爱", "方向明确", "长期关系")),
    ("婚育语义映射不准", ("孩子", "accept_partner_children", "has_children", "再婚", "婚况")),
    ("公开摘要过度简化", ("public_", "公开层", "public_values", "public_personality", "公开资料")),
]

PRIVACY_RISK_RULES = [
    ("收入信息不宜公开", ("收入", "income", "万/年")),
    ("婚育和前任隐私不宜公开", ("孩子", "离婚", "前夫", "前任", "再婚")),
    ("单位学校等可识别信息不宜公开", ("学校", "医院", "公司", "单位", "接单平台")),
    ("家庭与健康压力不宜公开", ("父母", "催婚", "焦虑", "身体负担", "论文压力", "家庭")),
]

MATCHING_ISSUE_RULES = [
    ("数据池覆盖不足", ("数据池", "样本", "只扫描", "scanned", "exclude_record_ref", "为空", "池太小")),
    ("硬筛或反向条件过严", ("硬筛", "过死", "硬门槛", "反向条件", "婚况接受范围", "筛掉", "过滤")),
    ("无结果解释不透明", ("不透明", "颗粒度", "解释", "原因", "反馈", "太粗", "看不出")),
    ("软偏好权重不足", ("表达", "分寸", "自然度", "边界", "沟通", "火花", "吸引力")),
    ("推进落地判断不足", ("推进", "落地", "执行力", "长期意图", "说清")),
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a persona-eval audit summary JSON from reviewer feedback and optional audit artifacts.",
    )
    parser.add_argument(
        "--feedback-input",
        required=True,
        help="Reviewer feedback JSON file. Supports both legacy and nested formats.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the audit summary JSON.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run id. Defaults to the feedback input stem.",
    )
    parser.add_argument(
        "--memory-snapshots-input",
        default=None,
        help="Optional memory snapshots JSON file for profile ids and private boundaries.",
    )
    parser.add_argument(
        "--search-results-input",
        default=None,
        help="Optional persona search results JSON file to enrich no-match explanations.",
    )
    parser.add_argument(
        "--dataset-diagnostics-input",
        default=None,
        help="Optional JSON object file with extra dataset diagnostics to merge into the summary.",
    )
    return parser.parse_args()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_list_payload(data, label):
    if not isinstance(data, list):
        raise SystemExit(f"Expected a JSON list in {label}")
    return data


def ensure_object_payload(data, label):
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {label}")
    return data


def canonical_satisfaction(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return SATISFACTION_ALIASES.get(text.lower(), SATISFACTION_ALIASES.get(text, text))


def top_categories(items, rules, limit=5):
    counts = Counter()
    for raw_item in items:
        item = str(raw_item or "").strip()
        if not item:
            continue
        matched = False
        for label, keywords in rules:
            if any(keyword in item for keyword in keywords):
                counts[label] += 1
                matched = True
        if not matched:
            counts[item] += 1
    return [label for label, _count in counts.most_common(limit)]


def extract_prefixed_line(output, prefix):
    pattern = re.compile(rf"(?m)^{re.escape(prefix)}\s*(.+)$")
    match = pattern.search(output or "")
    return match.group(1).strip() if match else None


def parse_pool_scanned(output):
    match = re.search(r"pool_summary:\s*scanned=(\d+)", output or "")
    if not match:
        return None
    return int(match.group(1))


def index_snapshots(memory_snapshots):
    indexed = {}
    for item in memory_snapshots:
        persona_id = item.get("persona_id")
        if persona_id:
            indexed[persona_id] = item
    return indexed


def index_search_results(search_results):
    indexed = {}
    for item in search_results:
        persona_id = item.get("persona_id") or item.get("id")
        if persona_id:
            indexed[persona_id] = item
    return indexed


def build_dataset_diagnostics(search_results, provided=None):
    diagnostics = {}

    tiny_pools = []
    exclude_only_personas = []
    for item in search_results:
        persona_id = item.get("persona_id") or item.get("id")
        output = item.get("output", "")
        scanned = parse_pool_scanned(output)
        why_no_match = extract_prefixed_line(output, "why_no_match:")
        if scanned is not None and scanned <= 5:
            tiny_pools.append(
                {
                    "persona_id": persona_id,
                    "scanned": scanned,
                    "why_no_match": why_no_match,
                }
            )
        if why_no_match and "exclude_record_ref" in why_no_match:
            exclude_only_personas.append(persona_id)

    if tiny_pools:
        diagnostics["tiny_pool_personas"] = tiny_pools
    if exclude_only_personas:
        diagnostics["exclude_only_personas"] = exclude_only_personas

    if provided:
        diagnostics.update(provided)

    return diagnostics


def build_matching_verdict(entry, search_entry):
    matching_feedback = entry.get("matching_feedback") or {}
    candidate_reviews = matching_feedback.get("candidate_reviews") or entry.get("candidate_reviews") or []
    verdict_lines = []
    if candidate_reviews:
        ranked = sorted(
            candidate_reviews,
            key=lambda item: (item.get("rank", 9999), item.get("name", "")),
        )
        for review in ranked:
            name = review.get("name") or "未命名候选"
            verdict = review.get("verdict") or "待判断"
            verdict_lines.append(f"{name}：{verdict}")
        return verdict_lines

    verdict_lines.append("无候选")
    if search_entry:
        why_no_match = extract_prefixed_line(search_entry.get("output", ""), "why_no_match:")
        if why_no_match:
            verdict_lines.append(f"原因：{why_no_match}")
        relax_suggestions = extract_prefixed_line(search_entry.get("output", ""), "relax_suggestions:")
        if relax_suggestions:
            verdict_lines.append(f"建议：{relax_suggestions}")
    summary = matching_feedback.get("summary") or entry.get("summary")
    if summary and all(summary not in line for line in verdict_lines):
        verdict_lines.append(summary)
    return verdict_lines


def build_audit_summary(
    feedback,
    feedback_input,
    run_id=None,
    memory_snapshots=None,
    search_results=None,
    dataset_diagnostics=None,
):
    review_metrics = summarize_agent_feedback.summarize_feedback(feedback, feedback_input, label=run_id)
    memory_snapshot_index = index_snapshots(memory_snapshots or [])
    search_result_index = index_search_results(search_results or [])

    all_memory_drifts = []
    all_privacy_flags = []
    all_matching_issues = []
    matching_satisfaction_counts = Counter()
    personas = []

    for index, entry in enumerate(feedback, start=1):
        persona_id = summarize_agent_feedback.extract_persona_id(entry, index)
        memory_accuracy = summarize_agent_feedback.extract_memory_accuracy(entry)
        matching_feedback = summarize_agent_feedback.extract_matching_feedback(entry)
        search_entry = search_result_index.get(persona_id)
        snapshot = memory_snapshot_index.get(persona_id, {})

        memory_drift = summarize_agent_feedback.as_list(memory_accuracy.get("drift", entry.get("drift")))
        do_not_public = summarize_agent_feedback.as_list(
            memory_accuracy.get("do_not_public", entry.get("do_not_public"))
        )
        systemic_issues = summarize_agent_feedback.as_list(
            matching_feedback.get("systemic_issues", entry.get("systemic_issue"))
        )
        matching_satisfaction = canonical_satisfaction(
            matching_feedback.get("overall_satisfaction")
        )
        if matching_satisfaction:
            matching_satisfaction_counts[matching_satisfaction] += 1

        all_memory_drifts.extend(memory_drift)
        all_privacy_flags.extend(do_not_public)
        all_matching_issues.extend(systemic_issues)

        persona_summary = {
            "persona_id": persona_id,
            "display_name": entry.get("display_name") or snapshot.get("display_name"),
            "profile_id": snapshot.get("profile_id"),
            "overall_score": summarize_agent_feedback.as_optional_float(entry.get("overall_score")),
            "matching_satisfaction": matching_satisfaction,
            "memory_drift": memory_drift,
            "do_not_public": do_not_public,
            "matching_verdict": build_matching_verdict(entry, search_entry),
            "systemic_issues": systemic_issues,
        }
        private_boundaries = snapshot.get("private_boundaries")
        if private_boundaries:
            persona_summary["private_boundaries"] = private_boundaries
        personas.append(persona_summary)

    summary = {
        "run_id": run_id or feedback_input.stem,
        "generated_at": datetime.now().date().isoformat(),
        "scope": list(DEFAULT_SCOPE),
        "overall": {
            "agent_count": review_metrics["persona_count"],
            "overall_score_avg": review_metrics.get("overall_score_average", 0.0),
            "matching_satisfaction_distribution": dict(
                sorted(matching_satisfaction_counts.items())
            ),
            "common_memory_issues": top_categories(all_memory_drifts, MEMORY_ISSUE_RULES),
            "common_public_risks": top_categories(all_privacy_flags, PRIVACY_RISK_RULES),
            "common_matching_issues": top_categories(all_matching_issues, MATCHING_ISSUE_RULES),
        },
        "personas": personas,
    }

    merged_dataset_diagnostics = build_dataset_diagnostics(search_results or [], dataset_diagnostics)
    if merged_dataset_diagnostics:
        summary["dataset_diagnostics"] = merged_dataset_diagnostics

    return summary


def main():
    args = parse_args()
    feedback_input_path = Path(args.feedback_input).resolve()
    output_path = Path(args.output).resolve()
    memory_snapshots_path = (
        Path(args.memory_snapshots_input).resolve() if args.memory_snapshots_input else None
    )
    search_results_path = (
        Path(args.search_results_input).resolve() if args.search_results_input else None
    )
    dataset_diagnostics_path = (
        Path(args.dataset_diagnostics_input).resolve() if args.dataset_diagnostics_input else None
    )

    feedback = ensure_list_payload(load_json(feedback_input_path), feedback_input_path)
    memory_snapshots = (
        ensure_list_payload(load_json(memory_snapshots_path), memory_snapshots_path)
        if memory_snapshots_path
        else []
    )
    search_results = (
        ensure_list_payload(load_json(search_results_path), search_results_path)
        if search_results_path
        else []
    )
    dataset_diagnostics = (
        ensure_object_payload(load_json(dataset_diagnostics_path), dataset_diagnostics_path)
        if dataset_diagnostics_path
        else None
    )

    summary = build_audit_summary(
        feedback,
        feedback_input_path,
        run_id=args.run_id,
        memory_snapshots=memory_snapshots,
        search_results=search_results,
        dataset_diagnostics=dataset_diagnostics,
    )
    write_json(output_path, summary)


if __name__ == "__main__":
    main()
