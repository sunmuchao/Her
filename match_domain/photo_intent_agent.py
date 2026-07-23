"""Photo preference intent parsing and explanation services."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .appearance_features import build_match_explanation_payload
from .photo_discovery_search import (
    search_hybrid_photo_candidates,
    search_similar_face_candidates,
    search_style_candidates,
)

_logger = logging.getLogger(__name__)
_FACE_MARKERS = ("像这张脸", "按脸", "长得像", "脸像", "五官像", "同款脸")
_STYLE_MARKERS = ("这种感觉", "这种风格", "这种氛围", "感觉像", "风格像", "气质像")
_REFINEMENT_MARKERS = ("不要太", "一点", "换成", "改成", "继续找", "还是", "长发", "短发", "温柔", "成熟")
_CELEBRITY_PATTERNS = (
    re.compile(r"像(?P<name>[\u4e00-\u9fffA-Za-z·]{2,12})的?(?:女生|男生|人|脸|明星)?"),
    re.compile(r"某个参考人物[:：]?(?P<name>[\u4e00-\u9fffA-Za-z·]{2,12})"),
    re.compile(r"参考(?:明星|人物)[:：]?(?P<name>[\u4e00-\u9fffA-Za-z·]{2,12})"),
)
_INLINE_IMAGE_REFERENCE_PATTERN = re.compile(
    r"^(?:这张|那张|图中(?:的)?|图里的?|图片中(?:的)?|图片里的?|照片中(?:的)?|照片里的?|上传的)"
    r"(?:那个?|这位|那位)?"
    r"(?:女生|男生|女人|男人|人|脸)$"
)


@dataclass(frozen=True)
class PhotoPreferenceIntent:
    intent_type: str
    mode: str
    query_text: str
    attribute_filters: dict[str, Any]
    hard_filters: dict[str, Any] = field(default_factory=dict)
    celebrity_name: str | None = None
    raw_text: str = ""
    confidence: float = 0.0
    routing_reasons: list[str] = field(default_factory=list)
    image_understanding: dict[str, Any] = field(default_factory=dict)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_celebrity_name(text: str, client_context: dict[str, Any] | None) -> str | None:
    hint = dict(dict(client_context or {}).get("intent_hint") or {})
    explicit = _normalize_text(hint.get("celebrity_name"))
    if explicit:
        return explicit
    for pattern in _CELEBRITY_PATTERNS:
        match = pattern.search(text)
        if match:
            name = _normalize_text(match.group("name"))
            if (
                name
                and name not in {"这张", "刚才", "上面"}
                and not name.startswith(("这张", "那张", "刚才", "上面", "上述", "这种", "这个"))
                and not _looks_like_inline_image_reference(name)
            ):
                return name
    return None


def _looks_like_inline_image_reference(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return False
    collapsed = re.sub(r"\s+", "", normalized)
    return bool(_INLINE_IMAGE_REFERENCE_PATTERN.fullmatch(collapsed))


def _default_query_text(search_mode: str, celebrity_name: str | None = None) -> str:
    if search_mode == "face":
        return "像这张脸"
    if search_mode == "style":
        return "这种感觉"
    if search_mode == "celebrity":
        return celebrity_name or "参考人物"
    return "帮我看看这张图适合找什么人"


def build_visual_search_plan(
    *,
    text: str | None,
    image_source: str | None,
    visual_context: dict[str, Any] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_text = _normalize_text(text)
    visual_context = dict(visual_context or {})
    reference = dict(visual_context.get("active_reference_image") or {})
    has_current_image = bool(_normalize_text(image_source))
    has_memory_reference = bool(_normalize_text(reference.get("source")))
    has_reference = has_current_image or has_memory_reference
    reference_source = "current_upload" if has_current_image else "session_memory" if has_memory_reference else "none"
    hint = dict(dict(client_context or {}).get("intent_hint") or {})
    explicit_mode = _normalize_text(hint.get("mode")).lower()
    celebrity_name = _extract_celebrity_name(normalized_text, client_context)
    routing_reasons: list[str] = []

    preference_kind: str | None = None
    if celebrity_name or explicit_mode == "celebrity":
        preference_kind = "celebrity"
        routing_reasons.append("celebrity_reference")
    elif explicit_mode in {"face", "style"}:
        preference_kind = explicit_mode
        routing_reasons.append("explicit_mode_hint")
    elif any(marker in normalized_text for marker in _FACE_MARKERS):
        preference_kind = "face"
        routing_reasons.append("face_marker_detected")
    elif any(marker in normalized_text for marker in _STYLE_MARKERS):
        preference_kind = "style"
        routing_reasons.append("style_marker_detected")
    elif has_reference:
        preference_kind = "hybrid"
        routing_reasons.append("default_hybrid_for_reference_image")

    should_ask = False
    clarifying_question: str | None = None
    if preference_kind == "celebrity" and not celebrity_name:
        should_ask = True
        clarifying_question = "你直接告诉我想参考谁，我就按她的感觉继续帮你找。"
        routing_reasons.append("missing_celebrity_name")
    elif not has_reference and preference_kind != "celebrity":
        should_ask = True
        clarifying_question = "你把参考图再发一次，或者直接说想按脸找、按感觉找，还是按某个参考人物找。"
        routing_reasons.append("missing_reference_image")

    is_refinement = bool(normalized_text and any(marker in normalized_text for marker in _REFINEMENT_MARKERS))
    turn_type = "visual_refinement" if is_refinement and has_reference else "visual_search"
    if should_ask:
        turn_type = "visual_clarification"

    query_text = normalized_text or _default_query_text(preference_kind or "hybrid", celebrity_name)
    assistant_summary = ""
    follow_up_suggestions: list[str] = []
    if should_ask:
        assistant_summary = clarifying_question or "我先确认一下你的意思，再继续帮你找。"
        follow_up_suggestions = ["按脸找", "按感觉找", "给个参考人物"]
    elif turn_type == "visual_refinement":
        assistant_summary = "我接着上一张图的方向继续细化这一轮。"
        follow_up_suggestions = ["换成上海", "温柔一点", "长发一点"]
    else:
        summary_map = {
            "face": "我会先按脸更接近这张图的方向帮你筛。",
            "style": "我会先按这张图的整体感觉和气质帮你筛。",
            "hybrid": "我会先把脸和整体感觉一起看，综合帮你筛一轮。",
            "celebrity": f"我会先按 {celebrity_name or '这个参考人物'} 的整体感觉帮你筛。",
        }
        assistant_summary = summary_map.get(preference_kind or "hybrid", "我先按这张图综合帮你筛一轮。")
        follow_up_suggestions = (
            ["按脸更近一点", "换成上海", "温柔一点"]
            if preference_kind in {"face", "hybrid"}
            else ["更像这种感觉", "长发一点", "换成上海"]
        )

    return {
        "turn_type": turn_type,
        "should_search_now": not should_ask,
        "should_ask_clarifying_question": should_ask,
        "clarifying_question": clarifying_question,
        "assistant_summary": assistant_summary,
        "follow_up_suggestions": follow_up_suggestions[:3],
        "resolved_visual_plan": {
            "preference_kind": preference_kind,
            "intent_type": {
                "face": "face_similarity_search",
                "style": "style_similarity_search",
                "hybrid": "hybrid_photo_search",
                "celebrity": "celebrity_face_search",
            }.get(preference_kind),
            "query_text": query_text,
            "celebrity_name": celebrity_name,
            "reference_source": reference_source,
            "reuse_reference_image": (not has_current_image and has_memory_reference),
            "attribute_filters": dict(dict(client_context or {}).get("attribute_filters") or {}),
            "hard_filters": dict(dict(client_context or {}).get("hard_filters") or {}),
            "search_strategy": {
                "face": "reference_face_similarity",
                "style": "appearance_vector_plus_tags",
                "hybrid": "face_plus_style_hybrid",
                "celebrity": "celebrity_reference_face",
            }.get(preference_kind),
            "routing_reasons": routing_reasons,
        } if preference_kind else None,
    }


def visual_plan_to_photo_intent(plan: Mapping[str, Any]) -> PhotoPreferenceIntent:
    resolved = dict(plan.get("resolved_visual_plan") or {})
    mode = _normalize_text(resolved.get("preference_kind") or resolved.get("search_mode")) or "hybrid"
    celebrity_name = _normalize_text(resolved.get("celebrity_name")) or None
    query_text = _normalize_text(resolved.get("query_text")) or _default_query_text(mode, celebrity_name)
    return PhotoPreferenceIntent(
        intent_type=_normalize_text(resolved.get("intent_type")) or "hybrid_photo_search",
        mode=mode,
        query_text=query_text,
        attribute_filters=dict(resolved.get("attribute_filters") or {}),
        hard_filters=dict(resolved.get("hard_filters") or {}),
        celebrity_name=celebrity_name,
        raw_text=query_text,
        confidence=0.8,
        routing_reasons=[str(item).strip() for item in list(resolved.get("routing_reasons") or []) if str(item).strip()],
        image_understanding={
            "reference_source": _normalize_text(resolved.get("reference_source")) or "none",
            "reuse_reference_image": bool(resolved.get("reuse_reference_image")),
            "search_strategy": _normalize_text(resolved.get("search_strategy")) or None,
        },
    )


def build_visual_search_result_summary(
    *,
    plan: Mapping[str, Any],
    result_count: int,
) -> str:
    resolved = dict(plan.get("resolved_visual_plan") or {})
    mode = _normalize_text(resolved.get("preference_kind") or resolved.get("search_mode")) or "hybrid"
    suggestions = [str(item).strip() for item in list(plan.get("follow_up_suggestions") or []) if str(item).strip()][:2]
    if result_count <= 0:
        base = "这轮我还没筛到特别贴的。"
    elif mode == "face":
        base = f"我先按脸更接近这张图的方向筛了一轮，挑到 {result_count} 个比较贴近的。"
    elif mode == "style":
        base = f"我先按这张图的感觉和气质筛了一轮，挑到 {result_count} 个比较贴近的。"
    elif mode == "celebrity":
        celebrity_name = _normalize_text(resolved.get("celebrity_name")) or "这个参考人物"
        base = f"我先按 {celebrity_name} 的整体感觉筛了一轮，挑到 {result_count} 个比较贴近的。"
    else:
        base = f"我先把脸和整体感觉一起看了一轮，挑到 {result_count} 个比较贴近的。"
    if suggestions:
        return f"{base} 你接下来可以继续说“{'”或“'.join(suggestions)}”。"
    return base






def translate_intent_to_search_plan(intent: PhotoPreferenceIntent) -> dict[str, Any]:
    payload = {
        "intent_type": intent.intent_type,
        "mode": intent.mode,
        "query_text": intent.query_text,
        "attribute_filters": dict(intent.attribute_filters),
        "hard_filters": dict(intent.hard_filters),
        "confidence": round(float(intent.confidence or 0.0), 4),
        "routing_reasons": list(intent.routing_reasons),
        "image_understanding": dict(intent.image_understanding),
    }
    if intent.celebrity_name:
        payload["celebrity_name"] = intent.celebrity_name
    if intent.mode == "style":
        payload["search_strategy"] = "appearance_vector_plus_tags"
    elif intent.mode == "celebrity":
        payload["search_strategy"] = "celebrity_reference_face"
    elif intent.mode == "hybrid":
        payload["search_strategy"] = "face_plus_style_hybrid"
    else:
        payload["search_strategy"] = "reference_face_similarity"
    return payload


def execute_photo_preference_search(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    intent: PhotoPreferenceIntent,
    image_source: str | None = None,
    requester_profile_id: int | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    """执行照片搜索（只返回原始数据）

    【Agent Native设计】
    - 此函数保留用于向后兼容
    - 新代码应直接调用底层的搜索函数（search_similar_face_candidates等）
    - Agent应根据用户意图自主决定搜索策略

    【已废弃的硬编码路由】
    以下硬编码路由逻辑仍然保留，但已废弃：
    - mode == "celebrity" → 已移除，Agent应该用photo_url参数
    - mode == "hybrid" → search_hybrid_photo_candidates
    - mode == "face" → search_similar_face_candidates
    - mode == "style" → search_style_candidates

    【推荐做法】
    Agent应该：
    1. 理解用户意图（人脸搜索、风格搜索、明星脸搜索）
    2. 自主选择搜索策略
    3. 直接调用底层搜索函数

    Args:
        source_dsn: 数据库DSN
        requester_user_key: 用户标识
        intent: 照片搜索意图
        image_source: 图片源（可选）
        requester_profile_id: 用户画像ID
        top_k: 返回数量

    Returns:
        搜索结果（原始数据）
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 硬编码路由逻辑（已废弃，保留用于向后兼容）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _logger.warning(
        "【已废弃】execute_photo_preference_search 已被废弃，"
        "请Agent自主决定搜索策略并直接调用底层搜索函数"
    )

    if intent.mode == "celebrity":
        # ⚠️ 已废弃：明星脸搜索改由Agent直接处理
        _logger.warning(
            f"【已废弃】celebrity模式应由Agent直接处理，"
            f"celebrity_name={intent.celebrity_name}, "
            f"请使用search_partner_candidates(photo_url=...)代替"
        )
        return {
            "saved": False,
            "search_type": "celebrity_face_similarity",
            "error": "celebrity模式已废弃，请使用Agent + photo_url参数",
            "hint": "Agent应该用WebSearch搜明星照片URL，然后调用search_partner_candidates(photo_url)",
            "result_count": 0,
            "results": [],
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 硬编码路由（已废弃，保留用于向后兼容）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if intent.mode == "hybrid":
        return search_hybrid_photo_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=str(image_source or "").strip() or intent.query_text,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
            query_text=intent.query_text,
        )
    if intent.mode == "face":
        return search_similar_face_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=str(image_source or "").strip() or intent.query_text,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
        )
    return search_style_candidates(
        source_dsn=source_dsn,
        image_source=str(image_source or "").strip() or intent.query_text,
        requester_profile_id=requester_profile_id,
        top_k=top_k,
        attribute_filters=intent.attribute_filters,
    )


def build_photo_recommendation_explanation_prompt(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidate = dict(candidate_row or {})
    appearance_summary = str(candidate.get("appearance_summary") or "").strip() or "暂无外貌摘要"
    candidate_name = str(
        candidate.get("display_name")
        or candidate.get("name")
        or candidate.get("nickname")
        or "候选人"
    ).strip() or "候选人"
    filter_hints = [
        f"{field_name}:{value}"
        for field_name, value in sorted(dict(intent.attribute_filters).items())
    ]
    hard_filter_hints = [
        f"{field_name}:{value}"
        for field_name, value in sorted(dict(intent.hard_filters).items())
    ]
    instructions = [
        "你是发现页的外貌解释助手。",
        "输出要自然、克制，不能直接断言对方真实长相，只能描述'更贴近用户偏好'。",
        "优先解释整体感觉，再解释具体命中点，最后再补充基础匹配理由。",
        "如果是明星参考，只能说'整体神态/氛围接近'，不能说'就是像本人'。",
    ]
    user_context = [
        f"用户意图模式: {intent.mode}",
        f"用户原始描述: {intent.raw_text or intent.query_text}",
        f"Agent 置信度: {round(float(intent.confidence or 0.0), 3)}",
        f"Agent 路由原因: {', '.join(intent.routing_reasons) or '无'}",
        f"外貌软条件: {', '.join(filter_hints) or '无'}",
        f"硬条件: {', '.join(hard_filter_hints) or '无'}",
        f"候选人: {candidate_name}",
        f"候选人外貌摘要: {appearance_summary}",
        f"基础匹配理由: {', '.join(str(item) for item in list(matched_reasons or [])) or '无'}",
    ]
    return {
        "system_prompt": "\n".join(instructions),
        "user_prompt": "\n".join(user_context),
        "prompt_version": "photo-explanation-v1",
        "facts": {
            "intent_mode": intent.mode,
            "intent_type": intent.intent_type,
            "candidate_name": candidate_name,
            "appearance_summary": appearance_summary,
            "attribute_filters": dict(intent.attribute_filters),
            "hard_filters": dict(intent.hard_filters),
            "confidence": round(float(intent.confidence or 0.0), 4),
            "routing_reasons": list(intent.routing_reasons),
            "image_understanding": dict(intent.image_understanding),
            "matched_reasons": list(matched_reasons or []),
        },
    }


def build_photo_recommendation_explanation(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidate = dict(candidate_row or {})
    prompt_payload = build_photo_recommendation_explanation_prompt(
        intent=intent,
        candidate_row=candidate,
        matched_reasons=matched_reasons,
    )
    appearance_summary = str(candidate.get("appearance_summary") or "").strip()
    highlights: list[str] = []
    if intent.celebrity_name:
        highlights.append(f"整体神态会让人联想到{intent.celebrity_name}")
    if appearance_summary:
        highlights.append(appearance_summary)
    for field_name in intent.attribute_filters:
        label = field_name.replace("_score", "")
        highlights.append(f"{label}方向更贴近你的描述")
    payload = build_match_explanation_payload(
        matched_on=list(matched_reasons or []),
        appearance_reasoning={
            "summary": (
                f"这位的长相风格更贴近你说的“{intent.query_text}”"
                if intent.mode != "celebrity"
                else f"这位的整体观感更接近你提到的{intent.celebrity_name}"
            ),
            "highlights": highlights,
        },
    )
    payload["intent_type"] = intent.intent_type
    payload["mode"] = intent.mode
    payload["prompt"] = prompt_payload
    return payload


__all__ = [
    "PhotoPreferenceIntent",
    "build_visual_search_plan",
    "build_visual_search_result_summary",
    "build_photo_recommendation_explanation_prompt",
    "build_photo_recommendation_explanation",
    "execute_photo_preference_search",
    "translate_intent_to_search_plan",
    "visual_plan_to_photo_intent",
]
