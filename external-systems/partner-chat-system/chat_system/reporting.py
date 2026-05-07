"""Reporting helpers for roleplay results and chat thread exports."""

from __future__ import annotations

from typing import Any

from .assistant_llm import _looks_like_direct_send_message
from .storage import json_loads


def _coerce_roleplay_mutual_intent(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "communication_problem":
        return "communication_problem"
    return "normal"


def _coerce_roleplay_interaction_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "repair":
        return "repair"
    return "none"


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _avg(values: list[int | float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _format_rate(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _format_score(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if score.is_integer():
        return str(int(score))
    return f"{score:.2f}"


def _format_ms(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if ms.is_integer():
        return f"{int(ms)} ms"
    return f"{ms:.2f} ms"


def _accuracy(
    turn_records: list[dict[str, Any]],
    *,
    gold_key: str,
    pred_key: str,
) -> dict[str, Any]:
    comparable = [
        record
        for record in turn_records
        if record.get(gold_key) not in (None, "") and record.get(pred_key) not in (None, "")
    ]
    matched = [
        record
        for record in comparable
        if str(record.get(gold_key) or "") == str(record.get(pred_key) or "")
    ]
    return {
        "comparable_turns": len(comparable),
        "matched_turns": len(matched),
        "rate": _rate(len(matched), len(comparable)),
    }


def _mode_distribution(turn_records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(turn_records)
    counts = {
        "normal": 0,
        "repair": 0,
        "other": 0,
    }
    for record in turn_records:
        mode = _coerce_roleplay_interaction_mode(
            record.get("interaction_mode") or record.get("interaction_mode_pred") or "none"
        )
        if mode in counts:
            counts[mode] += 1
        else:
            counts["other"] += 1
    return {
        "total_turns": total,
        "counts": counts,
        "rates": {key: _rate(value, total) for key, value in counts.items()},
        "non_normal_turns": total - counts["normal"],
    }


def _assistant_interventions(turn_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in turn_records if bool(record.get("assistant_invoked"))]


def _direct_send_violation_summary(turn_records: list[dict[str, Any]]) -> dict[str, Any]:
    interventions = _assistant_interventions(turn_records)
    violating_turns: list[int] = []
    for record in interventions:
        guidance = record.get("assistant_guidance") or {}
        suggestions = list(guidance.get("advice") or []) + list(guidance.get("reply_suggestions") or [])
        if any(_looks_like_direct_send_message(item) for item in suggestions):
            violating_turns.append(int(record.get("turn") or 0))
    return {
        "turns": violating_turns,
        "count": len(violating_turns),
        "rate": _rate(len(violating_turns), len(interventions)),
        "checked_intervention_turns": len(interventions),
    }


def _gold_need_rescue_for_view(record: dict[str, Any], *, view: str) -> bool:
    if view == "visible_text":
        return bool(((record.get("visible_text_gold_decision") or {}).get("need_rescue")))
    if view == "manifested_stress_beat":
        return bool(((record.get("manifested_stress_gold_decision") or {}).get("need_rescue")))
    return bool(record.get("need_rescue_gold"))


def _gold_interaction_mode_for_view(record: dict[str, Any], *, view: str) -> str:
    if view == "visible_text":
        return _coerce_roleplay_interaction_mode(
            ((record.get("visible_text_gold_decision") or {}).get("interaction_mode")) or "none"
        )
    if view == "manifested_stress_beat":
        return _coerce_roleplay_interaction_mode(
            ((record.get("manifested_stress_gold_decision") or {}).get("expected_interaction_mode"))
            or "none"
        )
    return _coerce_roleplay_interaction_mode(record.get("interaction_mode_gold") or "none")


def _gold_mutual_intent_for_view(record: dict[str, Any], *, view: str) -> str:
    if view == "visible_text":
        return _coerce_roleplay_mutual_intent(
            ((record.get("visible_text_gold_decision") or {}).get("mutual_intent_assessment")) or "normal"
        )
    if view == "manifested_stress_beat":
        return _coerce_roleplay_mutual_intent(
            ((record.get("manifested_stress_gold_decision") or {}).get("expected_mutual_intent_assessment"))
            or "normal"
        )
    return _coerce_roleplay_mutual_intent(record.get("mutual_intent_assessment_gold") or "normal")


def _recognition_view_summary(turn_records: list[dict[str, Any]], *, view: str) -> dict[str, Any]:
    comparable_turns = list(turn_records)
    need_matched = [
        record
        for record in comparable_turns
        if _gold_need_rescue_for_view(record, view=view) == bool(record.get("need_rescue_pred"))
    ]
    mode_matched = [
        record
        for record in comparable_turns
        if _gold_interaction_mode_for_view(record, view=view) == str(record.get("interaction_mode_pred") or "none")
    ]
    intent_matched = [
        record
        for record in comparable_turns
        if _gold_mutual_intent_for_view(record, view=view)
        == str(record.get("mutual_intent_assessment_pred") or "normal")
    ]
    repair_turns = [
        record
        for record in comparable_turns
        if _gold_interaction_mode_for_view(record, view=view) == "repair"
    ]
    repair_missed_none_turns = [
        record for record in repair_turns if _coerce_roleplay_interaction_mode(record.get("interaction_mode_pred")) == "none"
    ]
    repair_hit_turns = [
        record for record in repair_turns if _coerce_roleplay_interaction_mode(record.get("interaction_mode_pred")) == "repair"
    ]
    return {
        "need_rescue_accuracy": {
            "comparable_turns": len(comparable_turns),
            "matched_turns": len(need_matched),
            "rate": _rate(len(need_matched), len(comparable_turns)),
        },
        "interaction_mode_accuracy": {
            "comparable_turns": len(comparable_turns),
            "matched_turns": len(mode_matched),
            "rate": _rate(len(mode_matched), len(comparable_turns)),
        },
        "mutual_intent_accuracy": {
            "comparable_turns": len(comparable_turns),
            "matched_turns": len(intent_matched),
            "rate": _rate(len(intent_matched), len(comparable_turns)),
        },
        "repair_turns": len(repair_turns),
        "repair_hit_turns": len(repair_hit_turns),
        "repair_recall": _rate(len(repair_hit_turns), len(repair_turns)),
        "repair_missed_none_turns": len(repair_missed_none_turns),
        "repair_miss_rate": _rate(len(repair_missed_none_turns), len(repair_turns)),
    }


def build_roleplay_report_summary(result: dict[str, Any]) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    turn_records = [
        dict(record)
        for record in list(payload.get("turn_evaluations") or [])
        if isinstance(record, dict)
    ]
    metrics = dict(payload.get("assistant_metrics") or {})
    naturalness_metrics = dict(payload.get("naturalness_metrics") or {})
    llm_stats = {
        str(kind): dict(values)
        for kind, values in dict(payload.get("llm_stats") or {}).items()
        if isinstance(values, dict)
    }
    evaluation = {
        str(user_id): dict(values)
        for user_id, values in dict(payload.get("evaluation") or {}).items()
        if isinstance(values, dict)
    }
    assistant_scores = [
        int(values.get("assistant_score") or 0)
        for values in evaluation.values()
        if values.get("assistant_score") is not None
    ]
    conversation_scores = [
        int(values.get("conversation_score") or 0)
        for values in evaluation.values()
        if values.get("conversation_score") is not None
    ]
    interventions = _assistant_interventions(turn_records)
    compliant_turns = [
        record
        for record in interventions
        if str(record.get("assistant_mode_compliance") or "") == "compliant"
    ]
    direct_send = _direct_send_violation_summary(turn_records)
    recoverable = int(metrics.get("recoverable_intervention_turns") or 0)
    improved = int(metrics.get("improved_recovery_turns") or 0)
    slightly_improved = int(metrics.get("slightly_improved_recovery_turns") or 0)
    overpush_risk_turns = int(metrics.get("overpush_risk_turns") or 0)
    distribution = _mode_distribution(turn_records)
    visible_text_view = _recognition_view_summary(turn_records, view="visible_text")
    stress_beat_view = _recognition_view_summary(turn_records, view="stress_beat")
    manifested_stress_beat_view = _recognition_view_summary(
        turn_records,
        view="manifested_stress_beat",
    )
    recognition = {
        "need_rescue_accuracy": _accuracy(
            turn_records,
            gold_key="need_rescue_gold",
            pred_key="need_rescue_pred",
        ),
        "interaction_mode_accuracy": _accuracy(
            turn_records,
            gold_key="interaction_mode_gold",
            pred_key="interaction_mode_pred",
        ),
        "mutual_intent_accuracy": _accuracy(
            turn_records,
            gold_key="mutual_intent_assessment_gold",
            pred_key="mutual_intent_assessment_pred",
        ),
        "rescue_precision_proxy": metrics.get("precision_proxy"),
        "rescue_recall_proxy": metrics.get("recall_proxy"),
        "repair_recall": metrics.get(
            "repair_recall",
            manifested_stress_beat_view.get("repair_recall"),
        ),
        "repair_miss_rate": metrics.get(
            "repair_miss_rate",
            manifested_stress_beat_view.get("repair_miss_rate"),
        ),
        "visible_text_view": visible_text_view,
        "stress_beat_view": stress_beat_view,
        "manifested_stress_beat_view": manifested_stress_beat_view,
    }
    advice_quality = {
        "assistant_score_avg_1to5": _avg(assistant_scores),
        "conversation_score_avg_1to5": _avg(conversation_scores),
        "assistant_mode_compliance_rate": _rate(len(compliant_turns), len(interventions)),
        "direct_send_violation_rate": direct_send["rate"],
        "direct_send_violation_turns": direct_send["turns"],
        "avoid_violation_rate": _rate(
            int(metrics.get("avoid_violation_turns") or 0),
            len(interventions),
        ),
        "naturalness_average_score_1to5": naturalness_metrics.get("average_score"),
    }
    user_adoption = {
        "follow_rate": metrics.get("follow_rate"),
        "partial_follow_rate": metrics.get("partial_follow_rate"),
        "strong_follow_rate": metrics.get("strong_follow_rate"),
        "followed_intervention_turns": int(metrics.get("followed_intervention_turns") or 0),
        "intervention_turns": len(interventions),
    }
    local_recovery = {
        "local_recovery_rate": _rate(improved + slightly_improved, recoverable),
        "improved_recovery_rate": metrics.get("improved_recovery_rate"),
        "overpush_risk_rate": _rate(overpush_risk_turns, len(interventions)),
    }
    latency = {
        "assistant_invoke_avg_ms": metrics.get("assistant_invoke_avg_ms"),
        "assistant_invoke_max_ms": metrics.get("assistant_invoke_max_ms"),
        "assistant_invoke_timeout_rate": metrics.get("assistant_invoke_timeout_rate"),
        "assistant_guidance_fallback_rate": metrics.get("assistant_guidance_fallback_rate"),
        "fallback_message_rate": metrics.get("fallback_message_rate"),
        "message_generation_timeout_rate": metrics.get("message_generation_timeout_rate"),
        "self_evaluation_fallback_count": metrics.get("self_evaluation_fallback_count"),
        "self_evaluation_timeout_count": metrics.get("self_evaluation_timeout_count"),
        "llm_by_call_kind": llm_stats,
    }
    primary_evaluation = {
        "assistant_mode_compliance_rate": advice_quality["assistant_mode_compliance_rate"],
        "direct_send_violation_rate": advice_quality["direct_send_violation_rate"],
        "avoid_violation_rate": advice_quality["avoid_violation_rate"],
        "visible_text_interaction_mode_accuracy": (
            (visible_text_view.get("interaction_mode_accuracy") or {}).get("rate")
        ),
        "manifested_stress_interaction_mode_accuracy": (
            (manifested_stress_beat_view.get("interaction_mode_accuracy") or {}).get("rate")
        ),
        "repair_recall": recognition["repair_recall"],
        "repair_miss_rate": recognition["repair_miss_rate"],
        "assistant_invoke_timeout_rate": latency["assistant_invoke_timeout_rate"],
        "assistant_guidance_fallback_rate": latency["assistant_guidance_fallback_rate"],
        "fallback_message_rate": latency["fallback_message_rate"],
        "message_generation_timeout_rate": latency["message_generation_timeout_rate"],
        "stress_beat_manifestation_rate": metrics.get("stress_beat_manifestation_rate"),
    }
    reference_only = {
        "user_adoption": user_adoption,
        "local_recovery": local_recovery,
        "self_evaluation": {
            "assistant_score_avg_1to5": advice_quality["assistant_score_avg_1to5"],
            "conversation_score_avg_1to5": advice_quality["conversation_score_avg_1to5"],
        },
        "mode_alignment": {
            "simulated_reply_mode_prompted_turns": metrics.get("simulated_reply_mode_prompted_turns"),
            "simulated_reply_mode_alignment_rate": metrics.get("simulated_reply_mode_alignment_rate"),
            "simulated_reply_mode_strong_alignment_rate": metrics.get(
                "simulated_reply_mode_strong_alignment_rate"
            ),
        },
    }
    topline = {
        "assistant_mode_compliance_rate": primary_evaluation["assistant_mode_compliance_rate"],
        "interaction_mode_accuracy": primary_evaluation["manifested_stress_interaction_mode_accuracy"],
        "repair_recall": recognition["repair_recall"],
        "repair_miss_rate": recognition["repair_miss_rate"],
        "assistant_invoke_timeout_rate": latency["assistant_invoke_timeout_rate"],
        "assistant_guidance_fallback_rate": latency["assistant_guidance_fallback_rate"],
        "fallback_message_rate": latency["fallback_message_rate"],
    }
    return {
        "schema_version": 1,
        "case_id": payload.get("case_id"),
        "thread_id": payload.get("thread_id"),
        "rounds": int(payload.get("rounds") or len(turn_records)),
        "primary_evaluation": primary_evaluation,
        "recognition_accuracy": recognition,
        "advice_quality": advice_quality,
        "user_adoption": user_adoption,
        "local_recovery": local_recovery,
        "reference_only": reference_only,
        "latency": latency,
        "mode_distribution": distribution,
        "topline": topline,
    }


def render_roleplay_report_markdown(
    summary: dict[str, Any],
    *,
    include_title: bool = True,
) -> str:
    payload = summary if isinstance(summary, dict) else {}
    primary = dict(payload.get("primary_evaluation") or {})
    recognition = dict(payload.get("recognition_accuracy") or {})
    advice_quality = dict(payload.get("advice_quality") or {})
    reference_only = dict(payload.get("reference_only") or {})
    user_adoption = dict(reference_only.get("user_adoption") or payload.get("user_adoption") or {})
    local_recovery = dict(reference_only.get("local_recovery") or payload.get("local_recovery") or {})
    self_evaluation = dict(reference_only.get("self_evaluation") or {})
    mode_alignment = dict(reference_only.get("mode_alignment") or {})
    latency = dict(payload.get("latency") or {})
    visible_text_view = dict(recognition.get("visible_text_view") or {})
    stress_beat_view = dict(recognition.get("stress_beat_view") or {})
    manifested_stress_beat_view = dict(recognition.get("manifested_stress_beat_view") or {})
    distribution = dict(payload.get("mode_distribution") or {})
    counts = dict(distribution.get("counts") or {})
    rates = dict(distribution.get("rates") or {})
    llm_by_call = dict(latency.get("llm_by_call_kind") or {})

    lines = []
    if include_title:
        lines.extend(
            [
                "# Roleplay Report",
                "",
            ]
        )
    lines.extend(
        [
            f"- case_id: {payload.get('case_id') or ''}",
            f"- thread_id: {payload.get('thread_id') or ''}",
            f"- rounds: {payload.get('rounds') or 0}",
            "",
            "## 主要结论（提示是否合理）",
            "",
            "- 以下指标优先看“提示本身是否合理”，不把角色扮演有没有照做当主结论。",
            f"- assistant mode compliance rate: {_format_rate(primary.get('assistant_mode_compliance_rate'))}",
            f"- direct-send violation rate: {_format_rate(primary.get('direct_send_violation_rate'))}",
            f"- avoid violation rate: {_format_rate(primary.get('avoid_violation_rate'))}",
            f"- visible-text interaction mode accuracy: {_format_rate(primary.get('visible_text_interaction_mode_accuracy'))}",
            f"- manifested-stress interaction mode accuracy: {_format_rate(primary.get('manifested_stress_interaction_mode_accuracy'))}",
            f"- repair recall: {_format_rate(primary.get('repair_recall'))}",
            f"- repair miss rate: {_format_rate(primary.get('repair_miss_rate'))}",
            f"- stress-beat manifestation rate: {_format_rate(primary.get('stress_beat_manifestation_rate'))}",
            "",
            "## 三口径视图",
            "",
            (
                "- visible-text rescue need accuracy: "
                f"{_format_rate(((visible_text_view.get('need_rescue_accuracy') or {}).get('rate')))} "
                f"({((visible_text_view.get('need_rescue_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((visible_text_view.get('need_rescue_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- visible-text interaction mode accuracy: "
                f"{_format_rate(((visible_text_view.get('interaction_mode_accuracy') or {}).get('rate')))} "
                f"({((visible_text_view.get('interaction_mode_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((visible_text_view.get('interaction_mode_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- visible-text mutual intent accuracy: "
                f"{_format_rate(((visible_text_view.get('mutual_intent_accuracy') or {}).get('rate')))} "
                f"({((visible_text_view.get('mutual_intent_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((visible_text_view.get('mutual_intent_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            f"- visible-text repair turns: {int(visible_text_view.get('repair_turns') or 0)}",
            f"- visible-text repair recall: {_format_rate(visible_text_view.get('repair_recall'))}",
            f"- visible-text repair miss rate: {_format_rate(visible_text_view.get('repair_miss_rate'))}",
            (
                "- stress-beat rescue need accuracy: "
                f"{_format_rate(((stress_beat_view.get('need_rescue_accuracy') or {}).get('rate')))} "
                f"({((stress_beat_view.get('need_rescue_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((stress_beat_view.get('need_rescue_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- stress-beat interaction mode accuracy: "
                f"{_format_rate(((stress_beat_view.get('interaction_mode_accuracy') or {}).get('rate')))} "
                f"({((stress_beat_view.get('interaction_mode_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((stress_beat_view.get('interaction_mode_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- stress-beat mutual intent accuracy: "
                f"{_format_rate(((stress_beat_view.get('mutual_intent_accuracy') or {}).get('rate')))} "
                f"({((stress_beat_view.get('mutual_intent_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((stress_beat_view.get('mutual_intent_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            f"- stress-beat repair turns: {int(stress_beat_view.get('repair_turns') or 0)}",
            f"- stress-beat repair recall: {_format_rate(stress_beat_view.get('repair_recall'))}",
            f"- stress-beat repair miss rate: {_format_rate(stress_beat_view.get('repair_miss_rate'))}",
            "",
            (
                "- manifested-stress rescue need accuracy: "
                f"{_format_rate(((manifested_stress_beat_view.get('need_rescue_accuracy') or {}).get('rate')))} "
                f"({((manifested_stress_beat_view.get('need_rescue_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((manifested_stress_beat_view.get('need_rescue_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- manifested-stress interaction mode accuracy: "
                f"{_format_rate(((manifested_stress_beat_view.get('interaction_mode_accuracy') or {}).get('rate')))} "
                f"({((manifested_stress_beat_view.get('interaction_mode_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((manifested_stress_beat_view.get('interaction_mode_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            (
                "- manifested-stress mutual intent accuracy: "
                f"{_format_rate(((manifested_stress_beat_view.get('mutual_intent_accuracy') or {}).get('rate')))} "
                f"({((manifested_stress_beat_view.get('mutual_intent_accuracy') or {}).get('matched_turns') or 0)}/"
                f"{((manifested_stress_beat_view.get('mutual_intent_accuracy') or {}).get('comparable_turns') or 0)})"
            ),
            f"- manifested-stress repair turns: {int(manifested_stress_beat_view.get('repair_turns') or 0)}",
            f"- manifested-stress repair recall: {_format_rate(manifested_stress_beat_view.get('repair_recall'))}",
            f"- manifested-stress repair miss rate: {_format_rate(manifested_stress_beat_view.get('repair_miss_rate'))}",
            "",
            "## 稳定性",
            "",
            f"- assistant invoke avg: {_format_ms(latency.get('assistant_invoke_avg_ms'))}",
            f"- assistant invoke max: {_format_ms(latency.get('assistant_invoke_max_ms'))}",
            f"- assistant invoke timeout rate: {_format_rate(latency.get('assistant_invoke_timeout_rate'))}",
            f"- assistant guidance fallback rate: {_format_rate(latency.get('assistant_guidance_fallback_rate'))}",
            f"- fallback message rate: {_format_rate(latency.get('fallback_message_rate'))}",
            f"- message generation timeout rate: {_format_rate(latency.get('message_generation_timeout_rate'))}",
            f"- self-evaluation fallback count: {int(latency.get('self_evaluation_fallback_count') or 0)}",
            f"- self-evaluation timeout count: {int(latency.get('self_evaluation_timeout_count') or 0)}",
        ]
    )
    if llm_by_call:
        for kind, stats in sorted(llm_by_call.items()):
            lines.append(
                f"- llm {kind}: started={int(stats.get('calls_started') or 0)}, "
                f"ok={int(stats.get('successes') or stats.get('calls') or 0)}, "
                f"fail={int(stats.get('failures') or 0)}, timeout={int(stats.get('timeouts') or 0)}, "
                f"avg_ok={_format_ms(stats.get('avg_success_ms') or stats.get('avg_ms'))}, "
                f"avg_all={_format_ms(stats.get('avg_all_ms'))}, max={_format_ms(stats.get('max_ms'))}"
            )
    else:
        lines.append("- llm calls: n/a")
    lines.extend(
        [
            "",
            "## 参考结果（受角色扮演影响）",
            "",
            "- 以下结果容易被“角色有没有照提示做、角色演得像不像真人”影响，只作参考。",
            f"- assistant score avg: {_format_score(self_evaluation.get('assistant_score_avg_1to5') or advice_quality.get('assistant_score_avg_1to5'))}/5",
            f"- conversation score avg: {_format_score(self_evaluation.get('conversation_score_avg_1to5') or advice_quality.get('conversation_score_avg_1to5'))}/5",
            f"- naturalness avg: {_format_score(advice_quality.get('naturalness_average_score_1to5'))}/5",
            f"- follow rate: {_format_rate(user_adoption.get('follow_rate'))}",
            f"- strong follow rate: {_format_rate(user_adoption.get('strong_follow_rate'))}",
            f"- local recovery rate: {_format_rate(local_recovery.get('local_recovery_rate'))}",
            f"- improved recovery rate: {_format_rate(local_recovery.get('improved_recovery_rate'))}",
            f"- overpush risk rate: {_format_rate(local_recovery.get('overpush_risk_rate'))}",
            f"- simulated mode alignment rate: {_format_rate(mode_alignment.get('simulated_reply_mode_alignment_rate'))}",
            "",
            "## 模式分布",
            "",
            (
                f"- normal: {counts.get('normal') or 0} "
                f"({_format_rate(rates.get('normal'))})"
            ),
            (
                f"- repair: {counts.get('repair') or 0} "
                f"({_format_rate(rates.get('repair'))})"
            ),
            (
                f"- other: {counts.get('other') or 0} "
                f"({_format_rate(rates.get('other'))})"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _normalize_message_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = json_loads(row.get("metadata_json"), {})
    out = dict(row)
    out["metadata"] = metadata if isinstance(metadata, dict) else {}
    return out


def _assistant_message_title(row: dict[str, Any]) -> str:
    trace = dict(((row.get("metadata") or {}).get("assistant_trace")) or {})
    guidance = dict(trace.get("guidance") or {})
    hint_event = dict(trace.get("hint_event") or {})
    meta = dict(row.get("metadata") or {})
    if str(meta.get("owner_only_kind") or "") == "assistant_hint_entry":
        parts = ["助手建议入口"]
    else:
        parts = ["助手建议"]
    mode = str(guidance.get("interaction_mode") or "")
    if mode:
        parts.append(f"mode={mode}")
    trigger = str(hint_event.get("trigger_type") or "")
    if trigger:
        parts.append(f"trigger={trigger}")
    return " | ".join(parts)


def _message_block(row: dict[str, Any], *, title: str | None = None) -> list[str]:
    mid = row.get("message_id")
    who = row.get("author_id")
    vis = row.get("visibility")
    src = row.get("source")
    to = row.get("message_recipient_id")
    ts = row.get("created_at")
    label = title or str(who or "")
    head = f"### #{mid} | {label} | {vis} | {src} | →{to} | {ts}"
    body = str(row.get("body") or "").strip()
    return [head, "", body or "（空）", ""]


def build_thread_export_markdown(
    rows: list[dict[str, Any]],
    *,
    thread_id: str,
    roleplay_result: dict[str, Any] | None = None,
) -> str:
    normalized = [_normalize_message_row(dict(row)) for row in list(rows or [])]
    dyadic = [row for row in normalized if row.get("visibility") == "dyadic"]
    assistant_owner_only = [
        row
        for row in normalized
        if row.get("visibility") == "owner_only" and row.get("author_id") == "assistant"
    ]
    user_owner_only = [
        row
        for row in normalized
        if row.get("visibility") == "owner_only" and row.get("author_id") != "assistant"
    ]
    system_rows = [row for row in normalized if row.get("visibility") == "system"]

    lines: list[str] = [
        f"# 聊天导出 `thread_id={thread_id}`",
        "",
        (
            f"共 {len(normalized)} 条消息：双方可见 {len(dyadic)} 条，"
            f"助手建议 {len(assistant_owner_only)} 条，用户私有记录 {len(user_owner_only)} 条。"
        ),
        "",
        "## 主对话正文",
        "",
    ]
    if not dyadic:
        lines.append("（无）")
        lines.append("")
    else:
        for row in dyadic:
            lines.extend(_message_block(row))

    lines.extend(["## 助手建议", ""])
    if not assistant_owner_only:
        lines.append("（无）")
        lines.append("")
    else:
        for row in assistant_owner_only:
            lines.extend(_message_block(row, title=_assistant_message_title(row)))

    lines.extend(["## 用户私有记录", ""])
    if not user_owner_only:
        lines.append("（无）")
        lines.append("")
    else:
        for row in user_owner_only:
            lines.extend(_message_block(row, title="用户问助手/仅自己可见"))

    if system_rows:
        lines.extend(["## 系统消息", ""])
        for row in system_rows:
            lines.extend(_message_block(row, title="系统消息"))

    if roleplay_result:
        summary = dict(roleplay_result.get("report_summary") or {})
        if not summary:
            summary = build_roleplay_report_summary(roleplay_result)
        lines.extend(["## 评测摘要", "", render_roleplay_report_markdown(summary, include_title=False), ""])
        evaluation = dict(roleplay_result.get("evaluation") or {})
        if evaluation:
            lines.extend(["## 评测自评", ""])
            for user_id, item in evaluation.items():
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- {user_id}: 对话分={item.get('conversation_score')}, 助手分={item.get('assistant_score')}, "
                    f"用了助手={item.get('used_assistant')}"
                )
            lines.append("")

    return "\n".join(lines)


__all__ = [
    "build_roleplay_report_summary",
    "build_thread_export_markdown",
    "render_roleplay_report_markdown",
]
